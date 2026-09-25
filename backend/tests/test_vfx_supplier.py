"""特效镜头供应商权限视图的验收用例：直接跑服务层，覆盖七条验收口径。

运行：cd backend && .venv/bin/python tests/test_vfx_supplier.py
用例之间通过新建镜头与独立请求编号隔离，顺序执行互不影响。
"""
from __future__ import annotations

import os
import sys
import threading
from contextlib import contextmanager

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.services import vfx_access  # noqa: E402
from app.services.vfx_access import Operator  # noqa: E402
from app.services.vfx_supplier import VfxSupplierService, ViewError  # noqa: E402
from app.store import store  # noqa: E402

SUP_A = Operator("星火视效-制片", "supplier", "星火视效")
SUP_B = Operator("幻彩数字-制片", "supplier", "幻彩数字")
READONLY = Operator("只读观察员", "readonly")
REVIEWER = Operator("值班管理员", "reviewer")

_shot_seq = 0


def make_shot(supplier: str = "星火视效", status: str = "制作中") -> dict:
    """往仓库里补一条测试镜头，渲染帧数与交付版本用可识别的哨兵值。"""
    global _shot_seq
    _shot_seq += 1
    rows = store.rows("vfx")
    entry = {
        "id": max((int(row.get("id", 0)) for row in rows), default=0) + 1,
        "status": status,
        "pending": True,
        "abnormal": False,
        "镜头编号": f"VFX-T{_shot_seq:04d}",
        "所属集数": "第9集",
        "特效类型": "验收测试",
        "制作供应商": supplier,
        "渲染帧数": 4000 + _shot_seq,
        "预估工时": "1小时",
        "交付版本": f"v9.{_shot_seq}",
        "制作状态": status,
    }
    rows.append(entry)
    return entry


@contextmanager
def expect_error(status_code: int):
    try:
        yield
    except ViewError as exc:
        assert exc.status_code == status_code, f"期望状态 {status_code}，实际 {exc.status_code}：{exc.message}"
        return
    raise AssertionError(f"期望抛出 ViewError({status_code})，但请求被放行了")


def listed_ids(service: VfxSupplierService, operator: Operator) -> set[int]:
    rows, _ = service.list_view(operator, size=10000)
    return {int(row["id"]) for row in rows}


def test_supplier_only_sees_and_submits_own_shots() -> None:
    """供应商只能查看、提交本人名下镜头；他人镜头查看与提交都被拒绝。"""
    service = VfxSupplierService()
    own = make_shot(supplier="星火视效", status="制作中")
    other = make_shot(supplier="幻彩数字", status="制作中")
    ids = listed_ids(service, SUP_A)
    assert own["id"] in ids and other["id"] not in ids
    with expect_error(403):
        service.get_view(SUP_A, other["id"])
    with expect_error(403):
        service.run_supplier_action(SUP_A, other["id"], "提交审核", "REQ-OWN-1")
    service.run_supplier_action(SUP_A, own["id"], "提交审核", "REQ-OWN-2")
    assert own["status"] == "待审核"
    assert other["status"] == "制作中"


def test_readonly_cannot_change_review_results() -> None:
    """只读人员能看全部镜头，但提交、确认、指派都被拒绝，审核结果保持不动。"""
    service = VfxSupplierService()
    shot = make_shot(supplier="星火视效", status="制作中")
    assert shot["id"] in listed_ids(service, READONLY)
    with expect_error(403):
        service.run_supplier_action(READONLY, shot["id"], "提交审核", "REQ-RO-1")
    with expect_error(403):
        service.run_confirm(READONLY, shot["id"], "REQ-RO-2")
    with expect_error(403):
        service.reassign(READONLY, shot["id"], {"制作供应商": "幻彩数字", "请求编号": "REQ-RO-3"})
    assert shot["status"] == "制作中"
    assert service.list_review_records(REVIEWER, shot_id=shot["id"]) == []


def test_unauthorized_confirm_rejected() -> None:
    """越权确认必须拒绝：供应商与只读人员都不能确认完成，审核管理员可以。"""
    service = VfxSupplierService()
    shot = make_shot(supplier="星火视效", status="待审核")
    with expect_error(403):
        service.run_confirm(SUP_A, shot["id"], "REQ-CF-1")
    with expect_error(403):
        service.run_confirm(READONLY, shot["id"], "REQ-CF-2")
    assert shot["status"] == "待审核"
    service.run_confirm(REVIEWER, shot["id"], "REQ-CF-3")
    assert shot["status"] == "已完成"


def test_scope_shared_across_list_view_and_records() -> None:
    """权限归属变化后，列表、明细与审核记录共享同一口径，同步跟随新归属。"""
    service = VfxSupplierService()
    shot = make_shot(supplier="星火视效", status="制作中")
    service.run_supplier_action(SUP_A, shot["id"], "提交审核", "REQ-SC-1")
    assert shot["id"] in listed_ids(service, SUP_A)
    assert shot["id"] not in listed_ids(service, SUP_B)
    assert len(service.list_review_records(SUP_A, shot_id=shot["id"])) == 1
    assert len(service.list_review_records(SUP_B, shot_id=shot["id"])) == 0

    service.reassign(REVIEWER, shot["id"], {"制作供应商": "幻彩数字", "请求编号": "REQ-SC-2"})
    assert shot["id"] not in listed_ids(service, SUP_A)
    assert shot["id"] in listed_ids(service, SUP_B)
    with expect_error(403):
        service.get_view(SUP_A, shot["id"])
    assert service.get_view(SUP_B, shot["id"])["id"] == shot["id"]
    # 审核记录跟随新归属：原供应商看不到，新供应商看到完整历史
    assert len(service.list_review_records(SUP_A, shot_id=shot["id"])) == 0
    assert len(service.list_review_records(SUP_B, shot_id=shot["id"])) == 2
    # 归属变更后原供应商再提交，按越权拒绝
    with expect_error(403):
        service.run_supplier_action(SUP_A, shot["id"], "提交审核", "REQ-SC-3")


