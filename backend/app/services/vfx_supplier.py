"""特效镜头供应商权限视图：按身份过滤镜头、流转审核、沉淀审核记录。

并发与重试约定：
- 每个镜头一把锁，提交/确认/指派都在锁内完成；多个供应商同时提交同一镜头时，
  只有第一个通过状态校验的请求生效，其余拿到冲突提示，一个镜头只保留一次有效结果；
- 客户端每次操作携带「请求编号」，数据失败后用同一编号重试，服务端命中已存结果
  直接返回，不重复入账、不重复流转；校验失败的请求不占号，修正后可原号重试。
"""
from __future__ import annotations

import threading
from datetime import datetime
from typing import Any

from app.services import vfx_access
from app.services.vfx_access import Operator
from app.store import store

MODULE = "vfx"
STATUSES = ["待制作", "制作中", "待审核", "已完成"]
# 动作 -> (前置状态, 目标状态)；提交类动作只有归属供应商本人能发起，确认类只有审核管理员能发起
SUPPLIER_ACTIONS = {"开始制作": ("待制作", "制作中"), "提交审核": ("制作中", "待审核")}
REVIEWER_ACTIONS = {"确认完成": ("待审核", "已完成")}


class ViewError(Exception):
    """视图层业务错误：status_code 交给路由翻译成 HTTP 响应。"""

    def __init__(self, message: str, status_code: int = 400) -> None:
        super().__init__(message)
        self.message = message
        self.status_code = status_code


def must_request_id(values: dict[str, Any]) -> str:
    """提交类操作必须携带请求编号，用于失败重试时的幂等去重。"""
    request_id = str(values.get("请求编号") or "").strip()
    if not request_id:
        raise ViewError("缺少请求编号：为避免重复入账，提交类操作必须携带请求编号", 400)
    return request_id


