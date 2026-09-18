"""離線替身與 ASGI 路由測試；不代表真實 LINE／Gemini 已串接成功。"""
from __future__ import annotations

import base64
import hashlib
import hmac
import json
from pathlib import Path
import tempfile
import time
import unittest

import httpx
from fastapi.testclient import TestClient

from core import Engine, Settings, valid_signature, strict_json, MAX_BODY_BYTES, FALLBACK, PREFIX
from app import create_app, Recorder
from adapters import make_line_reply, load_settings

SETTINGS = Settings("test-secret-only", "test-access-only", "U" + "1" * 32, "test-gemini-only")


def sign(body: bytes, secret=SETTINGS.channel_secret):
    return base64.b64encode(hmac.new(secret.encode(), body, hashlib.sha256).digest()).decode()


def payload(text="LOCAL 測試", event_id="test-event-1", **changes):
    event = {"type": "message", "mode": "active", "webhookEventId": event_id,
             "replyToken": "test-reply-token-only", "source": {"type": "user", "userId": SETTINGS.test_user_id},
             "message": {"type": "text", "text": text}}
    event.update(changes)
    return json.dumps({"destination": "synthetic-bot", "events": [event]}, ensure_ascii=False).encode()


class FakeModel:
    def __init__(self, *, error=None, result=None):
        self.calls = 0
        self.error = error
        self.result = result or {"text": "合成案例目前仍待核對，無法確認後端結果。", "finish_reason": "STOP",
                                 "model_version": "OFFLINE_TEST_DOUBLE", "usage": {}, "blocked": None,
                                 "unexpected_non_text": False}
    def __call__(self):
        self.calls += 1
        if self.error:
            raise self.error
        return self.result


class FakeReply:
    def __init__(self, *, error=None, code=200):
        self.calls = []
        self.error, self.code = error, code
    def __call__(self, token, text):
        self.calls.append((token, text))
        if self.error:
            raise self.error
        return {"http_code": self.code}


