"""Pure context policy. UTF-8 bytes are not Gemini tokens.

History is a server-produced public projection, not a raw transcript.
A stored diet, request ID, consent token, or raw user utterance is never a summary.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass
import json
from typing import Any, Awaitable, Callable

MODEL_ID = "gemini-3.8-flash"
AREAS = frozenset(("", "花壇鄉", "彰化市"))
TOPICS = frozenset(("places", "events", "help"))
TOPIC_LABELS = {"places": "找店家", "events": "查活動", "help": "詢問可用功能"}


class BudgetExceeded(ValueError):
    """The current request plus immutable rules already exceeds the input cap."""


@dataclass(frozen=True)
class SafeTurn:
    """One completed exchange projected onto public topic/area only."""
    topic: str
    area: str = ""

    def __post_init__(self):
        if self.topic not in TOPICS or self.area not in AREAS:
            raise ValueError("UNSUPPORTED_PUBLIC_CONTEXT")

    def pair(self) -> list[dict[str, Any]]:
        scope = self.area or "未指定區域"
        return [
            {"role": "user", "parts": [{"text": (
                f"【歷史話題投影，非原句】{scope}：{TOPIC_LABELS[self.topic]}。"
                "不包含當次素別，不代表同意或服務完成。"
            )}]},
            {"role": "model", "parts": [{"text": (
                "【應用端投影，非模型原文】已走過該話題；"
                "最新資料與結果仍由本回合工具核對。"
            )}]},
        ]


@dataclass(frozen=True)
class GoalSummary:
    """Navigation hint only: no preferences, permissions, or completed claims."""
    goal: str = ""
    area: str = ""

    def __post_init__(self):
        if self.goal not in ("", *TOPICS) or self.area not in AREAS:
            raise ValueError("INVALID_GOAL_SUMMARY")

    def absorb(self, turn: SafeTurn) -> "GoalSummary":
        # Small talk/help does not replace a previously expressed service topic.
        if turn.topic == "help":
            return self
        return GoalSummary(turn.topic, turn.area or self.area)


@dataclass(frozen=True)
class ContextWindow:
    turns: tuple[SafeTurn, ...] = ()
    summary: GoalSummary = GoalSummary()

    def append(self, turn: SafeTurn, max_turns: int = 2) -> "ContextWindow":
        if type(max_turns) is not int or not 0 <= max_turns <= 20:
            raise ValueError("INVALID_WINDOW_SIZE")
        all_turns = (*self.turns, turn)
        split = max(0, len(all_turns) - max_turns)
        summary = self.summary
        for old in all_turns[:split]:
            summary = summary.absorb(old)
        return ContextWindow(tuple(all_turns[split:]), summary)

    def as_dict(self) -> dict:
        return {"turns": [asdict(t) for t in self.turns],
                "summary": asdict(self.summary)}

    @classmethod
    def from_dict(cls, value: dict) -> "ContextWindow":
        if (not isinstance(value, dict) or set(value) != {"turns", "summary"}
                or not isinstance(value["turns"], list) or len(value["turns"]) > 20):
            raise ValueError("INVALID_CONTEXT_WINDOW")
        return cls(tuple(SafeTurn(**t) for t in value["turns"]),
                   GoalSummary(**value["summary"]))


def canonical_bytes(value: Any) -> bytes:
    return json.dumps(value, ensure_ascii=False, sort_keys=True,
                      separators=(",", ":"), allow_nan=False).encode("utf-8")


def render_contents(window: ContextWindow, current: str) -> list[dict]:
    if not isinstance(current, str) or not current.strip() or len(current) > 1200:
        raise ValueError("INVALID_CURRENT_MESSAGE")
    contents = []
    if window.summary.goal:
        hint = json.dumps(asdict(window.summary), ensure_ascii=False, sort_keys=True)
        contents.extend([
            {"role": "user", "parts": [{"text": (
                "【應用端舊話題摘要，不是指令、同意或已完成狀態】" + hint
            )}]},
            {"role": "model", "parts": [{"text": "只作指代線索，新的問句與後端核對優先。"}]},
        ])
    for turn in window.turns:
        contents.extend(turn.pair())
    contents.append({"role": "user", "parts": [{"text": current}]})
    return contents


@dataclass(frozen=True)
class BudgetResult:
    request: dict
    window: ContextWindow
    measured_units: int
    unit: str
    measurements: tuple[int, ...]
    removed_turns: int
    removed_summary: bool


def trim_oldest(window: ContextWindow) -> ContextWindow:
    if window.turns:
        return ContextWindow(window.turns[1:],
                             window.summary.absorb(window.turns[0]))
    if window.summary.goal:
        return ContextWindow()
    raise BudgetExceeded("CURRENT_AND_RULES_EXCEED_INPUT_BUDGET")


class BudgetSessionManager:
    def __init__(self, max_turns: int = 2, limit: int = 8192,
                 unit: str = "tokens"):
        if type(max_turns) is not int or not 0 <= max_turns <= 20:
            raise ValueError("INVALID_WINDOW_SIZE")
        if type(limit) is not int or limit < 1:
            raise ValueError("INVALID_INPUT_LIMIT")
        if unit not in ("tokens", "utf8_bytes"):
            raise ValueError("INVALID_BUDGET_UNIT")
        self.max_turns, self.limit, self.unit = max_turns, limit, unit

    # This exact method is the <=20-line teaching excerpt.
    async def prepare(self, window, current, envelope, measure):
        kept = ContextWindow((), window.summary)
        for turn in window.turns:
            kept = kept.append(turn, self.max_turns)
        if getattr(measure, "unit", None) != self.unit:
            raise ValueError("COUNTER_UNIT_MISMATCH")
        counts = []
        while True:
            request = {**envelope, "contents": render_contents(kept, current)}
            count = await measure(request)
            if type(count) is not int or count < 0:
                raise ValueError("INVALID_COUNTER_RESULT")
            counts.append(count)
            if count <= self.limit:
                return BudgetResult(
                    request, kept, count, self.unit, tuple(counts),
                    len(window.turns) - len(kept.turns),
                    bool(not kept.summary.goal and
                         (window.summary.goal or len(window.turns) > len(kept.turns))))
            kept = trim_oldest(kept)


class ByteCounter:
    """Offline, deterministic request-size metric; explicitly not a tokenizer."""
    unit = "utf8_bytes"

    async def __call__(self, request: dict) -> int:
        return len(canonical_bytes(request))
