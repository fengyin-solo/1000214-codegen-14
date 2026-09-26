"""特效镜头供应商权限视图接口：按身份过滤镜头列表，提交、确认与归属调整共用同一份镜头数据。"""
from __future__ import annotations

from fastapi import APIRouter, Header, HTTPException, Query

from app.schemas import ActionResult, EntryPayload, PageResult
from app.services.vfx_vendor import Identity, VfxVendorService, parse_identity

router = APIRouter(prefix="/api/vfx-vendor", tags=["特效供应商权限视图"])

service = VfxVendorService()

LIST_FIELDS = ["镜头编号", "所属集数", "特效类型", "制作供应商", "渲染帧数", "预估工时", "交付版本", "制作状态"]
STATUSES = ["待制作", "制作中", "待审核", "已完成"]


def _identity(
    x_operator_name: str | None,
    x_operator_role: str | None,
) -> Identity:
    """解析请求头身份；角色不在允许范围时直接 400，而不是默默放行。"""
    try:
        return parse_identity(x_operator_name, x_operator_role)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.get("", response_model=PageResult[dict])
def list_entries(
    keyword: str | None = Query(default=None, description="按镜头编号检索"),
    status: str | None = Query(default=None, description="待制作、制作中、待审核、已完成"),
    page: int = 1,
    size: int = 20,
    x_operator_name: str | None = Header(default=None),
    x_operator_role: str | None = Header(default=None),
) -> PageResult[dict]:
    """按身份返回可见镜头：供应商只看本人镜头，只读人员与管理员看全量。"""
    if size > 200:
        raise HTTPException(status_code=400, detail="每页最多 200 条，请缩小分页范围")
    identity = _identity(x_operator_name, x_operator_role)
    items, total = service.list_entries(identity, keyword=keyword, status=status, page=page, size=size)
    return PageResult(items=items, total=total, page=page, size=size)


@router.get("/submissions", response_model=PageResult[dict])
def list_submissions(
    page: int = 1,
    size: int = 20,
    x_operator_name: str | None = Header(default=None),
    x_operator_role: str | None = Header(default=None),
) -> PageResult[dict]:
    """审核记录与列表同一口径：归属调整后，供应商看到的记录跟着当前归属走。"""
    if size > 200:
        raise HTTPException(status_code=400, detail="每页最多 200 条，请缩小分页范围")
    identity = _identity(x_operator_name, x_operator_role)
    items, total = service.list_submissions(identity, page=page, size=size)
    return PageResult(items=items, total=total, page=page, size=size)


@router.get("/{entry_id}", response_model=dict)
def get_entry(
    entry_id: int,
    x_operator_name: str | None = Header(default=None),
    x_operator_role: str | None = Header(default=None),
) -> dict:
    """读取单条镜头明细；供应商读他人镜头会被拒绝。"""
    identity = _identity(x_operator_name, x_operator_role)
    entry, message = service.get_entry(identity, entry_id)
    if entry is None:
        status_code = 403 if "越权" in message else 404
        raise HTTPException(status_code=status_code, detail=message)
    return entry


@router.post("/{entry_id}/actions", response_model=ActionResult)
def run_action(
    entry_id: int,
    payload: EntryPayload,
    x_operator_name: str | None = Header(default=None),
    x_operator_role: str | None = Header(default=None),
) -> ActionResult:
    """执行提交审核、确认完成、重试提交、调整归属；越权动作一律拒绝并说明原因。"""
    identity = _identity(x_operator_name, x_operator_role)
    ok, message, entry = service.run_action(identity, entry_id, payload.values)
    return ActionResult(ok=ok, message=message, entry=entry)