class CoreTests(unittest.TestCase):
    def setUp(self):
        self.events = []
        self.model, self.reply = FakeModel(), FakeReply()
        self.engine = Engine(SETTINGS, self.model, self.reply,
                             lambda status, **kw: self.events.append({"status": status, **kw}))
    def send(self, raw=None):
        raw = payload() if raw is None else raw
        return self.engine.receive(raw, sign(raw))
    def statuses(self):
        return [e["status"] for e in self.events]

    def test_official_public_signature_vector(self):
        # LINE 官方公開範例，不是真實測試頻道的秘密。
        body = b'{"destination":"U8e742f61d673b39c7fff3cecb7536ef0","events":[]}'
        self.assertTrue(valid_signature(body, "GhRKmvmHys4Pi8DxkF4+EayaH0OqtJtaZxgTD9fMDLs=",
                                        "8c570fa6dd201bb328f1c1eac23a96d8"))
    def test_valid_unicode_signature(self):
        raw = payload("LOCAL 測試")
        self.assertTrue(valid_signature(raw, sign(raw), SETTINGS.channel_secret))
    def test_missing_signature_does_not_parse(self):
        self.assertEqual(self.engine.receive(b"not-json", None), 401)
        self.assertEqual(self.model.calls, 0)
        self.assertEqual(self.reply.calls, [])
    def test_wrong_secret_rejected(self):
        raw = payload()
        self.assertEqual(self.engine.receive(raw, sign(raw, "other")), 401)
    def test_changed_space_rejected(self):
        raw = payload()
        self.assertEqual(self.engine.receive(raw + b" ", sign(raw)), 401)
    def test_reformatted_json_rejected(self):
        raw = payload()
        pretty = json.dumps(json.loads(raw), indent=2, ensure_ascii=False).encode()
        self.assertEqual(self.engine.receive(pretty, sign(raw)), 401)
    def test_invalid_base64_rejected(self):
        self.assertFalse(valid_signature(b"{}", "!" * 44, SETTINGS.channel_secret))
    def test_empty_secret_rejected(self):
        self.assertFalse(valid_signature(b"{}", sign(b"{}"), ""))
    def test_empty_events_200_no_side_effects(self):
        self.assertEqual(self.send(b'{"destination":"test","events":[]}'), 200)
        self.assertEqual(self.model.calls, 0)
        self.assertEqual(self.reply.calls, [])
        self.assertIn("WEBHOOK_VERIFIED_EMPTY", self.statuses())
    def test_signed_bad_json_400(self):
        self.assertEqual(self.send(b"bad-json"), 400)
    def test_duplicate_json_keys_rejected(self):
        self.assertEqual(self.send(b'{"events":[],"events":[]}'), 400)
    def test_nan_json_rejected(self):
        self.assertEqual(self.send(b'{"events":[],"x":NaN}'), 400)
    def test_wrong_events_type_rejected(self):
        self.assertEqual(self.send(b'{"events":{}}'), 400)
    def test_too_many_events_rejected(self):
        self.assertEqual(self.send(json.dumps({"events": [{}]*21}).encode()), 400)
    def test_oversized_body_rejected(self):
        self.assertEqual(self.engine.receive(b"x"*(MAX_BODY_BYTES+1), None), 413)
    def test_other_user_is_ignored(self):
        self.send(payload(source={"type":"user", "userId":"U"+"2"*32}))
        self.assertFalse(self.engine.process_one())
        self.assertEqual(self.model.calls, 0)
    def test_group_is_ignored(self):
        self.send(payload(source={"type":"group", "userId":SETTINGS.test_user_id}))
        self.assertFalse(self.engine.process_one())
    def test_standby_is_ignored(self):
        self.send(payload(mode="standby"))
        self.assertFalse(self.engine.process_one())
    def test_image_is_ignored(self):
        self.send(payload(message={"type":"image", "id":"test-image"}))
        self.assertFalse(self.engine.process_one())
    def test_free_text_not_sent_to_model(self):
        self.send(payload("我的個資與其他真正的問題"))
        self.assertFalse(self.engine.process_one())
        self.assertEqual(self.model.calls, 0)
    def test_missing_reply_token_ignored(self):
        self.send(payload(replyToken=""))
        self.assertFalse(self.engine.process_one())
    def test_ack_does_not_run_model_synchronously(self):
        self.assertEqual(self.send(), 200)
        self.assertEqual(self.model.calls, 0)
        self.assertEqual(self.reply.calls, [])
        self.assertIn("ACCEPTED_IN_MEMORY", self.statuses())
    def test_ping_skips_gemini(self):
        self.send(payload("LOCAL ping"))
        self.engine.process_one()
        self.assertEqual(self.model.calls, 0)
        self.assertEqual(len(self.reply.calls), 1)
        self.assertIn("LINE_REPLY_ACCEPTED", self.statuses())
    def test_model_then_reply(self):
        self.send()
        self.engine.process_one()
        self.assertEqual(self.model.calls, 1)
        self.assertTrue(self.reply.calls[0][1].startswith(PREFIX))
        self.assertIn("MODEL_TEXT_RECEIVED", self.statuses())
        e = next(e for e in self.events if e["status"] == "LINE_REPLY_ACCEPTED")
        self.assertEqual(e["phone_display"], "not_observed_by_server")
    def test_duplicate_processed_once(self):
        self.send(); self.engine.process_one(); self.send()
        self.assertFalse(self.engine.process_one())
        self.assertEqual(self.model.calls, 1)
        self.assertEqual(len(self.reply.calls), 1)
    def test_queue_full_returns_503_then_can_admit_later(self):
        self.send()
        second = payload(event_id="second")
        self.assertEqual(self.send(second), 503)
        self.engine.process_one()
        self.assertEqual(self.send(second), 200)
        self.engine.process_one()
        self.assertEqual(self.model.calls, 2)
    def test_multi_event_body_does_not_silently_take_first(self):
        a = json.loads(payload("LOCAL ping", "a"))["events"][0]
        b = json.loads(payload("LOCAL ping", "b"))["events"][0]
        raw = json.dumps({"events":[a,b]}).encode()
        self.assertEqual(self.send(raw), 503)
        self.engine.process_one()
        self.assertEqual(self.send(raw), 200)
        self.engine.process_one()
        self.assertEqual(len(self.reply.calls), 2)
    def test_model_timeout_uses_truthful_fallback(self):
        self.model.error = TimeoutError("do-not-log-secret")
        self.send(); self.engine.process_one()
        self.assertEqual(self.model.calls, 1)
        self.assertEqual(self.reply.calls[0][1], FALLBACK)
        self.assertNotIn("do-not-log-secret", json.dumps(self.events))
    def test_truncated_response_uses_fallback(self):
        self.model.result["finish_reason"] = "MAX_TOKENS"
        self.send(); self.engine.process_one()
        self.assertEqual(self.reply.calls[0][1], FALLBACK)
    def test_empty_response_uses_fallback(self):
        self.model.result["text"] = " "
        self.send(); self.engine.process_one()
        self.assertEqual(self.reply.calls[0][1], FALLBACK)
    def test_tool_part_is_not_executed(self):
        self.model.result["unexpected_non_text"] = True
        self.send(); self.engine.process_one()
        self.assertEqual(self.reply.calls[0][1], FALLBACK)
    def test_model_call_cap(self):
        for i in range(4):
            self.send(payload(event_id=str(i))); self.engine.process_one()
        self.assertEqual(self.model.calls, 3)
        self.assertEqual(len(self.reply.calls), 3)
        self.assertIn("MODEL_BUDGET_STOP", self.statuses())
    def test_reply_cap(self):
        for i in range(9):
            self.send(payload("LOCAL ping", str(i))); self.engine.process_one()
        self.assertEqual(len(self.reply.calls), 8)
        self.assertIn("REPLY_BUDGET_STOP", self.statuses())
    def test_reply_timeout_is_unknown_and_not_retried(self):
        self.reply.error = TimeoutError("reply-token-secret")
        self.send(); self.engine.process_one()
        self.assertEqual(len(self.reply.calls), 1)
        self.assertIn("LINE_REPLY_UNKNOWN", self.statuses())
        self.assertNotIn("reply-token-secret", json.dumps(self.events))
    def test_reply_http_error_not_accepted(self):
        self.reply.code = 400
        self.send(); self.engine.process_one()
        self.assertIn("LINE_REPLY_HTTP_ERROR", self.statuses())
        self.assertNotIn("LINE_REPLY_ACCEPTED", self.statuses())
    def test_local_job_window_exceeded_no_send(self):
        now = [0.0]
        self.engine.clock = lambda: now[0]
        self.send(); now[0] = 36
        self.engine.process_one()
        self.assertEqual(self.model.calls, 0)
        self.assertEqual(self.reply.calls, [])
    def test_model_too_slow_does_not_blindly_reply(self):
        now = [0.0]
        self.engine.clock = lambda: now[0]
        original = self.model
        def slow():
            now[0] = 36
            return original()
        self.engine.generate = slow
        self.send(); self.engine.process_one()
        self.assertEqual(self.model.calls, 1)
        self.assertEqual(self.reply.calls, [])
    def test_restart_is_not_durable_dedup(self):
        self.send(); self.engine.process_one()
        other = Engine(SETTINGS, self.model, self.reply, lambda *a, **k: None)
        raw = payload(); other.receive(raw, sign(raw)); other.process_one()
        self.assertEqual(self.model.calls, 2)  # 明確留下限制，不偽稱跨重啟去重。


