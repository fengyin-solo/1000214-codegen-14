"""特效镜头供应商权限策略：列表、明细视图与审核记录共用这一套口径。

身份分三种：
- 制作供应商 supplier：只能查看、提交归属自己名下的镜头；
- 只读人员 readonly：可以查看全部镜头，不能提交、不能确认、不能改归属；
- 审核管理员 reviewer：确认完成、重新指派供应商归属。

权限归属（制作供应商字段）一旦变化，列表、明细与审核记录因为都走
scope_rows 这一个过滤入口，看到的内容会同步变化，不需要各自维护。
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any

ROLE_SUPPLIER = "supplier"
ROLE_READONLY = "readonly"
ROLE_REVIEWER = "reviewer"

ROLE_LABELS = {
    ROLE_SUPPLIER: "制作供应商",
    ROLE_READONLY: "只读人员",
    ROLE_REVIEWER: "审核管理员",
}

# 演示环境的供应商名册；真实项目里来自账号体系
KNOWN_SUPPLIERS = ["星火视效", "幻彩数字", "流光特效"]

# 权限归属变更与审核流转都不允许改写的字段
PROTECTED_FIELDS = ("渲染帧数", "交付版本")

OWNER_FIELD = "制作供应商"


@dataclass(frozen=True)
class Operator:
    """一次请求的操作者身份：姓名、角色、供应商归属。"""

    name: str
    role: str
    supplier: str = ""

    @property
    def role_label(self) -> str:
        return ROLE_LABELS.get(self.role, self.role)


def resolve_operator(name: str | None, role: str | None, supplier: str | None) -> Operator:
    """把请求里的身份参数整理成 Operator；角色不在名册里直接拒绝。"""
    role_value = (role or "").strip() or ROLE_REVIEWER
    if role_value not in ROLE_LABELS:
        raise ValueError(f"未知角色「{role_value}」，只支持：{'、'.join(ROLE_LABELS.values())}")
    supplier_value = (supplier or "").strip()
    if role_value == ROLE_SUPPLIER and not supplier_value:
        raise ValueError("供应商身份必须带上供应商名称，否则无法确定可见范围")
    return Operator(name=(name or "").strip() or "值班管理员", role=role_value, supplier=supplier_value)


def scope_rows(operator: Operator, rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """按身份过滤镜头：供应商只看自己名下，其余角色看全部。"""
    if operator.role == ROLE_SUPPLIER:
        return [row for row in rows if str(row.get(OWNER_FIELD, "")) == operator.supplier]
    return list(rows)


def can_view(operator: Operator, entry: dict[str, Any]) -> bool:
    if operator.role == ROLE_SUPPLIER:
        return str(entry.get(OWNER_FIELD, "")) == operator.supplier
    return True


def can_submit(operator: Operator, entry: dict[str, Any]) -> bool:
    return operator.role == ROLE_SUPPLIER and str(entry.get(OWNER_FIELD, "")) == operator.supplier


def can_confirm(operator: Operator) -> bool:
    return operator.role == ROLE_REVIEWER


def can_reassign(operator: Operator) -> bool:
    return operator.role == ROLE_REVIEWER
