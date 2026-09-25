"""標準函式庫離線測試。SQLiteTestStore 不是 Firestore 模擬器。"""
from pathlib import Path
import json,os,sqlite3,tempfile,unittest
from unittest.mock import patch
from datetime import timedelta
from contract_checks import ContractChecks
from store import SQLiteTestStore,SQLiteTx,StoreUnavailable
from domain import key,pending
from service import HandoffService
from firestore_store import validate_target
from upstream import ConfirmationStore,operation_fingerprint

class CoreTests(ContractChecks,unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup)
        self.store=SQLiteTestStore(Path(self.tmp.name)/'db.sqlite3');self.init_contract()

    def test_reopened_database_new_service_reads_original(self):
        a=self.write();new=HandoffService(SQLiteTestStore(self.store.path),clock=self.clock)
        self.assertEqual(new.lookup(self.actor,self.args)['request_id'],a['request_id'])
    def test_store_unavailable_retains_unknown(self):
        with patch.object(self.store,'atomic',side_effect=StoreUnavailable('injected')):
            self.assertEqual(self.service.lookup(self.actor,self.args)['observation'],'lookup_unavailable')
            self.assertIsNone(self.write()['request_created'])
    def test_programming_error_is_not_hidden_as_not_found(self):
        with patch.object(self.store,'atomic',side_effect=ValueError('bug')):
            with self.assertRaises(ValueError):self.service.lookup(self.actor,self.args)
    def test_callback_replay_keeps_one_candidate_receipt(self):
        underlying=self.store;attempts=[]
        class RetryOnce:
            mode='SQLITE_TEST_ADAPTER'
            def atomic(_,fn,*,read_only=False):
                c=sqlite3.connect(underlying.path,isolation_level=None)
                try:
                    c.execute('BEGIN IMMEDIATE');value=fn(SQLiteTx(c,False));attempts.append(value);c.rollback()
                finally:c.close()
                value=underlying.atomic(fn,read_only=read_only);attempts.append(value);return value
        self.service.store=RetryOnce()
        result=self.write()
        self.assertEqual(len(attempts),2);self.assertEqual(attempts[0]['request_id'],attempts[1]['request_id'])
        self.assertEqual(result['request_id'],attempts[0]['request_id']);self.assertEqual(len(underlying.inspect()['requests']),1)
    def test_day08_persistent_gate_parity_for_fixed_scenarios(self):
        from confirmation_gate import validate_first_write
        import copy
        from dataclasses import replace
        # 比對本篇新增 gate 與 Day 8 的時間／內容／版本決定，不宣稱恢復其整個內部儲存。
        db=self.store.inspect();binding=db['bindings'][self.oid];confirmation=db['confirmations'][self.cid]
        for name in ('valid','expired','clock','version','data','content'):
            with self.subTest(name=name):
                original=ConfirmationStore();offer=original.issue(owner=self.actor.identity,operation=self.op,
                    current_catalog_version=self.op.catalog_version,data_status='adopted',now=self.now,ttl_seconds=300)
                original.decide(confirmation_id=offer['confirmation_id'],actor=self.actor.identity,current_operation=self.op,
                    current_catalog_version=self.op.catalog_version,data_status='adopted',permitted=True,approved=True,now=self.now)
                moment=self.now+(timedelta(seconds=300) if name=='expired' else timedelta(seconds=-1) if name=='clock' else timedelta())
                version='v2' if name=='version' else self.op.catalog_version
                status='pending' if name=='data' else 'adopted'
                op=replace(self.op,request_text='changed') if name=='content' else self.op
                expected=original.decide(confirmation_id=offer['confirmation_id'],actor=self.actor.identity,current_operation=op,
                    current_catalog_version=version,data_status=status,permitted=True,approved=True,now=moment)['status']
                from dataclasses import asdict
                actual=validate_first_write(confirmation,binding,asdict(op),{'catalog_version':version,
                    'data_status':status,'displayed_event':self.op.displayed_event},moment)
                self.assertEqual(actual or 'already_confirmed',expected)