class HttpAndReportTests(unittest.TestCase):
    def setUp(self):
        self.model, self.reply, self.events = FakeModel(), FakeReply(), []
        self.engine = Engine(SETTINGS, self.model, self.reply,
                             lambda status, **kw: self.events.append({"status":status, **kw}))
    def test_health_no_config_leak(self):
        with TestClient(create_app(self.engine)) as client:
            response = client.get("/healthz")
            self.assertEqual(response.status_code, 200)
            self.assertNotIn(SETTINGS.channel_secret, response.text)
    def test_docs_and_report_not_public(self):
        with TestClient(create_app(self.engine)) as client:
            for path in ("/docs", "/openapi.json", "/REPORT.html", "/.env"):
                self.assertEqual(client.get(path).status_code, 404)
    def test_unsigned_http_request(self):
        with TestClient(create_app(self.engine)) as client:
            response = client.post("/webhook", content=payload())
            self.assertEqual(response.status_code, 401)
        self.assertEqual(self.model.calls, 0)
    def test_http_duplicate_signature_header(self):
        raw = payload()
        with TestClient(create_app(self.engine)) as client:
            r = client.post("/webhook", content=raw,
                            headers=[("x-line-signature",sign(raw)),("x-line-signature",sign(raw))])
            self.assertEqual(r.status_code, 401)
    def test_http_signed_empty(self):
        raw = b'{"events":[]}'
        with TestClient(create_app(self.engine)) as client:
            r = client.post("/webhook", content=raw, headers={"x-line-signature":sign(raw)})
            self.assertEqual(r.status_code, 200)
        self.assertEqual(self.reply.calls, [])
    def test_http_worker_reaches_fake_reply(self):
        raw = payload()
        with TestClient(create_app(self.engine)) as client:
            r = client.post("/webhook", content=raw, headers={"x-line-signature":sign(raw)})
            self.assertEqual(r.status_code, 200)
            limit = time.monotonic() + 2
            while not self.reply.calls and time.monotonic() < limit:
                time.sleep(0.01)
            self.assertEqual(len(self.reply.calls), 1)
    def test_http_body_limit(self):
        raw = b"x"*(MAX_BODY_BYTES+1)
        with TestClient(create_app(self.engine)) as client:
            r = client.post("/webhook", content=raw, headers={"x-line-signature":sign(raw)})
            self.assertEqual(r.status_code, 413)
    def test_line_payload_and_no_network(self):
        seen = []
        def handler(request):
            seen.append(request)
            return httpx.Response(200, json={"sentMessages":[]})
        send = make_line_reply(SETTINGS, httpx.MockTransport(handler))
        self.assertEqual(send("private-token", "測試文字"), {"http_code":200})
        self.assertEqual(len(seen), 1)
        self.assertEqual(str(seen[0].url), "https://api.line.me/v2/bot/message/reply")
        self.assertEqual(json.loads(seen[0].content)["messages"], [{"type":"text", "text":"測試文字"}])
    def test_report_masks_secrets_and_html(self):
        with tempfile.TemporaryDirectory() as tmp:
            recorder = Recorder(Path(tmp)/"run", SETTINGS, {"test":"only"}, mode="OFFLINE_TEST_DOUBLE")
            recorder("TEST", text="<script>alert(1)</script> "+SETTINGS.channel_secret)
            html = (recorder.folder/"REPORT.html").read_text()
            self.assertNotIn("<script>alert", html)
            self.assertIn("&lt;script&gt;", html)
            self.assertNotIn(SETTINGS.channel_secret, html)
            data = json.loads((recorder.folder/"verification.json").read_text())
            self.assertEqual(data["phone_review"], "not_recorded")
    def test_config_accepts_private_files(self):
        with tempfile.TemporaryDirectory() as tmp:
            p = Path(tmp)
            (p/"line").write_text("LINE_CHANNEL_SECRET=abc\nLINE_CHANNEL_ACCESS_TOKEN=def\nLINE_TEST_USER_ID="+SETTINGS.test_user_id)
            (p/"gemini").write_text("GEMINI_API_KEY=abcxyz")
            result = load_settings(p/"line",p/"gemini","gemini-3.8-flash")
            self.assertEqual(result.test_user_id,SETTINGS.test_user_id)
    def test_settings_repr_does_not_show_secrets(self):
        self.assertNotIn(SETTINGS.channel_secret, repr(SETTINGS))
    def test_config_rejects_placeholders(self):
        with tempfile.TemporaryDirectory() as tmp:
            p = Path(tmp)
            (p/"line").write_text("LINE_CHANNEL_SECRET=YOUR_SECRET")
            (p/"gemini").write_text("GEMINI_API_KEY=abcxyz")
            with self.assertRaises(ValueError):
                load_settings(p/"line",p/"gemini","gemini-3.8-flash")


if __name__ == "__main__":
    unittest.main()
