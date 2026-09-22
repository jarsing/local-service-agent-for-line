"""Day 8 ADK 工具確認離線相容性測試。

使用 MockLlm 模擬模型工具呼叫，完全離線測試 ADK 工具確認的事件暫停、
FunctionResponse 回傳、重新呼叫原工具、以及伺服器端狀態核對。
0 模型 API 呼叫、0 外部網路存取。
"""
from __future__ import annotations

import asyncio
from datetime import datetime, timezone
from typing import AsyncGenerator
import unittest

from pydantic import PrivateAttr
from google.genai import types
from google.adk.models.base_llm import BaseLlm
from google.adk.models.llm_request import LlmRequest
from google.adk.models.llm_response import LlmResponse
from google.adk.runners import Runner
from google.adk.sessions import InMemorySessionService

from adapter import CatalogCatalogState, DEFAULT_EVENT_ID
from adk_bridge import ConfirmationService, create_day08_agent
from confirmation import Identity


class ScriptedMockLlm(BaseLlm):
    """可指定回應腳本的 MockLlm。"""
    _turns: int = PrivateAttr(default=0)
    _draft_id: str = PrivateAttr(default="draft-test-01")
    _request_text: str = PrivateAttr(default="請問集合地點在哪裡？")

    def __init__(
        self,
        draft_id: str = "draft-test-01",
        request_text: str = "請問集合地點在哪裡？",
    ) -> None:
        super().__init__(model="mock-gemini-model")
        self._draft_id = draft_id
        self._request_text = request_text

    async def generate_content_async(
        self, req: LlmRequest, stream: bool = False
    ) -> AsyncGenerator[LlmResponse, None]:
        self._turns += 1
        if self._turns == 1:
            # 回合 1：模型決定呼叫 prepare_handoff_draft
            fc = types.FunctionCall(
                name="prepare_handoff_draft",
                args={
                    "draft_id": self._draft_id,
                    "request_text": self._request_text,
                    "event_id": DEFAULT_EVENT_ID,
                },
                id="call_fc_01",
            )
            yield LlmResponse(
                content=types.Content(
                    role="model",
                    parts=[types.Part(function_call=fc)],
                )
            )
        else:
            # 回合 2：工具確認後模型總結
            yield LlmResponse(
                content=types.Content(
                    role="model",
                    parts=[types.Part(text="已為您處理確認流程！")],
                )
            )


