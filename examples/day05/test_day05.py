"""離線測試：真實資料函式及 Day 4 入口，模型和 LINE 採替身。"""
from __future__ import annotations
import asyncio
import base64
import copy
import hashlib
import hmac
import io
import json
from pathlib import Path
import tempfile
from types import SimpleNamespace as NS
import unittest
from unittest.mock import patch

from catalog import load_catalog, load_cases, normalize_query, search_catalog, make_search_tool, TOOL_NAME
from reporting import Report, read_key, render_report, comparison_markdown
from runtime import Trace, trace_matches, error_info
from line_bridge import load_day04, make_reply, BridgeGenerator


class CatalogTests(unittest.TestCase):
    def setUp(self): self.data=load_catalog(); self.cases=load_cases()
    def test_four_events(self): self.assertEqual(len(self.data["events"]),4)
    def test_four_questions(self): self.assertEqual(len(self.cases),4)
    def test_query_returns_time_place(self):
        result=search_catalog(self.data,self.cases[0]["query"])
        self.assertEqual(result["events"][0]["time"],"09:30")
        self.assertEqual(result["events"][0]["meeting_point"],"示範社區活動中心入口")
    def test_missing_field_is_explicit_unknown(self):
        self.assertNotIn("accessibility",self.data["events"][0])
        result=search_catalog(self.data,self.cases[0]["query"])
        self.assertIsNone(result["events"][0]["accessibility"])
        self.assertEqual(result["unknown_fields"],["walk-001.accessibility"])
    def test_false_is_not_unknown(self):
        result=search_catalog(self.data,self.cases[2]["query"])
        self.assertIs(result["events"][0]["accessibility"],False)
        self.assertEqual(result["unknown_fields"],[])
    def test_filters_combine_with_and(self):
        self.assertEqual(search_catalog(self.data,{"date":"2026-09-27","area":"鹿港鎮"})["status"],"not_found")
    def test_area_only(self): self.assertEqual(len(search_catalog(self.data,{"area":"彰化市"})["events"]),2)
    def test_not_found(self): self.assertEqual(search_catalog(self.data,self.cases[3]["query"])["events"],[])
    def test_source_and_update_retained(self):
        e=search_catalog(self.data,self.cases[0]["query"])["events"][0]
        self.assertEqual(e["source"],"DEMO-WALK-001"); self.assertTrue(e["updated_at"])
    def test_input_is_not_mutated(self):
        before=copy.deepcopy(self.data); r=search_catalog(self.data,self.cases[0]["query"])
        r["events"][0]["time"]="00:00"; self.assertEqual(self.data,before)
    def test_empty_query_rejected(self):
        with self.assertRaises(ValueError): normalize_query({})
    def test_extra_parameter_rejected(self):
        with self.assertRaises(ValueError): normalize_query({"area":"彰化市","path":"/etc/passwd"})
    def test_invalid_date_rejected(self):
        with self.assertRaises(ValueError): normalize_query({"date":"2026-02-30"})
    def test_non_string_rejected(self):
        with self.assertRaises(ValueError): normalize_query({"area":7})
    def test_tool_real_execution_is_recorded(self):
        events=[]; tool=make_search_tool(self.data,lambda kind,**fields:events.append({"kind":kind,**fields}))
        self.assertEqual(tool.__name__,"search_local_events")
        tool(**self.cases[0]["query"]); self.assertEqual(events[0]["kind"],"TOOL_EXECUTED")
    def test_tool_cap(self):
        tool=make_search_tool(self.data,lambda *a,**k:None,max_calls=1)
        tool(area="彰化市"); self.assertEqual(tool(area="彰化市")["code"],"TOOL_LIMIT")
    def test_all_cases_match_catalog(self):
        for c in self.cases:
            result=search_catalog(self.data,c["query"])
            self.assertEqual([x["id"] for x in result["events"]],c["expected_ids"])
            self.assertEqual(result["unknown_fields"],c["expected_unknown"])