class VfxSupplierService:
    def __init__(self) -> None:
        self._locks: dict[int, threading.Lock] = {}
        self._locks_guard = threading.Lock()
        self._records: list[dict[str, Any]] = []
        self._request_results: dict[str, dict[str, Any]] = {}
        self._record_seq = 0

    # ---------- 查询：列表、明细、汇总、审核记录共用 scope_rows 口径 ----------

    def list_view(
        self,
        operator: Operator,
        *,
        keyword: str | None = None,
        status: str | None = None,
        page: int = 1,
        size: int = 20,
    ) -> tuple[list[dict[str, Any]], int]:
        rows = vfx_access.scope_rows(operator, store.rows(MODULE))
        if keyword:
            rows = [row for row in rows if keyword in str(row.get("镜头编号", ""))]
        if status:
            rows = [row for row in rows if row.get("status") == status]
        total = len(rows)
        start = max(page - 1, 0) * size
        return rows[start:start + size], total

    def summary(self, operator: Operator) -> list[dict[str, Any]]:
        rows = vfx_access.scope_rows(operator, store.rows(MODULE))
        items = [{"label": "可见镜头", "value": len(rows)}]
        items += [
            {"label": f"{status}镜头", "value": sum(1 for row in rows if row.get("status") == status)}
            for status in STATUSES
        ]
        return items

    def get_view(self, operator: Operator, entry_id: int) -> dict[str, Any]:
        entry = store.find(MODULE, entry_id)
        if entry is None:
            raise ViewError(f"特效镜头 {entry_id} 不存在或已归档", 404)
        if not vfx_access.can_view(operator, entry):
            raise ViewError(f"特效镜头 {entry_id} 不在{operator.role_label}的可见范围内", 403)
        return entry

    def list_review_records(self, operator: Operator, *, shot_id: int | None = None) -> list[dict[str, Any]]:
        """审核记录与列表同一口径：只返回当前身份可见镜头的记录，归属变化后自动跟随。"""
        visible_ids = {int(row["id"]) for row in vfx_access.scope_rows(operator, store.rows(MODULE))}
        records = [record for record in self._records if record["镜头id"] in visible_ids]
        if shot_id is not None:
            records = [record for record in records if record["镜头id"] == shot_id]
        return sorted(records, key=lambda record: int(record["id"]), reverse=True)

    # ---------- 动作：供应商提交、审核管理员确认、重新指派 ----------

    def run_supplier_action(self, operator: Operator, entry_id: int, action: str, request_id: str) -> dict[str, Any]:
        if action not in SUPPLIER_ACTIONS:
            raise ViewError(f"动作「{action}」不属于供应商可执行范围", 400)
        entry = self._must_find(entry_id)
        if operator.role == vfx_access.ROLE_READONLY:
            raise ViewError("只读人员不能改动审核结果", 403)
        if operator.role != vfx_access.ROLE_SUPPLIER:
            raise ViewError("审核管理员无需代替供应商提交，请由归属供应商本人操作", 403)
        if not vfx_access.can_submit(operator, entry):
            raise ViewError(f"镜头归属「{entry.get(vfx_access.OWNER_FIELD)}」，供应商只能提交本人名下镜头", 403)
        return self._run_locked(operator, entry, action, SUPPLIER_ACTIONS[action], request_id)

    def run_confirm(self, operator: Operator, entry_id: int, request_id: str) -> dict[str, Any]:
        if not vfx_access.can_confirm(operator):
            raise ViewError(f"越权确认已拒绝：{operator.role_label}不能确认完成，只有审核管理员可以", 403)
        entry = self._must_find(entry_id)
        return self._run_locked(operator, entry, "确认完成", REVIEWER_ACTIONS["确认完成"], request_id)

    def reassign(self, operator: Operator, entry_id: int, values: dict[str, Any]) -> dict[str, Any]:
        if not vfx_access.can_reassign(operator):
            raise ViewError(f"越权指派已拒绝：{operator.role_label}不能调整供应商归属", 403)
        touched = [field for field in vfx_access.PROTECTED_FIELDS if field in values]
        if touched:
            raise ViewError(f"{'、'.join(touched)}为受保护字段，不随权限归属变更", 400)
        target = str(values.get(vfx_access.OWNER_FIELD) or "").strip()
        if target not in vfx_access.KNOWN_SUPPLIERS:
            raise ViewError(f"供应商「{target}」不在名册内：{'、'.join(vfx_access.KNOWN_SUPPLIERS)}", 400)
        request_id = must_request_id(values)
        entry = self._must_find(entry_id)
        replay = self._replay(request_id)
        if replay is not None:
            return replay
        with self._lock_for(entry_id):
            replay = self._replay(request_id)
            if replay is not None:
                return replay
            previous = str(entry.get(vfx_access.OWNER_FIELD, ""))
            if previous == target:
                raise ViewError(f"镜头已归属「{target}」，无需重新指派", 400)
            entry[vfx_access.OWNER_FIELD] = target
            record = self._append_record(operator, entry, "重新指派", f"{previous} → {target}", request_id)
            result = {
                "entry": dict(entry),
                "message": f"镜头归属已由{previous}调整为{target}，列表、视图与审核记录同步生效",
                "record": record,
            }
            self._request_results[request_id] = result
            return result

    # ---------- 内部工具 ----------

    def _run_locked(
        self,
        operator: Operator,
        entry: dict[str, Any],
        action: str,
        flow: tuple[str, str],
        request_id: str,
    ) -> dict[str, Any]:
        replay = self._replay(request_id)
        if replay is not None:
            return replay
        with self._lock_for(int(entry["id"])):
            replay = self._replay(request_id)
            if replay is not None:
                return replay
            # 锁内复核归属：指派变更与提交可能并发，归属已不在本人名下就拒绝
            if operator.role == vfx_access.ROLE_SUPPLIER and not vfx_access.can_submit(operator, entry):
                raise ViewError("镜头归属已变更，供应商只能提交本人名下镜头", 403)
            expected, target = flow
            current = str(entry.get("status", ""))
            if current != expected:
                raise ViewError(
                    f"镜头当前状态为「{current}」，{action}已被先到的有效请求占用，仅保留一次有效结果",
                    409,
                )
            entry["status"] = target
            entry["制作状态"] = target
            entry["pending"] = target != STATUSES[-1]
            record = self._append_record(operator, entry, action, "已受理", request_id)
            result = {"entry": dict(entry), "message": f"特效镜头已{action}", "record": record}
            self._request_results[request_id] = result
            return result

    def _replay(self, request_id: str) -> dict[str, Any] | None:
        stored = self._request_results.get(request_id)
        if stored is None:
            return None
        return {**stored, "message": f"{stored['message']}（重复请求，已按首次结果返回）", "replayed": True}

    def _append_record(
        self,
        operator: Operator,
        entry: dict[str, Any],
        action: str,
        result_text: str,
        request_id: str,
    ) -> dict[str, Any]:
        self._record_seq += 1
        record = {
            "id": self._record_seq,
            "镜头id": int(entry["id"]),
            "镜头编号": entry.get("镜头编号"),
            "动作": action,
            "操作人": operator.name,
            "操作角色": operator.role_label,
            "归属供应商": entry.get(vfx_access.OWNER_FIELD),
            "结果": result_text,
            "请求编号": request_id,
            "时间": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        }
        self._records.append(record)
        return record

    def _must_find(self, entry_id: int) -> dict[str, Any]:
        entry = store.find(MODULE, entry_id)
        if entry is None:
            raise ViewError(f"特效镜头 {entry_id} 不存在或已归档", 404)
        return entry

    def _lock_for(self, entry_id: int) -> threading.Lock:
        with self._locks_guard:
            return self._locks.setdefault(entry_id, threading.Lock())