class SafetyTests(unittest.TestCase):
    def test_structured_keys_do_not_have_separator_collisions(self):
        self.assertNotEqual(key('a|b','c'),key('a','b|c'))
    def test_emulator_requires_explicit_loopback_and_demo_project(self):
        with patch.dict(os.environ,{'FIRESTORE_EMULATOR_HOST':'127.0.0.1:8080'}):
            validate_target('demo-local-day11','day11-test')
            with self.assertRaises(ValueError):validate_target('real-project','day11-test')
    def test_missing_emulator_host_does_not_fallback_to_cloud(self):
        with patch.dict(os.environ,{'FIRESTORE_EMULATOR_HOST':''}):
            with self.assertRaises(ValueError):validate_target('demo-local-day11','day11-test')
    def test_emulator_rejects_nonlocal_host(self):
        with patch.dict(os.environ,{'FIRESTORE_EMULATOR_HOST':'example.com:8080'}):
            with self.assertRaises(ValueError):validate_target('demo-local-day11','day11-test')
    def test_cloud_needs_separate_explicit_approval(self):
        with patch.dict(os.environ,{'FIRESTORE_EMULATOR_HOST':''}):
            with self.assertRaises(ValueError):validate_target('real-project','day11-test',cloud=True)
    def test_cloud_rejects_mixed_emulator_config(self):
        with patch.dict(os.environ,{'FIRESTORE_EMULATOR_HOST':'localhost:8080'}):
            with self.assertRaises(ValueError):validate_target('real-project','day11-test',cloud=True,approve_cloud=True)
    def test_namespace_must_be_isolated(self):
        with patch.dict(os.environ,{'FIRESTORE_EMULATOR_HOST':'localhost:8080'}):
            with self.assertRaises(ValueError):validate_target('demo-local-day11','production')
    def test_model_cannot_change_grants_by_tool_schema(self):
        import ast
        module=ast.parse((Path(__file__).parent/'adk_bridge.py').read_text('utf-8'))
        names={'create_handoff_request','reconcile_handoff_request'}
        functions=[n for n in ast.walk(module) if isinstance(n,ast.FunctionDef) and n.name in names]
        self.assertEqual(len(functions),2)
        for f in functions:
            self.assertEqual([a.arg for a in f.args.args],['idempotency_key','confirmation_id','request_text','event_id','tool_context'])

    def test_network_guard_keeps_socket_a_class(self):
        from evidence import no_network
        import socket,ssl
        with no_network():
            self.assertIsInstance(socket.socket,type)
            self.assertTrue(issubclass(ssl.SSLSocket,socket.socket))
    def test_network_guard_blocks_dns_and_connect(self):
        from evidence import no_network
        import socket
        with no_network():
            with self.assertRaisesRegex(RuntimeError,'NETWORK_BLOCKED'):
                socket.getaddrinfo('example.invalid',443)
            with socket.socket() as sock:
                with self.assertRaisesRegex(RuntimeError,'NETWORK_BLOCKED'):
                    sock.connect(('127.0.0.1',9))
    def test_network_guard_allows_asyncio_self_pipe(self):
        from evidence import no_network
        import asyncio
        async def tiny():return 7
        with no_network():self.assertEqual(asyncio.run(tiny()),7)

class PackagingTests(unittest.TestCase):
    def test_all_day11_python_sources_compile(self):
        for path in Path(__file__).parent.glob('*.py'):
            compile(path.read_text('utf-8'),str(path),'exec')
    def test_new_workflow_is_separate_and_has_real_exit_check(self):
        root=Path(__file__).resolve().parents[2]
        text=(root/'.github/workflows/day11.yml').read_text('utf-8')
        self.assertIn('contents: read',text)
        self.assertIn('--module test_core',text);self.assertIn('--module test_adk_offline',text)
        self.assertNotIn('continue-on-error',text);self.assertNotIn('|| true',text)
        self.assertNotIn('secrets.',text);self.assertNotIn('--approve-cloud',text)
        self.assertNotIn('id-token: write',text)
    def test_inherited_workflow_not_replaced(self):
        root=Path(__file__).resolve().parents[2]
        text=(root/'.github/workflows/ci.yml').read_text('utf-8')
        self.assertIn('examples/day10/verify.py --group core',text)
        self.assertIn('examples/day10/verify.py --group sdk',text)
    def test_raw_sqlite_reference_is_not_called_firestore_emulator(self):
        self.assertEqual(SQLiteTestStore.mode,'SQLITE_TEST_ADAPTER')
    def test_day11_has_no_live_gemini_switch(self):
        import ast
        tree=ast.parse((Path(__file__).parent/'demo.py').read_text('utf-8'))
        strings=[n.value for n in ast.walk(tree) if isinstance(n,ast.Constant) and isinstance(n.value,str)]
        self.assertNotIn('--live',strings)
    def test_dependency_lock_checks_original_sources(self):
        from upstream import check_dependencies
        values=check_dependencies()
        self.assertIn('examples/day08/confirmation.py',values)
        self.assertIn('examples/day09/handoff.py',values)
        self.assertEqual(values['docs/day01/handoff-timeout-001.json'],'9a4768046189e6ba0d42637953b8d73e41566f7c573ea0a76b32079b1a762218')

class ProcessTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        from demo import run_demo
        cls.tmp=tempfile.TemporaryDirectory()
        cls.root,cls.report=run_demo(Path(cls.tmp.name),origin=os.getenv('LOCAL_EXECUTION_ORIGIN','reader_local'))
    @classmethod
    def tearDownClass(cls):cls.tmp.cleanup()
    def test_all_six_cases_have_actual_different_processes(self):
        self.assertTrue(self.report['success'],self.report)
        self.assertEqual(len(self.report['cases']),6)
        for c in self.report['cases']:self.assertNotEqual(*c['pids'])
    def test_postcommit_crash_returns_original_row(self):
        from proof import check_case
        c=check_case(self.root/'after_commit','after_commit')
        self.assertEqual((c['rows_after_a'],c['rows_after_b'],c['writes']),(1,1,1))
    def test_prewrite_crash_reuses_original_approval(self):
        from proof import check_case
        c=check_case(self.root/'before_write','before_write')
        self.assertEqual((c['rows_after_a'],c['rows_after_b'],c['writes']),(0,1,2))
    def test_expired_beforewrite_does_not_write(self):
        from proof import check_case
        self.assertEqual(check_case(self.root/'expired_before_write','expired_before_write')['rows_after_b'],0)
    def test_unknown_can_coexist_with_an_existing_request(self):
        from proof import check_case
        c=check_case(self.root/'lookup_unavailable','lookup_unavailable')
        self.assertEqual(c['status'],'pending_verification');self.assertEqual(c['rows_after_b'],1)
        self.assertIsNone(c['request_id'])
    def test_proof_reads_sqlite_not_only_json_claims(self):
        from proof import check_case
        import shutil
        dest=self.root/'tampered-copy';shutil.copytree(self.root/'after_commit',dest)
        from contextlib import closing
        with closing(sqlite3.connect(dest/'after-b.sqlite3')) as c:
            c.execute("DELETE FROM docs WHERE kind='requests'");c.commit()
        with self.assertRaisesRegex(AssertionError,'SQLite'):check_case(dest,'after_commit')



