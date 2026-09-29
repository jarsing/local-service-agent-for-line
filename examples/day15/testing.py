"""Explicit scripted orchestration; never used as Gemini validation."""
from starlette.concurrency import run_in_threadpool
from .context_store import ContextJournal, project_result
from .session_budget import BudgetSessionManager, ByteCounter, MODEL_ID


from .fixtures import FIXTURE_ENVELOPE


class ScriptedBudgetInterpreter:
    mode = "SCRIPTED_CONTEXT_NOT_GEMINI_OR_ADK"

    def __init__(self, mapping=None):
        self.mapping = mapping or {}
        self.reports = []
        self.limit = 9000

    async def ask(self, question, actor, event_id, tools):
        journal = ContextJournal(tools.memory)
        snapshot = await run_in_threadpool(journal.read, actor)
        prepared = await BudgetSessionManager(2, self.limit, "utf8_bytes").prepare(
            snapshot.window, question, FIXTURE_ENVELOPE, ByteCounter()
        )
        name, args = self.mapping.get(question, (
            "search_local_places", {"area": "", "dietary_type": "", "keyword": ""}
        ))
        args = dict(args)
        if not args.get("area") and name == "search_local_places":
            # Explicit deterministic substitute for reference resolution, not NLU.
            area = next((t.area for t in reversed(snapshot.window.turns) if t.area),
                        snapshot.window.summary.area)
            args["area"] = area
        result = await run_in_threadpool(tools.execute, name, args)
        if result.get("status") not in (
            "memory_proposal_requested", "memory_management_requested"
        ):
            await run_in_threadpool(journal.append, actor, snapshot, event_id,
                                    project_result(result))
        report = {
            "mode": self.mode, "model_calls": 0,
            "input_bytes": prepared.measured_units, "input_tokens": None,
            "model_latency_seconds": None, "tool_events": tools.calls,
            "result": result, "context": prepared.window.as_dict(),
        }
        self.reports.append(report)
        return report