class AdkConfirmationTests(unittest.IsolatedAsyncioTestCase):

    async def asyncSetUp(self) -> None:
        self.catalog_state = CatalogCatalogState("v1")
        self.service = ConfirmationService(
            catalog_state=self.catalog_state,
            time_provider=lambda: datetime(2026, 9, 22, 1, 0, tzinfo=timezone.utc),
        )
        self.identity = Identity("demo-user-1", "demo-session-1")
        self.session_service = InMemorySessionService()

    async def _setup_flow(self, mock_llm: ScriptedMockLlm):
        agent = create_day08_agent(
            model=mock_llm,
            service=self.service,
            current_identity=self.identity,
        )
        runner = Runner(agent=agent, session_service=self.session_service, app_name="local_day08")
        session = await self.session_service.create_session(
            app_name="local_day08",
            user_id=self.identity.user_id,
            session_id=self.identity.session_id,
        )
        return runner, session

    async def test_normal_confirmation_flow(self):
        """情境一：正常流程，內容與版本均相同，確認被記錄。"""
        mock_llm = ScriptedMockLlm()
        runner, session = await self._setup_flow(mock_llm)

        # 步驟 1：使用者送出需求
        user_msg = types.Content(role="user", parts=[types.Part(text="請幫我整理集合地點詢問")])
        events_turn1 = []
        async for ev in runner.run_async(session_id=session.id, user_id=self.identity.user_id, new_message=user_msg):
            events_turn1.append(ev)

        # 檢查是否有 adk_request_confirmation
        conf_fc = None
        for ev in events_turn1:
            for fc in ev.get_function_calls():
                if fc.name == "adk_request_confirmation":
                    conf_fc = fc
                    break
        self.assertIsNotNone(conf_fc, "必須發出 adk_request_confirmation 事件")
        self.assertIn("originalFunctionCall", conf_fc.args)

        # 步驟 2：使用者按下確認
        conf_resp = types.FunctionResponse(
            name="adk_request_confirmation",
            id=conf_fc.id,
            response={"confirmed": True},
        )
        user_reply = types.Content(role="user", parts=[types.Part(function_response=conf_resp)])

        tool_resp = None
        async for ev in runner.run_async(session_id=session.id, user_id=self.identity.user_id, new_message=user_reply):
            for fr in ev.get_function_responses():
                if fr.name == "prepare_handoff_draft":
                    tool_resp = fr.response

        self.assertIsNotNone(tool_resp, "必須收到 prepare_handoff_draft 工具的後續執行結果")
        self.assertEqual(tool_resp.get("status"), "confirmation_recorded")
        self.assertFalse(tool_resp.get("execution_allowed"))
        self.assertIn("receipt", tool_resp)
        self.assertEqual(tool_resp["receipt"]["catalog_version"], "v-0337e2296139")

    async def test_version_changed_during_waiting(self):
        """情境二：等待確認期間，系統切換新版，按下原確認應回傳 version_changed。"""
        mock_llm = ScriptedMockLlm()
        runner, session = await self._setup_flow(mock_llm)

        # 步驟 1：出示確認（此時是 v1，時段 07:30~11:00）
        user_msg = types.Content(role="user", parts=[types.Part(text="請幫我整理集合地點詢問")])
        conf_fc = None
        async for ev in runner.run_async(session_id=session.id, user_id=self.identity.user_id, new_message=user_msg):
            for fc in ev.get_function_calls():
                if fc.name == "adk_request_confirmation":
                    conf_fc = fc

        self.assertIsNotNone(conf_fc)

        # 步驟 2：在等待期間切換版本至 v2（08:00~11:00）
        self.catalog_state.switch_to("v2")
        self.assertEqual(self.catalog_state.catalog_version, "v-62ccd0ef3ca44e6ca8b7ef2d3302ab28")

        # 步驟 3：使用者按下原畫面的確認
        conf_resp = types.FunctionResponse(
            name="adk_request_confirmation",
            id=conf_fc.id,
            response={"confirmed": True},
        )
        user_reply = types.Content(role="user", parts=[types.Part(function_response=conf_resp)])

        tool_resp = None
        async for ev in runner.run_async(session_id=session.id, user_id=self.identity.user_id, new_message=user_reply):
            for fr in ev.get_function_responses():
                if fr.name == "prepare_handoff_draft":
                    tool_resp = fr.response

        self.assertIsNotNone(tool_resp)
        self.assertEqual(tool_resp.get("status"), "version_changed")
        self.assertFalse(tool_resp.get("execution_allowed"))

    async def test_user_cancellation(self):
        """情境三：使用者按下取消（confirmed=False）。"""
        mock_llm = ScriptedMockLlm()
        runner, session = await self._setup_flow(mock_llm)

        user_msg = types.Content(role="user", parts=[types.Part(text="請幫我整理集合地點詢問")])
        conf_fc = None
        async for ev in runner.run_async(session_id=session.id, user_id=self.identity.user_id, new_message=user_msg):
            for fc in ev.get_function_calls():
                if fc.name == "adk_request_confirmation":
                    conf_fc = fc

        conf_resp = types.FunctionResponse(
            name="adk_request_confirmation",
            id=conf_fc.id,
            response={"confirmed": False},
        )
        user_reply = types.Content(role="user", parts=[types.Part(function_response=conf_resp)])

        tool_resp = None
        async for ev in runner.run_async(session_id=session.id, user_id=self.identity.user_id, new_message=user_reply):
            for fr in ev.get_function_responses():
                if fr.name == "prepare_handoff_draft":
                    tool_resp = fr.response

        self.assertEqual(tool_resp.get("status"), "cancelled")
        self.assertFalse(tool_resp.get("execution_allowed"))

    async def test_repeat_confirmation_returns_same_receipt(self):
        """情境四：同一確認重送，回傳 already_confirmed 與相同 receipt。"""
        mock_llm = ScriptedMockLlm()
        runner, session = await self._setup_flow(mock_llm)

        user_msg = types.Content(role="user", parts=[types.Part(text="請幫我整理集合地點詢問")])
        conf_fc = None
        async for ev in runner.run_async(session_id=session.id, user_id=self.identity.user_id, new_message=user_msg):
            for fc in ev.get_function_calls():
                if fc.name == "adk_request_confirmation":
                    conf_fc = fc

        conf_resp = types.FunctionResponse(
            name="adk_request_confirmation",
            id=conf_fc.id,
            response={"confirmed": True},
        )
        user_reply = types.Content(role="user", parts=[types.Part(function_response=conf_resp)])

        first_tool_resp = None
        async for ev in runner.run_async(session_id=session.id, user_id=self.identity.user_id, new_message=user_reply):
            for fr in ev.get_function_responses():
                if fr.name == "prepare_handoff_draft":
                    first_tool_resp = fr.response

        self.assertEqual(first_tool_resp.get("status"), "confirmation_recorded")

        # 模擬再次送出相同 confirmation_id 的確認
        second_resp = self.service.validate_and_record(
            confirmation_id=first_tool_resp["receipt"]["confirmation_id"],
            actor=self.identity,
            draft_id=mock_llm._draft_id,
            approved=True,
        )
        self.assertEqual(second_resp.get("status"), "already_confirmed")
        self.assertEqual(second_resp.get("receipt"), first_tool_resp.get("receipt"))

    async def test_wrong_actor_rejected(self):
        """情境五：不同使用者試圖核准該確認，回傳 wrong_actor。"""
        mock_llm = ScriptedMockLlm()
        runner, session = await self._setup_flow(mock_llm)

        user_msg = types.Content(role="user", parts=[types.Part(text="請幫我整理集合地點詢問")])
        conf_fc = None
        async for ev in runner.run_async(session_id=session.id, user_id=self.identity.user_id, new_message=user_msg):
            for fc in ev.get_function_calls():
                if fc.name == "adk_request_confirmation":
                    conf_fc = fc

        # 使用者 B 試圖確認
        other_user = Identity("demo-user-b", "demo-session-b")
        cid = conf_fc.args["toolConfirmation"]["payload"]["confirmation_id"]
        res = self.service.validate_and_record(
            confirmation_id=cid,
            actor=other_user,
            draft_id=mock_llm._draft_id,
            approved=True,
        )
        self.assertEqual(res.get("status"), "wrong_actor")
        self.assertFalse(res.get("execution_allowed"))

    async def test_m03_unmatched_id_does_not_confirm_latest_draft(self):
        """M03 回歸：提供無效或缺少確認 ID 時，絕不回退確認最新的待確認單；涵蓋 session helper。"""
        from adk_bridge import lookup_confirmation_id_from_session
        from google.adk.events import Event

        # 1. 驗證 lookup_confirmation_id_from_session 邊界條件
        self.assertIsNone(lookup_confirmation_id_from_session(None))

        # 建立具備 session events 的模擬 context 測試 helper 正向與反向配對
        class DummyInvocationContext:
            def __init__(self, session):
                self.session = session

        class DummyToolContext:
            def __init__(self, fc_id, session):
                self.function_call_id = fc_id
                self._invocation_context = DummyInvocationContext(session)

        mock_fc = types.FunctionCall(
            name="adk_request_confirmation",
            id="conf_call_999",
            args={
                "originalFunctionCall": {"id": "fc_match_123"},
                "toolConfirmation": {
                    "payload": {"confirmation_id": "cid-session-matched-789"}
                },
            },
        )
        mock_event = Event(
            author="local_day08_agent",
            content=types.Content(role="model", parts=[types.Part(function_call=mock_fc)]),
        )

        test_sess = await self.session_service.create_session(
            app_name="local_day08", user_id="user_m03_helper", session_id="sess_m03_helper"
        )
        test_sess.events.append(mock_event)

        # 正向：matching function_call_id 能找到正確 confirmation_id
        matching_ctx = DummyToolContext("fc_match_123", test_sess)
        self.assertEqual(
            lookup_confirmation_id_from_session(matching_ctx),
            "cid-session-matched-789",
        )

        # 反向：無 matching event 回傳 None
        unmatched_ctx = DummyToolContext("fc_different_456", test_sess)
        self.assertIsNone(lookup_confirmation_id_from_session(unmatched_ctx))

        # 2. 業務端驗證：開立草稿 A 與草稿 B，無效 ID 絕不回退確認最新待確認單
        op_a = self.service.get_or_create_operation("draft-A", DEFAULT_EVENT_ID, "問題A", self.identity)
        offer_a = self.service.issue_offer(self.identity, op_a)

        # 同一人在同一 session 開立草稿 B
        op_b = self.service.get_or_create_operation("draft-B", DEFAULT_EVENT_ID, "問題B", self.identity)
        offer_b = self.service.issue_offer(self.identity, op_b)

        # 試圖以不存在或錯誤的 confirmation_id 確認
        res = self.service.validate_and_record(
            confirmation_id="fake-invalid-id",
            actor=self.identity,
            draft_id="draft-A",
            approved=True,
        )
        self.assertEqual(res.get("status"), "not_found")
        self.assertFalse(res.get("execution_allowed"))

        # 確認草稿 B 依然處於 awaiting_confirmation，未被誤確認
        record_b = self.service.store._records[offer_b["confirmation_id"]]
        self.assertEqual(record_b["status"], "awaiting_confirmation")

    async def test_m04_modified_draft_content_rejected_as_content_changed(self):
        """M04 回歸：在等待確認期間若草稿內容被修改，舊確認單因操作指紋不符回傳 content_changed。"""
        # 建立草稿 001 原問題
        op1 = self.service.get_or_create_operation("draft-001", DEFAULT_EVENT_ID, "請問集合地點在哪裡？", self.identity)
        offer1 = self.service.issue_offer(self.identity, op1)

        # 使用者修改草稿問題為停車資訊（目錄版本未變）
        self.service.get_or_create_operation("draft-001", DEFAULT_EVENT_ID, "請問附近是否有收費停車場？", self.identity)

        # 以舊確認單按下確認
        res = self.service.validate_and_record(
            confirmation_id=offer1["confirmation_id"],
            actor=self.identity,
            draft_id="draft-001",
            approved=True,
        )
        self.assertEqual(res.get("status"), "content_changed")
        self.assertFalse(res.get("execution_allowed"))

    async def test_m04_draft_isolation_across_different_users(self):
        """M04 回歸：不同使用者使用相同 draft_id 時，草稿內容互不污染。"""
        user_a = Identity("user-A", "session-A")
        user_b = Identity("user-B", "session-B")

        op_a = self.service.get_or_create_operation("draft-shared", DEFAULT_EVENT_ID, "使用者A的問題", user_a)
        offer_a = self.service.issue_offer(user_a, op_a)

        op_b = self.service.get_or_create_operation("draft-shared", DEFAULT_EVENT_ID, "使用者B的問題", user_b)
        offer_b = self.service.issue_offer(user_b, op_b)

        # 使用者 A 正常確認自己未變動的草稿
        res_a = self.service.validate_and_record(
            confirmation_id=offer_a["confirmation_id"],
            actor=user_a,
            draft_id="draft-shared",
            approved=True,
        )
        self.assertEqual(res_a.get("status"), "confirmation_recorded")

        # 使用者 B 正常確認自己未變動的草稿
        res_b = self.service.validate_and_record(
            confirmation_id=offer_b["confirmation_id"],
            actor=user_b,
            draft_id="draft-shared",
            approved=True,
        )
        self.assertEqual(res_b.get("status"), "confirmation_recorded")

    async def test_m05_runner_handles_abnormal_cases(self):
        """M05 回歸：測試 runner 正確判定無確認事件或非預期狀態之情境。"""
        from run import run_scenario_with_runner, ScenarioMetricsTracker

        class NoConfirmMockLlm(BaseLlm):
            """模擬模型未發出確認工具呼叫，僅回傳一般文字。"""
            def __init__(self) -> None:
                super().__init__(model="mock-no-confirm")

            async def generate_content_async(self, req: LlmRequest, stream: bool = False):
                yield LlmResponse(
                    content=types.Content(
                        role="model",
                        parts=[types.Part(text="我是普通文字回答，未發起工具確認。")],
                    )
                )

        # 案例 1：無確認事件，run_scenario_with_runner 應回傳 success=False 與相符 error
        runner1, session1 = await self._setup_flow(NoConfirmMockLlm())
        tracker1 = ScenarioMetricsTracker("異常測試1", max_calls=4)
        res1 = await run_scenario_with_runner(
            runner=runner1,
            session_id=session1.id,
            user_id=self.identity.user_id,
            service=self.service,
            user_prompt="請幫我詢問活動",
            tracker=tracker1,
            expected_status="confirmation_recorded",
        )
        self.assertFalse(res1["success"])
        self.assertIn("No adk_request_confirmation", res1.get("error", ""))

        # 案例 2：工具回傳狀態與預期不符時，判定為失敗（重置 session_service 避免重名）
        self.session_service = InMemorySessionService()
        mock_llm2 = ScriptedMockLlm()
        runner2, session2 = await self._setup_flow(mock_llm2)
        tracker2 = ScenarioMetricsTracker("異常測試2", max_calls=4)
        res2 = await run_scenario_with_runner(
            runner=runner2,
            session_id=session2.id,
            user_id=self.identity.user_id,
            service=self.service,
            user_prompt="請幫我整理集合地點詢問",
            tracker=tracker2,
            expected_status="version_changed",
        )
        self.assertFalse(res2["success"])
        self.assertIn("與預期（version_changed）不符", res2.get("error", ""))


if __name__ == "__main__":
    unittest.main()
