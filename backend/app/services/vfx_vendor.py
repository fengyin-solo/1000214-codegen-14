"""特效镜头供应商权限视图业务规则。

视图不另存镜头数据：列表、明细与审核记录都读写同一份特效镜头表，
供应商归属调整只改「制作供应商」字段，渲染帧数、交付版本等既有数据保持不动。
"""
from __future__ import annotations

import threading
from dataclasses import dataclass
from datetime import datetime
from typing import Any
from urllib.parse import unquote

from app.store import store

MODULE = "vfx"
SUBMISSION_MODULE = "vfx_vendor_submission"

ROLE_ADMIN = "admin"
ROLE_VENDOR = "vendor"
ROLE_READONLY = "readonly"
ROLES = (ROLE_ADMIN, ROLE_VENDOR, ROLE_READONLY)
ROLE_LABELS = {ROLE_ADMIN: "审核管理员", ROLE_VENDOR: "制作供应商", ROLE_READONLY: "只读人员"}

ACTION_SUBMIT = "提交审核"
ACTION_CONFIRM = "确认完成"
ACTION_RETRY = "重试提交"
ACTION_ASSIGN = "调整归属"
ACTIONS = (ACTION_SUBMIT, ACTION_CONFIRM, ACTION_RETRY, ACTION_ASSIGN)

RECORD_ACTIVE = "有效"
RECORD_FAILED = "失败"

# 提交去重用的全局锁：多个供应商同时提交时，只有先进入临界区的一次生效。
SUBMIT_LOCK = threading.Lock()

# 镜头处于这些状态时才允许提交审核，避免待审核/已完成镜头被重复提交。
SUBMITTABLE_STATUSES = ("待制作", "制作中")


@dataclass(frozen=True)
class Identity:
    """一次请求的身份：角色决定能做什么，名称决定供应商能看到哪几条镜头。"""

    name: str
    role: str


def parse_identity(name: str | None, role: str | None) -> Identity:
    """把请求头里的身份信息整理成统一结构；缺省按管理员处理，陌生角色直接报错。

    请求头只能携带 ASCII，中文名称按百分号编码传输，这里统一解码还原。
    """
    role_value = (role or "").strip() or ROLE_ADMIN
    if role_value not in ROLES:
        raise ValueError(f"未知身份角色「{role_value}」，可选：{'、'.join(ROLES)}")
    display = unquote((name or "").strip())
    if not display and role_value != ROLE_VENDOR:
        display = "值班管理员"
    return Identity(name=display, role=role_value)