def test_concurrent_submit_keeps_single_result() -> None:
    """多个请求同时提交同一镜头：只放行一个有效结果，其余冲突，审核记录只有一条。"""
    service = VfxSupplierService()
    shot = make_shot(supplier="星火视效", status="制作中")
    outcomes: list[tuple[str, int]] = []
    barrier = threading.Barrier(5)

    def attempt(index: int) -> None:
        barrier.wait()
        try:
            service.run_supplier_action(SUP_A, shot["id"], "提交审核", f"REQ-CC-{index}")
            outcomes.append(("ok", 200))
        except ViewError as exc:
            outcomes.append(("error", exc.status_code))

    threads = [threading.Thread(target=attempt, args=(i,)) for i in range(5)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()

    assert sum(1 for kind, _ in outcomes if kind == "ok") == 1, outcomes
    assert sum(1 for kind, code in outcomes if kind == "error" and code == 409) == 4, outcomes
    assert shot["status"] == "待审核"
    records = service.list_review_records(REVIEWER, shot_id=shot["id"])
    assert len(records) == 1

    # 不同供应商同时提交各自名下的镜头，互不阻塞
    shot_a = make_shot(supplier="星火视效", status="制作中")
    shot_b = make_shot(supplier="幻彩数字", status="制作中")
    barrier2 = threading.Barrier(2)
    errors: list[ViewError] = []

    def attempt_other(operator: Operator, entry: dict, request_id: str) -> None:
        barrier2.wait()
        try:
            service.run_supplier_action(operator, entry["id"], "提交审核", request_id)
        except ViewError as exc:
            errors.append(exc)

    ta = threading.Thread(target=attempt_other, args=(SUP_A, shot_a, "REQ-CC-A"))
    tb = threading.Thread(target=attempt_other, args=(SUP_B, shot_b, "REQ-CC-B"))
    ta.start()
    tb.start()
    ta.join()
    tb.join()
    assert not errors
    assert shot_a["status"] == "待审核" and shot_b["status"] == "待审核"


def test_failed_attempt_can_retry_with_same_request_id() -> None:
    """数据失败可重试：失败不占号，同一请求编号重试幂等，不重复入账。"""
    service = VfxSupplierService()
    shot = make_shot(supplier="星火视效", status="待制作")
    # 状态不满足，提交失败；失败的请求不占号
    with expect_error(409):
        service.run_supplier_action(SUP_A, shot["id"], "提交审核", "REQ-RT-1")
    service.run_supplier_action(SUP_A, shot["id"], "开始制作", "REQ-RT-0")
    # 用同一请求编号重试，这次成功
    result = service.run_supplier_action(SUP_A, shot["id"], "提交审核", "REQ-RT-1")
    assert result["entry"]["status"] == "待审核"
    # 网络抖动后的重复重试命中已存结果，不重复流转、不重复入账
    replay = service.run_supplier_action(SUP_A, shot["id"], "提交审核", "REQ-RT-1")
    assert "重复请求" in replay["message"]
    assert shot["status"] == "待审核"
    records = service.list_review_records(REVIEWER, shot_id=shot["id"])
    assert len([record for record in records if record["动作"] == "提交审核"]) == 1


def test_protected_fields_untouched() -> None:
    """既有渲染帧数与交付版本不受提交、确认、指派影响；携带受保护字段直接拒绝。"""
    service = VfxSupplierService()
    shot = make_shot(supplier="星火视效", status="待制作")
    before = {field: shot[field] for field in vfx_access.PROTECTED_FIELDS}
    service.run_supplier_action(SUP_A, shot["id"], "开始制作", "REQ-PF-1")
    service.run_supplier_action(SUP_A, shot["id"], "提交审核", "REQ-PF-2")
    service.run_confirm(REVIEWER, shot["id"], "REQ-PF-3")
    service.reassign(REVIEWER, shot["id"], {"制作供应商": "幻彩数字", "请求编号": "REQ-PF-4"})
    for field, value in before.items():
        assert shot[field] == value, f"{field} 被改动：{value} -> {shot[field]}"
    with expect_error(400):
        service.reassign(REVIEWER, shot["id"], {"制作供应商": "星火视效", "渲染帧数": 1, "请求编号": "REQ-PF-5"})
    with expect_error(400):
        service.reassign(REVIEWER, shot["id"], {"制作供应商": "星火视效", "交付版本": "v0.0", "请求编号": "REQ-PF-6"})


if __name__ == "__main__":
    tests = [value for name, value in sorted(globals().items()) if name.startswith("test_")]
    failed = 0
    for test in tests:
        try:
            test()
            print(f"PASS {test.__name__}")
        except Exception as exc:  # noqa: BLE001
            failed += 1
            print(f"FAIL {test.__name__}: {exc}")
    print(f"\n{len(tests) - failed}/{len(tests)} 通过")
    sys.exit(1 if failed else 0)
