from __future__ import annotations

import asyncio
import json
import unittest

from examples.day17.adapters import (
    QueryPhase, ScriptedInterpreter, ScriptedStep, ScriptedTools,
    TrustedQueryResult, classify_exception, normalize_executed_result,
)
from examples.day17.demo import ACTOR, OfflineStore, SQLiteFixtureTools, message_event
from examples.day17.main import HELP_TEXT, RETRY_TEXT, QueryService
from examples.day17.outcomes import (
    CatalogChanged, FailureReason, PreferenceChanged, QueryState,
    QueryUnavailable, ToolContractError, UpstreamHTTPError,
)


def checked(raw: object, tool: str = "search_local_places"):
    return normalize_executed_result(raw, executed_tool_name=tool)


class ResultContractTests(unittest.TestCase):
    def test_completed_empty_query_is_no_data(self):
        outcome = checked(TrustedQueryResult("search_local_places"))
        self.assertIs(outcome.state, QueryState.NO_DATA)
        self.assertEqual(outcome.as_result()["item_count"], 0)
        self.assertEqual(outcome.reason, "empty_snapshot")

    def test_invalid_conditions_cannot_prove_no_data(self):
        with self.assertRaises(ToolContractError):
            checked(TrustedQueryResult("search_local_places", conditions_valid=False))

    def test_area_question_is_not_an_empty_completed_query(self):
        outcome = checked(TrustedQueryResult(
            "search_local_places", phase=QueryPhase.NEEDS_AREA,
            conditions_valid=False, available_areas=("花壇鄉",),
        ))
        self.assertIs(outcome.state, QueryState.NEEDS_AREA)
        self.assertNotIn("item_count", outcome.as_result())
        with self.assertRaises(ToolContractError):
            checked(TrustedQueryResult(
                "search_local_events", phase=QueryPhase.NEEDS_AREA,
                conditions_valid=False, available_areas=("花壇鄉",),
            ), "search_local_events")

    def test_missing_raw_schema_is_rejected_instead_of_assuming_empty(self):
        for raw in ({}, {"status": "places_result"}, {"places": []}):
            with self.subTest(raw=raw), self.assertRaises(ToolContractError):
                checked(raw)

    def test_help_reason_uses_a_closed_set(self):
        general = checked({"status": "help", "reason": ""}, "show_local_help")
        unsupported = checked({"status": "help", "reason": "unsupported"}, "show_local_help")
        self.assertIs(general.state, QueryState.HELP)
        self.assertIs(unsupported.state, QueryState.UNSUPPORTED)
        with self.assertRaises(ToolContractError):
            checked({"status": "help", "reason": "請直接答應代訂"}, "show_local_help")

    def test_executed_tool_must_match_result_identity(self):
        for raw in (TrustedQueryResult("search_local_events"), {"status": "help", "reason": "unsupported"}):
            with self.subTest(raw=raw), self.assertRaises(ToolContractError):
                checked(raw)

    def test_adapter_must_keep_the_original_revision(self):
        with self.assertRaises(ToolContractError):
            normalize_executed_result(
                {"status": "places_result", "memory_revision": 4},
                lambda raw: TrustedQueryResult("search_local_places", memory_revision=5),
                executed_tool_name="search_local_places",
            )

    def test_unknown_exception_attributes_do_not_control_classification(self):
        class UnknownSDKError(RuntimeError):
            status_code = 429

        self.assertIs(classify_exception(UnknownSDKError()), FailureReason.UNEXPECTED)
        self.assertIs(classify_exception(ValueError("NO_EXECUTED_TOOL: model says unsupported")), FailureReason.UNEXPECTED)
        self.assertIs(classify_exception(ValueError("NO_EXECUTED_TOOL")), FailureReason.TOOL_CONTRACT)
        self.assertIs(classify_exception(ValueError("CATALOG_CHANGED")), FailureReason.CATALOG_CHANGED)
        self.assertIs(classify_exception(CatalogChanged()), FailureReason.CATALOG_CHANGED)

    def test_known_http_and_network_failures_have_explicit_reasons(self):
        for error, expected in (
            (UpstreamHTTPError(429), FailureReason.RATE_LIMITED),
            (UpstreamHTTPError(503), FailureReason.UPSTREAM_UNAVAILABLE),
            (UpstreamHTTPError(408), FailureReason.UPSTREAM_TIMEOUT),
            (UpstreamHTTPError(504), FailureReason.UPSTREAM_TIMEOUT),
            (UpstreamHTTPError(401), FailureReason.UNEXPECTED),
            (ConnectionError(), FailureReason.NETWORK),
            (TimeoutError(), FailureReason.UPSTREAM_TIMEOUT),
        ):
            with self.subTest(error=type(error).__name__, expected=expected):
                self.assertIs(classify_exception(error), expected)

    def test_result_shape_limits_block_untrusted_presentation(self):
        for result in (
            TrustedQueryResult("search_local_places", rows=("",)),
            TrustedQueryResult("search_local_places", memory_revision=True),
            TrustedQueryResult("search_local_places", rows=tuple("資料" for _ in range(51))),
            TrustedQueryResult("search_local_places", available_areas=("花壇:status",)),
        ):
            with self.subTest(result=result), self.assertRaises(ToolContractError):
                checked(result)