class VfxVendorService:
    """供应商权限视图：按身份控制可见范围与可执行动作。"""

    # ---------- 查询：列表、明细、审核记录共用同一份镜头数据 ----------
    def _visible_rows(self, identity: Identity) -> list[dict[str, Any]]:
        rows = store.rows(MODULE)
        if identity.role == ROLE_VENDOR:
            rows = [row for row in rows if str(row.get("制作供应商", "")) == identity.name]
        return rows

    def list_entries(
        self,
        identity: Identity,
        *,
        keyword: str | None = None,
        status: str | None = None,
        page: int = 1,
        size: int = 20,
    ) -> tuple[list[dict[str, Any]], int]:
        rows = self._visible_rows(identity)
        if keyword:
            rows = [row for row in rows if keyword in str(row.get("镜头编号", ""))]
        if status:
            rows = [row for row in rows if row.get("status") == status]
        total = len(rows)
        start = max(page - 1, 0) * size
        return rows[start:start + size], total

    def get_entry(self, identity: Identity, entry_id: int) -> tuple[dict[str, Any] | None, str]:
        entry = store.find(MODULE, entry_id)
        if entry is None:
            return None, f"特效镜头 {entry_id} 不存在或已归档"
        if identity.role == ROLE_VENDOR and str(entry.get("制作供应商", "")) != identity.name:
            return None, "越权访问已拒绝：制作供应商只能查看本人镜头"
        return entry, ""

    def list_submissions(
        self,
        identity: Identity,
        *,
        page: int = 1,
        size: int = 20,
    ) -> tuple[list[dict[str, Any]], int]:
        records = [self._enrich(record) for record in store.rows(SUBMISSION_MODULE)]
        if identity.role == ROLE_VENDOR:
            records = [record for record in records if record["当前归属供应商"] == identity.name]
        records.sort(key=lambda record: int(record.get("id", 0)), reverse=True)
        total = len(records)
        start = max(page - 1, 0) * size
        return records[start:start + size], total

    def _enrich(self, record: dict[str, Any]) -> dict[str, Any]:
        """审核记录不快照归属：读取时回查镜头当前供应商，保证与列表、视图同一口径。"""
        enriched = dict(record)
        shot = store.find(MODULE, int(record.get("镜头id", 0)))
        if shot is not None:
            enriched["当前归属供应商"] = str(shot.get("制作供应商", ""))
            enriched["镜头编号"] = str(shot.get("镜头编号", record.get("镜头编号", "")))
        else:
            enriched["当前归属供应商"] = ""
        return enriched

    # ---------- 动作 ----------
    def run_action(
        self,
        identity: Identity,
        entry_id: int,
        values: dict[str, Any],
    ) -> tuple[bool, str, dict[str, Any] | None]:
        action = str(values.get("action") or "").strip()
        entry = store.find(MODULE, entry_id)
        if entry is None:
            return False, f"特效镜头 {entry_id} 不存在或已归档", None
        if identity.role == ROLE_VENDOR and str(entry.get("制作供应商", "")) != identity.name:
            return False, "越权操作已拒绝：制作供应商只能操作本人镜头", None
        if action == ACTION_SUBMIT:
            return self._submit(identity, entry, values)
        if action == ACTION_CONFIRM:
            return self._confirm(identity, entry)
        if action == ACTION_RETRY:
            return self._retry(identity, entry, values)
        if action == ACTION_ASSIGN:
            return self._assign(identity, entry, values)
        return False, f"动作「{action}」不属于供应商权限视图可执行范围", None

    def _submit(
        self,
        identity: Identity,
        entry: dict[str, Any],
        values: dict[str, Any],
    ) -> tuple[bool, str, dict[str, Any] | None]:
        if identity.role == ROLE_READONLY:
            return False, "只读人员不能改动审核结果，本次提交已拒绝", None
        request_id = str(values.get("请求编号") or "").strip()
        with SUBMIT_LOCK:
            if request_id:
                existed = self._find_record(int(entry["id"]), request_id=request_id)
                if existed is not None:
                    if existed.get("状态") == RECORD_FAILED:
                        return self._retry_record(existed, entry, values)
                    return True, "相同请求编号的提交已受理，重复提交已去重", self._enrich(existed)
            if entry.get("status") not in SUBMITTABLE_STATUSES:
                return False, f"镜头当前状态为「{entry.get('status')}」，不能重复提交审核", None
            active = self._active_record(int(entry["id"]))
            if active is not None:
                return False, "该镜头已存在有效提交，本次提交未生效（只保留一次有效结果）", self._enrich(active)
            record = self._new_record(identity, entry, request_id)
            store.rows(SUBMISSION_MODULE).append(record)
            try:
                self._apply_submission(entry, values)
            except RuntimeError as exc:
                record["状态"] = RECORD_FAILED
                record["备注"] = f"数据写入失败，可重试：{exc}"
                return False, "提交记录已登记，但数据写入失败，可稍后重试", self._enrich(record)
        return True, "提交成功，镜头已进入待审核", self._enrich(record)

    def _confirm(
        self,
        identity: Identity,
        entry: dict[str, Any],
    ) -> tuple[bool, str, dict[str, Any] | None]:
        if identity.role == ROLE_READONLY:
            return False, "只读人员不能改动审核结果，确认已拒绝", None
        if identity.role != ROLE_ADMIN:
            return False, "越权确认已拒绝：只有审核管理员可以确认完成", None
        with SUBMIT_LOCK:
            record = self._active_record(int(entry["id"]))
            if record is None:
                return False, "该镜头没有待确认的有效提交", None
            record["结果"] = "已完成"
            record["备注"] = f"{identity.name} 确认完成"
            entry["status"] = "已完成"
            entry["pending"] = False
        return True, "审核结果已确认，镜头制作完成", self._enrich(record)

    def _retry(
        self,
        identity: Identity,
        entry: dict[str, Any],
        values: dict[str, Any],
    ) -> tuple[bool, str, dict[str, Any] | None]:
        if identity.role == ROLE_READONLY:
            return False, "只读人员不能改动审核结果，重试已拒绝", None
        with SUBMIT_LOCK:
            record = self._latest_failed(int(entry["id"]))
            if record is None:
                return False, "该镜头没有可重试的失败提交", None
            return self._retry_record(record, entry, values)

    def _retry_record(
        self,
        record: dict[str, Any],
        entry: dict[str, Any],
        values: dict[str, Any],
    ) -> tuple[bool, str, dict[str, Any] | None]:
        """重试失败提交；调用方必须已持有 SUBMIT_LOCK。"""
        if self._active_record(int(entry["id"])) is not None:
            return False, "该镜头已存在有效提交，失败记录不再重试", self._enrich(record)
        try:
            self._apply_submission(entry, values)
        except RuntimeError as exc:
            record["备注"] = f"重试仍失败，可再次重试：{exc}"
            return False, "重试仍失败，可稍后再次重试", self._enrich(record)
        record["状态"] = RECORD_ACTIVE
        record["备注"] = "重试成功"
        return True, "重试成功，镜头已进入待审核", self._enrich(record)

    def _assign(
        self,
        identity: Identity,
        entry: dict[str, Any],
        values: dict[str, Any],
    ) -> tuple[bool, str, dict[str, Any] | None]:
        if identity.role != ROLE_ADMIN:
            return False, "越权调整已拒绝：只有审核管理员可以调整供应商归属", None
        new_vendor = str(values.get("新供应商") or "").strip()
        if not new_vendor:
            return False, "缺少必填字段：新供应商", None
        old_vendor = str(entry.get("制作供应商", ""))
        if new_vendor == old_vendor:
            return False, f"镜头已归属于「{new_vendor}」，无需调整", None
        # 只改归属字段：渲染帧数、交付版本等既有数据保持不动
        entry["制作供应商"] = new_vendor
        return True, f"镜头归属已由「{old_vendor}」调整为「{new_vendor}」，列表、视图与审核记录同步生效", entry

    # ---------- 记录与落库 ----------
    def _new_record(self, identity: Identity, entry: dict[str, Any], request_id: str) -> dict[str, Any]:
        rows = store.rows(SUBMISSION_MODULE)
        seq = max((int(row.get("id", 0)) for row in rows), default=0) + 1
        return {
            "id": seq,
            "记录编号": f"SUB-{seq:04d}",
            "镜头id": int(entry.get("id", 0)),
            "镜头编号": str(entry.get("镜头编号", "")),
            "提交供应商": identity.name,
            "动作": ACTION_SUBMIT,
            "请求编号": request_id or f"AUTO-{seq:04d}",
            "状态": RECORD_ACTIVE,
            "结果": "待审核",
            "提交时间": datetime.now().isoformat(timespec="seconds"),
            "备注": "",
        }

    def _find_record(self, shot_id: int, *, request_id: str) -> dict[str, Any] | None:
        for record in store.rows(SUBMISSION_MODULE):
            if int(record.get("镜头id", 0)) == shot_id and record.get("请求编号") == request_id:
                return record
        return None

    def _active_record(self, shot_id: int) -> dict[str, Any] | None:
        actives = [
            record for record in store.rows(SUBMISSION_MODULE)
            if int(record.get("镜头id", 0)) == shot_id and record.get("状态") == RECORD_ACTIVE
        ]
        return actives[-1] if actives else None

    def _latest_failed(self, shot_id: int) -> dict[str, Any] | None:
        failed = [
            record for record in store.rows(SUBMISSION_MODULE)
            if int(record.get("镜头id", 0)) == shot_id and record.get("状态") == RECORD_FAILED
        ]
        return failed[-1] if failed else None

    @staticmethod
    def _apply_submission(entry: dict[str, Any], values: dict[str, Any]) -> None:
        """把提交结果落到镜头上；失败时抛错，由调用方把记录标记为可重试。"""
        if values.get("模拟故障"):
            raise RuntimeError("模拟的数据写入故障")
        entry["status"] = "待审核"
        entry["pending"] = True
