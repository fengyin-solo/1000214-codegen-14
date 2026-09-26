"""特效镜头供应商权限视图：权限、并发去重、失败重试与既有数据不动的规则测试。"""
from __future__ import annotations

import copy
import threading
import unittest
from urllib.parse import quote

from fastapi.testclient import TestClient

from app.main import app
from app.services.vfx_vendor import Identity, VfxVendorService
from app.store import store


def make_headers(role: str, name: str) -> dict[str, str]:
    """请求头只能携带 ASCII，中文名称按百分号编码传输。"""
    return {"X-Operator-Role": role, "X-Operator-Name": quote(name)}


ADMIN = make_headers("admin", "值班管理员")
VENDOR_A = make_headers("vendor", "视界特效")
VENDOR_B = make_headers("vendor", "幻彩数字")
READONLY = make_headers("readonly", "跟组实习生")


def submissions_of(shot_id: int) -> list[dict]:
    return [row for row in store.rows("vfx_vendor_submission") if row.get("镜头id") == shot_id]


class VfxVendorPermissionTest(unittest.TestCase):
    def setUp(self) -> None:
        self._snapshot = copy.deepcopy(store._tables)
        store.rows("vfx_vendor_submission").clear()
        self.client = TestClient(app)

    def tearDown(self) -> None:
        store._tables = self._snapshot

    # ---------- 可见范围 ----------
    def test_vendor_only_sees_own_shots(self) -> None:
        resp = self.client.get("/api/vfx-vendor", headers=VENDOR_A)
        self.assertEqual(resp.status_code, 200)
        payload = resp.json()
        self.assertGreater(payload["total"], 0)
        for item in payload["items"]:
            self.assertEqual(item["制作供应商"], "视界特效")

    def test_admin_and_readonly_see_all_shots(self) -> None:
        for headers in (ADMIN, READONLY):
            resp = self.client.get("/api/vfx-vendor", headers=headers)
            self.assertEqual(resp.status_code, 200)
            self.assertEqual(resp.json()["total"], len(store.rows("vfx")))

    def test_vendor_cannot_view_others_detail(self) -> None:
        own = self.client.get("/api/vfx-vendor/1", headers=VENDOR_A)
        self.assertEqual(own.status_code, 200)
        others = self.client.get("/api/vfx-vendor/2", headers=VENDOR_A)
        self.assertEqual(others.status_code, 403)

    def test_unknown_role_rejected(self) -> None:
        resp = self.client.get("/api/vfx-vendor", headers={"X-Operator-Role": "super"})
        self.assertEqual(resp.status_code, 400)

    # ---------- 提交与越权 ----------
    def _submit(self, shot_id: int, headers: dict, **values):
        body = {"action": "提交审核", **values}
        return self.client.post(f"/api/vfx-vendor/{shot_id}/actions", headers=headers, json={"values": body})

    def test_vendor_submit_own_shot(self) -> None:
        resp = self._submit(1, VENDOR_A, 请求编号="REQ-1")
        self.assertTrue(resp.json()["ok"], resp.json()["message"])
        self.assertEqual(store.find("vfx", 1)["status"], "待审核")
        records = submissions_of(1)
        self.assertEqual(len(records), 1)
        self.assertEqual(records[0]["状态"], "有效")
        self.assertEqual(records[0]["提交供应商"], "视界特效")

    def test_vendor_submit_others_shot_rejected(self) -> None:
        resp = self._submit(2, VENDOR_A)
        self.assertFalse(resp.json()["ok"])
        self.assertEqual(submissions_of(2), [])
        self.assertEqual(store.find("vfx", 2)["status"], "制作中")

    def test_readonly_cannot_submit_or_confirm(self) -> None:
        submit = self._submit(1, READONLY)
        self.assertFalse(submit.json()["ok"])
        confirm = self.client.post(
            "/api/vfx-vendor/1/actions", headers=READONLY, json={"values": {"action": "确认完成"}}
        )
        self.assertFalse(confirm.json()["ok"])
        self.assertEqual(submissions_of(1), [])
        self.assertEqual(store.find("vfx", 1)["status"], "待制作")

    def test_vendor_confirm_rejected_admin_confirm_ok(self) -> None:
        self.assertTrue(self._submit(1, VENDOR_A).json()["ok"])
        vendor_confirm = self.client.post(
            "/api/vfx-vendor/1/actions", headers=VENDOR_A, json={"values": {"action": "确认完成"}}
        )
        self.assertFalse(vendor_confirm.json()["ok"])
        self.assertIn("越权", vendor_confirm.json()["message"])
        admin_confirm = self.client.post(
            "/api/vfx-vendor/1/actions", headers=ADMIN, json={"values": {"action": "确认完成"}}
        )
        self.assertTrue(admin_confirm.json()["ok"], admin_confirm.json()["message"])
        self.assertEqual(store.find("vfx", 1)["status"], "已完成")
        self.assertEqual(submissions_of(1)[0]["结果"], "已完成")

    # ---------- 并发与幂等 ----------
    def test_concurrent_submit_keeps_single_active_record(self) -> None:
        service = VfxVendorService()
        results: list[bool] = []

        def worker(index: int) -> None:
            ok, _message, _record = service.run_action(
                Identity(name="视界特效", role="vendor"),
                1,
                {"action": "提交审核", "请求编号": f"REQ-T-{index}"},
            )
            results.append(ok)

        threads = [threading.Thread(target=worker, args=(i,)) for i in range(6)]
        for thread in threads:
            thread.start()
        for thread in threads:
            thread.join()

        self.assertEqual(sum(1 for ok in results if ok), 1)
        actives = [row for row in submissions_of(1) if row["状态"] == "有效"]
        self.assertEqual(len(actives), 1)
        self.assertEqual(store.find("vfx", 1)["status"], "待审核")

    def test_same_request_id_is_idempotent(self) -> None:
        first = self._submit(1, VENDOR_A, 请求编号="REQ-DUP")
        second = self._submit(1, VENDOR_A, 请求编号="REQ-DUP")
        self.assertTrue(first.json()["ok"])
        self.assertTrue(second.json()["ok"])
        self.assertIn("去重", second.json()["message"])
        self.assertEqual(len(submissions_of(1)), 1)

    # ---------- 失败可重试 ----------
    def test_failed_submission_can_retry(self) -> None:
        failed = self._submit(1, VENDOR_A, 请求编号="REQ-F1", 模拟故障=True)
        self.assertFalse(failed.json()["ok"])
        self.assertEqual(store.find("vfx", 1)["status"], "待制作")
        self.assertEqual(submissions_of(1)[0]["状态"], "失败")

        retried = self.client.post(
            "/api/vfx-vendor/1/actions", headers=VENDOR_A, json={"values": {"action": "重试提交"}}
        )
        self.assertTrue(retried.json()["ok"], retried.json()["message"])
        self.assertEqual(store.find("vfx", 1)["status"], "待审核")
        records = submissions_of(1)
        self.assertEqual(len(records), 1)
        self.assertEqual(records[0]["状态"], "有效")

    def test_failed_submission_retry_with_same_request_id(self) -> None:
        self.assertFalse(self._submit(1, VENDOR_A, 请求编号="REQ-F2", 模拟故障=True).json()["ok"])
        retried = self._submit(1, VENDOR_A, 请求编号="REQ-F2")
        self.assertTrue(retried.json()["ok"], retried.json()["message"])
        self.assertEqual(len(submissions_of(1)), 1)
        self.assertEqual(submissions_of(1)[0]["状态"], "有效")

    # ---------- 归属调整与同一口径 ----------
    def test_assign_keeps_views_consistent_and_preserves_fields(self) -> None:
        before = dict(store.find("vfx", 1))
        self.assertTrue(self._submit(1, VENDOR_A).json()["ok"])

        assign = self.client.post(
            "/api/vfx-vendor/1/actions",
            headers=ADMIN,
            json={"values": {"action": "调整归属", "新供应商": "幻影工坊"}},
        )
        self.assertTrue(assign.json()["ok"], assign.json()["message"])

        after = store.find("vfx", 1)
        self.assertEqual(after["制作供应商"], "幻影工坊")
        self.assertEqual(after["渲染帧数"], before["渲染帧数"])
        self.assertEqual(after["交付版本"], before["交付版本"])

        # 列表口径：原供应商看不到，新供应商看得到
        old_list = self.client.get("/api/vfx-vendor", headers=VENDOR_A).json()
        self.assertNotIn(1, [item["id"] for item in old_list["items"]])
        new_headers = make_headers("vendor", "幻影工坊")
        new_list = self.client.get("/api/vfx-vendor", headers=new_headers).json()
        self.assertIn(1, [item["id"] for item in new_list["items"]])

        # 审核记录口径：跟着当前归属走
        old_records = self.client.get("/api/vfx-vendor/submissions", headers=VENDOR_A).json()
        self.assertEqual(old_records["total"], 0)
        new_records = self.client.get("/api/vfx-vendor/submissions", headers=new_headers).json()
        self.assertEqual(new_records["total"], 1)
        self.assertEqual(new_records["items"][0]["当前归属供应商"], "幻影工坊")

        # 既有特效模块读到的渲染帧数与交付版本保持一致
        legacy = self.client.get("/api/vfx/1").json()
        self.assertEqual(legacy["渲染帧数"], before["渲染帧数"])
        self.assertEqual(legacy["交付版本"], before["交付版本"])

    def test_vendor_cannot_assign(self) -> None:
        resp = self.client.post(
            "/api/vfx-vendor/1/actions",
            headers=VENDOR_A,
            json={"values": {"action": "调整归属", "新供应商": "幻影工坊"}},
        )
        self.assertFalse(resp.json()["ok"])
        self.assertEqual(store.find("vfx", 1)["制作供应商"], "视界特效")


if __name__ == "__main__":
    unittest.main()