class TraceTests(unittest.TestCase):
    def setUp(self): self.trace=Trace(lambda *a,**k:None,3)
    def test_claim_without_execution_has_no_trace(self):
        self.assertFalse(trace_matches([{"kind":"FINAL_TEXT","text":"查好了"}],["walk-001"]))
    def test_real_execution_and_response_match(self):
        c=load_cases()[0]; result=search_catalog(load_catalog(),c["query"])
        events=[{"kind":"TOOL_REQUESTED","name":TOOL_NAME,"args":c["query"]},
                {"kind":"TOOL_EXECUTED","name":TOOL_NAME,"args":c["query"],"result":result},
                {"kind":"TOOL_RESPONSE","name":TOOL_NAME,"response":result}]
        self.assertTrue(trace_matches(events,["walk-001"]))
        self.assertFalse(trace_matches(events,["walk-002"]))
    def test_not_found_also_checks_query(self):
        case=load_cases()[3]
        query={"date":"2026-12-31","area":"彰化市","keyword":"夜間走讀"}
        result=search_catalog(load_catalog(),query)
        events=[{"kind":"TOOL_REQUESTED","name":TOOL_NAME,"args":query},
                {"kind":"TOOL_EXECUTED","name":TOOL_NAME,"args":query,"result":result},
                {"kind":"TOOL_RESPONSE","name":TOOL_NAME,"response":result}]
        self.assertFalse(trace_matches(events,[],case["query"]))
    def test_correct_not_found_trace(self):
        case=load_cases()[3];query=case["query"];result=search_catalog(load_catalog(),query)
        events=[{"kind":"TOOL_REQUESTED","name":TOOL_NAME,"args":query},
                {"kind":"TOOL_EXECUTED","name":TOOL_NAME,"args":query,"result":result},
                {"kind":"TOOL_RESPONSE","name":TOOL_NAME,"response":result}]
        self.assertTrue(trace_matches(events,[],query))
    def test_tool_response_required(self):
        result=search_catalog(load_catalog(),{"area":"彰化市"})
        self.assertFalse(trace_matches([{"kind":"TOOL_EXECUTED","args":{"area":"彰化市"},"result":result}],['walk-001','craft-003']))
    def test_model_budget(self):
        req=NS(config=NS(tools=[]))
        for _ in range(3): self.trace.before_model(None,req)
        with self.assertRaises(RuntimeError):self.trace.before_model(None,req)
    def test_extra_tool_argument_blocked(self):
        result=self.trace.before_tool(NS(name=TOOL_NAME),{"area":"彰化市","shell":"ls"},None)
        self.assertEqual(result["code"],"INVALID_ARGUMENTS")
    def test_thought_part_excluded(self):
        event=NS(error_code=None,partial=False,finish_reason="STOP",
                 content=NS(parts=[NS(text="hidden",thought=True),NS(text="09:30",thought=False)]),
                 get_function_calls=lambda:[],get_function_responses=lambda:[],is_final_response=lambda:True)
        self.trace.observe(event);self.assertEqual(self.trace.final_text,"09:30")
    def test_usage_unknown_stays_none(self):
        self.trace.after_model(None,NS(usage_metadata=None,finish_reason="STOP",model_version=None,error_code=None))
        self.assertIsNone(self.trace.responses[0]["usage"]["total_token_count"])
    def test_http_error_metadata(self):
        error=ValueError("x"); error.code=503
        self.assertEqual(error_info(error)["http_code"],503)


