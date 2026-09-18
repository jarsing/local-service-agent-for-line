"""LOCAL Day 4：驗簽、限定收件與單一背景工作；不建業務案件。"""
from __future__ import annotations

import base64
import hashlib
import hmac
import json
import queue
import threading
import time
import uuid
from dataclasses import dataclass, field
from typing import Callable, Any

MAX_BODY_BYTES = 65_536
MAX_EVENTS = 20
MAX_SEEN = 256
MAX_MODEL_CALLS = 3
MAX_REPLY_CALLS = 8
MAX_JOB_AGE_SECONDS = 35
PING_COMMAND = "LOCAL ping"
DEMO_COMMAND = "LOCAL 測試"
PING_TEXT = "LOCAL 測試入口已連通。這次沒有呼叫 Gemini，也沒有建立服務請求。"
PREFIX = "【合成案例演練，非真實案件】\n"
FALLBACK = PREFIX + "這次暫時無法產生可用的說明；沒有查詢、送出或安排任何服務。"


@dataclass(frozen=True, repr=False)
class Settings:
    channel_secret: str = field(repr=False)
    channel_access_token: str = field(repr=False)
    test_user_id: str = field(repr=False)
    gemini_key: str = field(repr=False)
    model: str = "gemini-3.8-flash"


def valid_signature(raw_body: bytes, signature: str | None, secret: str) -> bool:
    """核對原始位元組，不先解析或重新序列化 JSON。"""
    if not secret or not isinstance(signature, str) or len(signature) != 44:
        return False
    try:
        supplied = base64.b64decode(signature, validate=True)
    except (ValueError, TypeError):
        return False
    expected = hmac.new(secret.encode("utf-8"), raw_body, hashlib.sha256).digest()
    return len(supplied) == 32 and hmac.compare_digest(expected, supplied)


def strict_json(raw_body: bytes) -> dict:
    def pairs(items):
        result = {}
        for key, value in items:
            if key in result:
                raise ValueError("重複 JSON 欄位")
            result[key] = value
        return result
    def reject_constant(value):
        raise ValueError("非標準 JSON 常數")
    value = json.loads(raw_body.decode("utf-8"), object_pairs_hook=pairs,
                       parse_constant=reject_constant)
    if not isinstance(value, dict):
        raise ValueError("最外層必須是物件")
    return value


def safe_error(exc: Exception) -> dict:
    code = getattr(exc, "code", None)
    return {"type": type(exc).__name__,
            "http_code": code if isinstance(code, int) and not isinstance(code, bool) else None}


@dataclass(repr=False)
class Job:
    trace: str
    command: str
    reply_token: str = field(repr=False)
    received_at: float