class NewHandoffTests(unittest.TestCase):
    def test_same_huatan_snapshot_is_reused_without_changing_date(self):
        from fixtures import sample_operation
        op=sample_operation()
        self.assertEqual(op.event_id,'evt-60d76a55472c503faa4c')
        self.assertEqual(op.displayed_event['date'],'2026-09-19')
        self.assertEqual(op.request_text,'請問花壇場次的集合地點在哪裡？')
    def test_memory_store_is_process_local_not_a_firestore_fallback(self):
        from memory_control import MemoryControlStore
        a=MemoryControlStore();b=MemoryControlStore()
        ident=key('test')
        a.atomic(lambda tx:tx.create('requests',ident,{'message':'original'}))
        self.assertEqual(a.inspect()['requests'][ident]['message'],'original')
        self.assertEqual(b.inspect(),{})
        self.assertEqual(a.mode,'MEMORY_CONTROL')
    def test_memory_read_only_disallows_mutation(self):
        from memory_control import MemoryControlStore
        from domain import ContractError
        a=MemoryControlStore()
        with self.assertRaises(ContractError):
            a.atomic(lambda tx:tx.put('requests',key('test'),{}),read_only=True)
        self.assertEqual(a.inspect(),{})
    def test_memory_failure_rolls_back_its_trial_copy(self):
        from memory_control import MemoryControlStore
        a=MemoryControlStore();ident=key('test')
        a.atomic(lambda tx:tx.create('requests',ident,{'message':'original'}))
        def failure(tx):
            tx.put('requests',ident,{'message':'changed'})
            raise ValueError('injected')
        with self.assertRaises(ValueError):a.atomic(failure)
        self.assertEqual(a.inspect()['requests'][ident]['message'],'original')
    def test_emulator_target_rejects_query_credentials_and_fragments(self):
        for host in ('localhost:8080?x=y','localhost:8080#other','user@localhost:8080','localhost:8080/path'):
            with self.subTest(host=host),patch.dict(os.environ,{'FIRESTORE_EMULATOR_HOST':host}):
                with self.assertRaises(ValueError):validate_target('demo-local-day11','day11-test')
    def test_transient_error_classifier_accepts_explicit_abort_cause_only(self):
        from types import SimpleNamespace
        from firestore_store import transient_storage_error
        errors=SimpleNamespace(**{n:type(n,(Exception,),{}) for n in
            ('ServiceUnavailable','DeadlineExceeded','Aborted','ResourceExhausted')})
        wrapped=ValueError('retry exhausted');wrapped.__cause__=errors.Aborted('aborted')
        self.assertTrue(transient_storage_error(wrapped,errors))
        for name in vars(errors):self.assertTrue(transient_storage_error(getattr(errors,name)(),errors))
        self.assertFalse(transient_storage_error(ValueError('ordinary bug'),errors))
        other=ValueError('not transaction');other.__cause__=KeyError('bug')
        self.assertFalse(transient_storage_error(other,errors))
    def test_firestore_wrapper_reads_with_transaction_and_rejects_after_write(self):
        from firestore_store import FirestoreTx
        from domain import ContractError
        from unittest.mock import MagicMock
        doc=MagicMock();doc.get.return_value.exists=True;doc.get.return_value.to_dict.return_value={'x':1}
        root=MagicMock();root.collection.return_value.document.return_value=doc
        transaction=MagicMock();tx=FirestoreTx(root,transaction,read_only=False)
        self.assertEqual(tx.get('requests',key('x')),{'x':1})
        doc.get.assert_called_once_with(transaction=transaction,retry=None,timeout=10)
        tx.create('requests',key('x'),{'x':2})
        transaction.create.assert_called_once_with(doc,{'x':2})
        with self.assertRaises(ContractError):tx.get('requests',key('x'))
        # 這是 wrapper 單元測試，不是 Firestore SDK 或伺服器整合。

class MemoryComparisonTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        from comparison import run_comparison
        cls.tmp=tempfile.TemporaryDirectory()
        cls.folder,cls.result=run_comparison(Path(cls.tmp.name),origin=os.getenv('LOCAL_EXECUTION_ORIGIN','reader_local'))
    @classmethod
    def tearDownClass(cls):cls.tmp.cleanup()
    def test_control_loses_task_while_sqlite_preserves_it(self):
        self.assertTrue(self.result['success'],self.result)
        memory,persistent=self.result['rows']
        self.assertEqual((memory['rows_after_a'],memory['rows_after_b']),(1,0))
        self.assertEqual((persistent['rows_after_a'],persistent['rows_after_b']),(1,1))
        self.assertEqual(memory['status'],'session_not_found')
        self.assertEqual(persistent['status'],'already_created')
        self.assertIsNotNone(persistent['request_id'])
    def test_memory_b_has_no_confirmation_and_uses_no_original_args_config(self):
        memory=self.result['rows'][0]
        case=self.folder/memory['run']/'normal'
        cfg=json.loads((case/'config.json').read_text())
        self.assertFalse({'request_id','send_args','confirmation_id','idempotency_key'} & set(cfg))
        after=json.loads((case/'after-b.json').read_text())
        self.assertFalse(after.get('bindings'));self.assertFalse(after.get('confirmations'))
        from proof import load_events
        self.assertFalse(any(e['kind']=='CONFIRMATION_STORED' for e in load_events(case/'process-b')))
    def test_all_four_processes_are_actual_distinct_children(self):
        pids=[pid for row in self.result['rows'] for pid in row['pids']]
        self.assertEqual(len(set(pids)),4)
    def test_sqlite_comparison_does_not_claim_firestore_ran(self):
        self.assertFalse(self.result['firestore_emulator_passed'])
        self.assertFalse(self.result['firestore_cloud_passed'])
    def test_persistent_comparison_rejects_tampered_database(self):
        import shutil
        from proof import check_case
        row=self.result['rows'][1];case=self.folder/row['run']/'normal'
        other=self.folder/'tampered';shutil.copytree(case,other)
        with sqlite3.connect(other/'after-b.sqlite3') as c:
            c.execute("DELETE FROM docs WHERE kind='requests'");c.commit()
        with self.assertRaisesRegex(AssertionError,'SQLite'):check_case(other,'normal')

if __name__=='__main__':unittest.main()