class ReportTests(unittest.TestCase):
    def test_unique_folders(self):
        with tempfile.TemporaryDirectory() as temp:
            a=Report(Path(temp),"OFFLINE_TEST");b=Report(Path(temp),"OFFLINE_TEST")
            self.assertNotEqual(a.folder,b.folder)
    def test_secrets_redacted_in_nested_data(self):
        with tempfile.TemporaryDirectory() as temp:
            r=Report(Path(temp),"OFFLINE_TEST",secrets=('very-secret"value',))
            r("X",data={"value":'very-secret"value'})
            self.assertNotIn('very-secret',(r.folder/'verification.json').read_text())
    def test_html_escapes_model_text(self):
        with tempfile.TemporaryDirectory() as temp:
            r=Report(Path(temp),"OFFLINE_TEST");r.data["events"]=[{"text":"<script>alert(1)</script>"}]
            page=render_report(r.data)
            self.assertNotIn('<script>',page);self.assertIn('&lt;script&gt;',page)
    def test_markdown_escape(self):
        data={"turns":[{"case_id":"x","condition":"with_tool","question":"a|b","final_text":"<img>\nhello|x"}]}
        text=comparison_markdown(data)
        self.assertIn("&#124;",text);self.assertIn("&lt;img&gt;",text);self.assertIn("尚未執行",text)
    def test_read_key_file_takes_precedence(self):
        with tempfile.TemporaryDirectory() as temp:
            p=Path(temp)/'key.env';p.write_text('GEMINI_API_KEY="local-key"\n')
            with patch.dict('os.environ',{'GEMINI_API_KEY':'other-key'}):self.assertEqual(read_key(p),'local-key')
    def test_key_missing_fails(self):
        with patch.dict('os.environ',{},clear=True):
            with self.assertRaises(ValueError): read_key(None)


class LineBridgeTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls): cls.core,cls.app,cls.adapters=load_day04()
    def settings(self):return self.core.Settings('test-secret','test-token','U'+'1'*32,'test-key')
    def body(self,text='LOCAL ping',user=None):
        return json.dumps({'events':[{'type':'message','mode':'active','source':{'type':'user','userId':user or 'U'+'1'*32},
           'message':{'type':'text','text':text},'webhookEventId':'evt-demo','replyToken':'reply-demo'}]},ensure_ascii=False).encode()
    def signature(self,body):return base64.b64encode(hmac.new(b'test-secret',body,hashlib.sha256).digest()).decode()
    def test_ping_never_calls_model(self):
        sent=[]
        engine=self.core.Engine(self.settings(),lambda: self.fail('ping 呼叫了模型'),lambda t,x:sent.append(x) or {'http_code':200},lambda *a,**k:None)
        raw=self.body();self.assertEqual(engine.receive(raw,self.signature(raw)),200);engine.process_one();self.assertEqual(len(sent),1)
    def test_invalid_signature_blocked(self):
        engine=self.core.Engine(self.settings(),lambda: {},lambda *a:{},lambda *a,**k:None)
        self.assertEqual(engine.receive(self.body(),"wrong"),401);self.assertTrue(engine.pending.empty())
    def test_other_user_ignored(self):
        engine=self.core.Engine(self.settings(),lambda: {},lambda *a:{},lambda *a,**k:None)
        raw=self.body(user='U'+'2'*32);engine.receive(raw,self.signature(raw));self.assertTrue(engine.pending.empty())
    def test_new_fallback_has_no_false_lookup_claim(self):
        sent=[];send=make_reply(lambda token,text:sent.append(text) or {'http_code':200},self.core)
        send('token',self.core.FALLBACK);self.assertEqual(sent[0],'這次活動查詢暫時遇到問題，請稍後再試。')
    def test_model_original_text_preserved(self):
        sent=[];send=make_reply(lambda token,text:sent.append(text),self.core)
        send('token',self.core.PREFIX+'模型原文');self.assertEqual(sent[0],'【LOCAL 範例活動】\n模型原文')
    def test_generator_uses_live_result_and_caps_one_turn(self):
        class R:
            def __call__(self,*a,**k):pass
            def add_turn(self,t):self.turn=t
        async def fake(*a,**k):return {'status':'RECORDED','final_text':'離線替身','finish_reason':'STOP'}
        r=R();g=BridgeGenerator(r,'dummy')
        with patch('line_bridge.run_turn',new=fake):
            self.assertEqual(g()['text'],'離線替身')
            with self.assertRaises(RuntimeError):g()
    def test_fastapi_signed_empty_event(self):
        from fastapi.testclient import TestClient
        engine=self.core.Engine(self.settings(),lambda:{},lambda *a:{},lambda *a,**k:None)
        with TestClient(self.app.create_app(engine)) as client:
            raw=b'{"events":[]}'
            self.assertEqual(client.post('/webhook',content=raw,headers={'x-line-signature':self.signature(raw)}).status_code,200)
            self.assertEqual(client.get('/docs').status_code,404)


if __name__=='__main__':unittest.main()