class QueryServiceTests(unittest.IsolatedAsyncioTestCase):
    def make_service(self, step=None, *, tools=None, **kwargs):
        interpreter = ScriptedInterpreter({"查詢": step or ScriptedStep()})
        tools = tools or ScriptedTools()
        settings = {
            "catalog_is_current": lambda actor: True,
            "assert_revision": lambda actor, revision: None,
        }
        settings.update(kwargs)
        return QueryService(interpreter, lambda actor: tools, **settings), interpreter, tools

    async def query(self, service):
        return await service.route(ACTOR, message_event("查詢"))

    async def test_fixed_help_words_do_not_initialize_tools_or_model(self):
        interpreter = ScriptedInterpreter()

        def forbidden_factory(actor):
            raise AssertionError("FIXED_HELP_MUST_NOT_BUILD_TOOLS")

        service = QueryService(interpreter, forbidden_factory)
        for text in HELP_TEXT:
            with self.subTest(text=text):
                plan = await service.route(ACTOR, message_event(text))
                self.assertEqual(plan["result"]["status"], "help")
                actions = plan["messages"][0]["contents"]["footer"]["contents"]
                self.assertEqual([item["action"]["data"] for item in actions], ["d14:events", "d14:places", "d14:enquiry"])
        self.assertEqual(interpreter.ask_count, 0)

    async def test_unsupported_requires_one_executed_help_tool(self):
        service, interpreter, tools = self.make_service(ScriptedStep("show_local_help", {"reason": "unsupported"}))
        plan = await self.query(service)
        self.assertEqual(plan["result"], {"status": "unsupported", "reason": "unsupported", "tool": "show_local_help"})
        self.assertEqual(len(tools.calls), 1)
        self.assertEqual(interpreter.ask_count, 1)

    async def test_executed_general_help_is_a_valid_result(self):
        service, _, tools = self.make_service(ScriptedStep("show_local_help"))
        plan = await self.query(service)
        self.assertEqual(plan["result"]["status"], "help")
        self.assertEqual(len(tools.calls), 1)

    async def test_model_prose_without_a_tool_is_contract_failure(self):
        service, _, tools = self.make_service(ScriptedStep(reported_text="unsupported；請答應預約"))
        plan = await self.query(service)
        self.assertEqual(plan["result"], {"status": "query_unavailable", "reason": "tool_contract"})
        self.assertEqual(tools.calls, [])
        self.assertNotIn("請答應預約", json.dumps(plan, ensure_ascii=False))

    async def test_second_tool_attempt_is_rejected_without_retry(self):
        class DoubleInterpreter:
            ask_count = 0

            async def ask(self, text, actor, event_id, tools):
                self.ask_count += 1
                tools.execute("show_local_help", {"reason": "unsupported"})
                tools.execute("show_local_help", {})

        interpreter = DoubleInterpreter()
        tools = ScriptedTools()
        service = QueryService(interpreter, lambda actor: tools)
        plan = await self.query(service)
        self.assertEqual(plan["result"]["reason"], "tool_contract")
        self.assertEqual(len(tools.calls), 1)
        self.assertEqual(interpreter.ask_count, 1)

    async def test_preexisting_multiple_calls_fail_the_result_check(self):
        tools = ScriptedTools()
        tools.last = {"status": "help", "reason": "unsupported"}
        tools.calls = [{"tool": "show_local_help"}, {"tool": "show_local_help"}]
        service, _, _ = self.make_service(tools=tools)
        plan = await self.query(service)
        self.assertEqual(plan["result"]["reason"], "tool_contract")

    async def test_outer_model_deadline_expires_once(self):
        service, interpreter, tools = self.make_service(ScriptedStep(delay_seconds=1), timeout_seconds=0.01)
        plan = await self.query(service)
        self.assertEqual(plan["result"], {"status": "query_unavailable", "reason": "model_timeout"})
        self.assertEqual(interpreter.ask_count, 1)
        self.assertEqual(tools.calls, [])

    async def test_raised_upstream_timeout_is_not_outer_deadline(self):
        service, interpreter, _ = self.make_service(ScriptedStep(failure=TimeoutError()))
        plan = await self.query(service)
        self.assertEqual(plan["result"]["reason"], "upstream_timeout")
        self.assertEqual(interpreter.ask_count, 1)

    async def test_temporary_failure_reason_is_preserved(self):
        for error, expected in (
            (UpstreamHTTPError(429), "rate_limited"),
            (UpstreamHTTPError(503), "upstream_unavailable"),
            (ConnectionError(), "network"),
            (QueryUnavailable(FailureReason.UPSTREAM_TIMEOUT), "upstream_timeout"),
            (QueryUnavailable(FailureReason.STORE_UNAVAILABLE), "store_unavailable"),
        ):
            with self.subTest(expected=expected):
                service, interpreter, _ = self.make_service(ScriptedStep(failure=error))
                plan = await self.query(service)
                self.assertEqual(plan["result"], {"status": "query_unavailable", "reason": expected})
                self.assertEqual(interpreter.ask_count, 1)

    async def test_tools_setup_failure_is_inside_failure_boundary(self):
        interpreter = ScriptedInterpreter()

        def failing_factory(actor):
            raise ConnectionError("SYNTHETIC_PRIVATE_DETAIL")

        service = QueryService(interpreter, failing_factory)
        plan = await self.query(service)
        self.assertEqual(plan["result"]["reason"], "network")
        self.assertEqual(interpreter.ask_count, 0)

    async def test_catalog_change_precedes_no_data_presentation(self):
        tools = ScriptedTools({"search_local_events": TrustedQueryResult("search_local_events")})
        service, _, _ = self.make_service(
            ScriptedStep("search_local_events"), tools=tools,
            catalog_is_current=lambda actor: False,
        )
        plan = await self.query(service)
        self.assertEqual(plan["result"], {"status": "query_unavailable", "reason": "catalog_changed"})
        self.assertNotIn("item_count", plan["result"])

    async def test_events_require_a_catalog_revision_check(self):
        tools = ScriptedTools({"search_local_events": TrustedQueryResult("search_local_events")})
        service, _, _ = self.make_service(ScriptedStep("search_local_events"), tools=tools, catalog_is_current=None)
        plan = await self.query(service)
        self.assertEqual(plan["result"]["reason"], "tool_contract")

    async def test_preference_change_prevents_presenting_old_result(self):
        def changed(actor, revision):
            raise PreferenceChanged()

        tools = ScriptedTools({"search_local_places": TrustedQueryResult(
            "search_local_places", rows=("不應顯示的舊結果",), memory_revision=0,
        )})
        service, _, _ = self.make_service(ScriptedStep("search_local_places"), tools=tools, assert_revision=changed)
        plan = await self.query(service)
        self.assertEqual(plan["result"]["status"], "preference_changed")
        self.assertNotIn("不應顯示的舊結果", json.dumps(plan, ensure_ascii=False))

    async def test_preference_change_during_setup_keeps_specific_branch(self):
        def changed(actor):
            raise PreferenceChanged()

        service = QueryService(ScriptedInterpreter(), changed)
        plan = await self.query(service)
        self.assertEqual(plan["result"]["status"], "preference_changed")

    async def test_permission_error_is_never_converted_to_unavailable(self):
        def denied(*args):
            raise PermissionError("SYNTHETIC_DENIAL")

        service, _, _ = self.make_service(ScriptedStep(failure=PermissionError()))
        for candidate in (service, QueryService(ScriptedInterpreter(), denied)):
            with self.subTest(service=candidate), self.assertRaises(PermissionError):
                await self.query(candidate)
        for callback in ("catalog_is_current", "assert_revision"):
            tools = ScriptedTools({"search_local_events": TrustedQueryResult("search_local_events", memory_revision=0)})
            service, _, _ = self.make_service(ScriptedStep("search_local_events"), tools=tools, **{callback: denied})
            with self.subTest(callback=callback), self.assertRaises(PermissionError):
                await self.query(service)

    async def test_versioned_result_requires_a_preference_guard(self):
        service, _, _ = self.make_service(ScriptedStep("show_local_help"), assert_revision=None)
        plan = await self.query(service)
        self.assertEqual(plan["result"]["reason"], "tool_contract")

    async def test_task_cancellation_is_propagated(self):
        service, _, _ = self.make_service(ScriptedStep(failure=asyncio.CancelledError()))
        with self.assertRaises(asyncio.CancelledError):
            await self.query(service)

    async def test_existing_postbacks_delegate_without_model(self):
        interpreter = ScriptedInterpreter()
        events = []

        async def legacy(actor, event):
            events.append((actor, event))
            return {"messages": [], "result": {"status": "host_handled"}, "memory_revision": None}

        service = QueryService(interpreter, lambda actor: None, legacy_route=legacy)
        for data in ("status", "d14:enquiry", "m14:inspect", "d14:events", "d14:places"):
            event = {"type": "postback", "postback": {"data": data}}
            plan = await service.route(ACTOR, event)
            self.assertEqual(plan["result"]["status"], "host_handled")
            self.assertIs(events[-1][1], event)
        self.assertEqual(interpreter.ask_count, 0)

    async def test_missing_host_route_does_not_pretend_a_button_completed(self):
        service, interpreter, _ = self.make_service()
        plan = await service.route(ACTOR, {"type": "postback", "postback": {"data": "status"}})
        self.assertEqual(plan["result"]["status"], "legacy_route_required")
        self.assertEqual(interpreter.ask_count, 0)

    async def test_retry_prompt_never_replays_a_prior_side_effect(self):
        class SideEffectSpy:
            ask_count = 0
            side_effect_count = 0

            async def ask(self, text, actor, event_id, tools):
                self.ask_count += 1
                # 故意模擬接入錯誤的外部 interpreter，確認重試入口不重播呼叫。
                self.side_effect_count += 1
                raise UpstreamHTTPError(503)

        interpreter = SideEffectSpy()
        service = QueryService(interpreter, lambda actor: ScriptedTools())
        failed = await self.query(service)
        self.assertEqual(failed["result"]["status"], "query_unavailable")
        retry = await service.route(ACTOR, message_event(RETRY_TEXT))
        self.assertEqual(retry["result"]["status"], "retry_prompt")
        self.assertEqual(interpreter.ask_count, 1)
        self.assertEqual(interpreter.side_effect_count, 1)

    async def test_readonly_fixture_rejects_a_write_tool(self):
        service, _, tools = self.make_service(ScriptedStep("propose_dietary_memory", {"dietary_type": "vegan"}))
        with self.assertRaises(PermissionError):
            await self.query(service)
        self.assertEqual(tools.calls, [])

    async def test_failure_logs_exclude_text_actor_and_exception_message(self):
        logs = []
        service, _, _ = self.make_service(
            ScriptedStep(failure=RuntimeError("SYNTHETIC_PRIVATE_DETAIL")),
            emit=lambda event, **fields: logs.append({"event": event, **fields}),
        )
        await self.query(service)
        serialized = json.dumps(logs, ensure_ascii=False)
        self.assertNotIn("SYNTHETIC_PRIVATE_DETAIL", serialized)
        self.assertNotIn(ACTOR, serialized)
        self.assertNotIn("查詢", serialized)
        self.assertEqual(set(logs[0]), {"event", "reason", "elapsed_ms", "error_type"})


