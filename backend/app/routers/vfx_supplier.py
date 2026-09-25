"""特效镜头供应商权限视图接口：列表、明细与审核记录共用同一套权限口径。"""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query, Request

from app.schemas import ActionResult, EntryPayload, PageResult
from app.services import vfx_access
from app.services.vfx_access import Operator
from app.services.vfx_supplier import STATUSES, VfxSupplierService, ViewError, must_request_id

router = APIRouter(prefix="/api/vfx-supplier", tags=["特效供应商视图"])

service = VfxSupplierService()


def get_operator(request: Request) -> Operator:
    """从查询参数解析身份：前端每次请求都会带上，缺省按审核管理员处理。"""
    params = request.query_params
    try:
        return vfx_access.resolve_operator(params.get("_operator"), params.get("_role"), params.get("_supplier"))
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


def _translate(error: ViewError) -> HTTPException:
    return HTTPException(status_code=error.status_code, detail=error.message)


@router.get("", response_model=PageResult[dict])
def list_view(
    operator: Operator = Depends(get_operator),
    keyword: str | None = Query(default=None, description="按镜头编号检索"),
    status: str | None = Query(default=None, description="待制作、制作中、待审核、已完成"),
    page: int = 1,
    size: int = 20,
) -> PageResult[dict]:
    """按当前身份可见范围列出特效镜头；供应商只能看到本人名下镜头。"""
    if size > 200:
        raise HTTPException(status_code=400, detail="每页最多 200 条，请缩小分页范围")
    items, total = service.list_view(operator, keyword=keyword, status=status, page=page, size=size)
    return PageResult(items=items, total=total, page=page, size=size)


@router.get("/summary")
def summary(operator: Operator = Depends(get_operator)) -> dict[str, object]:
    """汇总卡片：与列表同一可见口径，归属变化后同步变化。"""
    return {"items": service.summary(operator)}


@router.get("/suppliers")
def suppliers() -> dict[str, object]:
    """供应商名册与受保护字段，供前端切换身份与重新指派时使用。"""
    return {
        "suppliers": vfx_access.KNOWN_SUPPLIERS,
        "protected_fields": list(vfx_access.PROTECTED_FIELDS),
        "statuses": STATUSES,
    }


@router.get("/review-records")
def review_records(
    operator: Operator = Depends(get_operator),
    shot_id: int | None = Query(default=None, description="只看某个镜头的审核记录"),
) -> dict[str, object]:
    """审核记录：与列表同一可见口径，权限归属变化后自动跟随新归属。"""
    records = service.list_review_records(operator, shot_id=shot_id)
    return {"items": records, "total": len(records)}


@router.get("/{entry_id}", response_model=dict)
def get_view(entry_id: int, operator: Operator = Depends(get_operator)) -> dict:
    """单条明细：不在当前身份可见范围内时按越权拒绝。"""
    try:
        return service.get_view(operator, entry_id)
    except ViewError as exc:
        raise _translate(exc) from exc


@router.post("/{entry_id}/actions", response_model=ActionResult)
def run_action(entry_id: int, payload: EntryPayload, operator: Operator = Depends(get_operator)) -> ActionResult:
    """执行开始制作、提交审核、确认完成；越权请求一律拒绝并说明原因。"""
    action = str(payload.values.get("action") or "").strip()
    try:
        request_id = must_request_id(payload.values)
        if action == "确认完成":
            result = service.run_confirm(operator, entry_id, request_id)
        else:
            result = service.run_supplier_action(operator, entry_id, action, request_id)
    except ViewError as exc:
        raise _translate(exc) from exc
    return ActionResult(ok=True, message=result["message"], entry=result["entry"])


@router.post("/{entry_id}/reassign", response_model=ActionResult)
def reassign(entry_id: int, payload: EntryPayload, operator: Operator = Depends(get_operator)) -> ActionResult:
    """重新指派供应商归属：仅审核管理员；渲染帧数、交付版本为受保护字段。"""
    try:
        result = service.reassign(operator, entry_id, payload.values)
    except ViewError as exc:
        raise _translate(exc) from exc
    return ActionResult(ok=True, message=result["message"], entry=result["entry"])