class Engine:
    """測試用記憶體佇列；HTTP 收件與訊息回覆分離，但不保證崩潰後恢復。"""
    def __init__(self, settings: Settings, generate: Callable[[], dict],
                 reply: Callable[[str, str], dict], record: Callable[..., None],
                 *, clock=time.monotonic):
        self.settings = settings
        self.generate = generate
        self.reply = reply
        self.record = record
        self.clock = clock
        self.pending: queue.Queue[Job] = queue.Queue(maxsize=1)
        self.lock = threading.RLock()
        self.seen: set[bytes] = set()
        self.model_calls = 0
        self.reply_calls = 0
        self.stop_event = threading.Event()
        self.thread: threading.Thread | None = None

    def start(self):
        self.thread = threading.Thread(target=self._worker, name="local-day04", daemon=True)
        self.thread.start()

    def close(self):
        self.stop_event.set()
        if self.thread:
            self.thread.join(timeout=30)
        self.record("SESSION_STOPPED", pending_jobs=self.pending.qsize())

    def _worker(self):
        while not self.stop_event.is_set():
            self.process_one(timeout=0.2)

    def receive(self, raw: bytes, signature: str | None) -> int:
        # 驗簽前只做長度檢查；不記錄原始本文、簽章或身分。
        if len(raw) > MAX_BODY_BYTES:
            self.record("BODY_TOO_LARGE")
            return 413
        if not valid_signature(raw, signature, self.settings.channel_secret):
            self.record("SIGNATURE_REJECTED")
            return 401
        try:
            data = strict_json(raw)
            events = data.get("events")
            if not isinstance(events, list) or len(events) > MAX_EVENTS:
                raise ValueError("不接受的事件陣列")
        except (ValueError, UnicodeError, RecursionError):
            self.record("JSON_REJECTED")
            return 400
        if not events:
            self.record("WEBHOOK_VERIFIED_EMPTY")
            return 200
        busy = False
        for event in events:
            if not isinstance(event, dict):
                self.record("EVENT_IGNORED", reason="invalid_event")
                continue
            source, message = event.get("source"), event.get("message")
            if (event.get("type") != "message" or event.get("mode") != "active"
                    or not isinstance(source, dict) or source.get("type") != "user"
                    or source.get("userId") != self.settings.test_user_id
                    or not isinstance(message, dict) or message.get("type") != "text"):
                self.record("EVENT_IGNORED", reason="outside_test_scope")
                continue
            text = message.get("text")
            if text not in (PING_COMMAND, DEMO_COMMAND):
                self.record("EVENT_IGNORED", reason="unknown_command")
                continue
            event_id, token = event.get("webhookEventId"), event.get("replyToken")
            if (not isinstance(event_id, str) or not event_id or len(event_id) > 256
                    or not isinstance(token, str) or not token or len(token) > 256):
                self.record("EVENT_IGNORED", reason="missing_event_id_or_token")
                continue
            key = hashlib.sha256(event_id.encode()).digest()
            with self.lock:
                if key in self.seen:
                    self.record("DUPLICATE_SKIPPED")
                    continue
                if len(self.seen) >= MAX_SEEN:
                    self.record("SESSION_LIMIT_REACHED")
                    continue
                job = Job(uuid.uuid4().hex[:12], text, token, self.clock())
                try:
                    self.pending.put_nowait(job)
                except queue.Full:
                    busy = True
                    self.record("QUEUE_FULL")
                    continue
                self.seen.add(key)
                self.record("ACCEPTED_IN_MEMORY", trace=job.trace,
                            command="ping" if text == PING_COMMAND else "synthetic_demo")
        # 某事件未入列時回 503；已入列的事件在本行程存活期間會去重。
        # 本文不承諾 LINE 一定重送，也不宣稱這是可靠的持久化收件。
        return 503 if busy else 200

    def process_one(self, timeout: float = 0) -> bool:
        try:
            job = self.pending.get(timeout=timeout)
        except queue.Empty:
            return False
        try:
            self._process(job)
        except Exception as exc:
            self.record("WORKER_ERROR", trace=job.trace, error=safe_error(exc))
        finally:
            self.pending.task_done()
        return True

    def _process(self, job: Job):
        if self.clock() - job.received_at > MAX_JOB_AGE_SECONDS:
            self.record("LOCAL_REPLY_WINDOW_EXCEEDED", trace=job.trace)
            return
        if self.reply_calls >= MAX_REPLY_CALLS:
            self.record("REPLY_BUDGET_STOP", trace=job.trace)
            return
        kind = "ping"
        text = PING_TEXT
        if job.command == DEMO_COMMAND:
            if self.model_calls >= MAX_MODEL_CALLS:
                self.record("MODEL_BUDGET_STOP", trace=job.trace)
                return
            self.model_calls += 1
            self.record("MODEL_STARTED", trace=job.trace, invocation=self.model_calls)
            kind, text = "fallback", FALLBACK
            try:
                result = self.generate()
                candidate = result.get("text")
                if (isinstance(candidate, str) and candidate.strip()
                        and result.get("finish_reason") == "STOP"
                        and not result.get("blocked")
                        and not result.get("unexpected_non_text")
                        and len(candidate.encode("utf-16-le")) // 2 <= 3500):
                    kind, text = "gemini_text", PREFIX + candidate
                    self.record("MODEL_TEXT_RECEIVED", trace=job.trace,
                                response=result, semantic_review="not_recorded")
                else:
                    self.record("MODEL_NEEDS_REVIEW", trace=job.trace)
            except Exception as exc:
                self.record("MODEL_ERROR", trace=job.trace, error=safe_error(exc))
        if self.clock() - job.received_at > MAX_JOB_AGE_SECONDS:
            self.record("LOCAL_REPLY_WINDOW_EXCEEDED", trace=job.trace)
            return
        self.reply_calls += 1
        try:
            result = self.reply(job.reply_token, text)
            code = result.get("http_code")
            self.record("LINE_REPLY_ACCEPTED" if code == 200 else "LINE_REPLY_HTTP_ERROR",
                        trace=job.trace, reply_kind=kind, http_code=code,
                        phone_display="not_observed_by_server")
        except Exception as exc:
            # 結果未知，不重用 token、不改 push、不再呼叫模型。
            self.record("LINE_REPLY_UNKNOWN", trace=job.trace, reply_kind=kind,
                        error=safe_error(exc), phone_display="not_observed_by_server")