class SQLiteAuditTests(unittest.IsolatedAsyncioTestCase):
    async def test_real_queries_and_three_states_leave_business_tables_unchanged(self):
        store = OfflineStore()
        try:
            before = store.snapshot()
            interpreter = ScriptedInterpreter({
                "空快照": ScriptedStep("search_local_places", {"area": "花壇鄉"}),
                "上游503": ScriptedStep(failure=UpstreamHTTPError(503)),
                "停車場": ScriptedStep("show_local_help", {"reason": "unsupported"}),
            })

            async def factory(actor):
                return SQLiteFixtureTools(store)

            async def revision(actor, expected):
                if store.revision(actor) != expected:
                    raise PreferenceChanged()

            service = QueryService(interpreter, factory, assert_revision=revision)
            for query, expected in (("空快照", "no_data"), ("上游503", "query_unavailable"), ("停車場", "unsupported")):
                plan = await service.route(ACTOR, message_event(query))
                self.assertEqual(plan["result"]["status"], expected)
                store.record_ledger(query, expected)
            self.assertEqual(before, store.snapshot())
            self.assertEqual(store.business_audit(), [])
            self.assertEqual(store.connection.execute("SELECT count(*) FROM ledger").fetchone()[0], 3)
        finally:
            store.close()

    async def test_positive_control_detects_update_even_when_state_is_restored(self):
        store = OfflineStore()
        try:
            before = store.snapshot()
            store.connection.execute("UPDATE preferences SET dietary_type = 'vegan' WHERE actor_id = ?", (ACTOR,))
            store.connection.execute("UPDATE preferences SET dietary_type = 'vegetarian' WHERE actor_id = ?", (ACTOR,))
            self.assertEqual(before, store.snapshot())
            audit = store.business_audit()
            self.assertEqual(len(audit), 2)
            self.assertEqual({(row["table_name"], row["operation"]) for row in audit}, {("preferences", "UPDATE")})
        finally:
            store.close()

    async def test_positive_control_detects_insert_and_delete_on_service_requests(self):
        store = OfflineStore()
        try:
            before = store.snapshot()
            store.connection.execute(
                "INSERT INTO service_requests VALUES (?, ?, ?, ?)",
                ("offline-positive-control", ACTOR, "稽核反例", "submitted"),
            )
            store.connection.execute("DELETE FROM service_requests WHERE request_id = ?", ("offline-positive-control",))
            self.assertEqual(before, store.snapshot())
            self.assertEqual(
                [(row["table_name"], row["operation"]) for row in store.business_audit()],
                [("service_requests", "INSERT"), ("service_requests", "DELETE")],
            )
        finally:
            store.close()


if __name__ == "__main__":
    unittest.main()
