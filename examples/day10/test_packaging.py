"""交付的靜態防線：不是 GitHub runner 的成功紀錄。"""
from __future__ import annotations
import ast
from html import escape
import json
from pathlib import Path
import re
import tempfile
import unittest
from evidence import execution_info
from reporting import build_report
from upstream import HERE, REPO


class PackagingTests(unittest.TestCase):
    def test_all_python_files_compile(self):
        for path in HERE.glob('*.py'):
            compile(path.read_text('utf-8'),str(path),'exec')

    def test_action_refs_match_reviewed_full_sha_manifest(self):
        workflow=(REPO/'.github/workflows/ci.yml').read_text()
        lock=json.loads((HERE/'action-lock.json').read_text())
        refs=re.findall(r'uses:\s*(actions/[\w-]+)@([0-9a-f]{40})',workflow)
        self.assertEqual(len(refs),6)
        for repo,sha in refs:
            self.assertEqual(sha,lock['actions'][repo]['sha'])

    def test_workflow_has_no_business_secrets_or_live_invocation(self):
        text=(REPO/'.github/workflows/ci.yml').read_text()
        for forbidden in ('secrets.', 'id-token:', '--live', 'pull_request_target:', 'continue-on-error:', '|| true'):
            self.assertNotIn(forbidden,text)
        self.assertIn('contents: read',text)
        self.assertIn('workflow_dispatch:',text)
        self.assertIn('branches: [main]',text)

    def test_workflow_uses_separate_core_and_adk_jobs(self):
        text=(REPO/'.github/workflows/ci.yml').read_text()
        self.assertIn('--group core',text); self.assertIn('--group sdk',text)
        self.assertIn('python -m pip check',text)
        self.assertNotIn('path: editorial',text)

    def test_html_escapes_model_text_and_labels_static_source(self):
        with tempfile.TemporaryDirectory() as temp:
            path=Path(temp)/'REPORT.html'
            report={'mode':'OFFLINE_ADK','execution':{'origin':'assistant_check'},'success':False,
                    'cases':[{'name':'demo','steps':[],'model_turns':[{'phase':'submit','final_text':'<script>bad()</script>'}]}]}
            build_report(report,path)
            text=path.read_text()
            self.assertNotIn('<script>',text)
            self.assertIn(escape('<script>bad()</script>'),text)
            self.assertIn('assistant_check',text)
            self.assertIn('未通過／未完整執行',text)

    def test_html_does_not_overwrite_existing_report(self):
        with tempfile.TemporaryDirectory() as temp:
            path=Path(temp)/'REPORT.html'
            build_report({},path)
            with self.assertRaises(FileExistsError): build_report({},path)

    def test_model_workflow_is_bounded_and_no_real_model_name_is_assumed(self):
        runtime=(HERE/'runtime.py').read_text()
        self.assertIn('max_llm_calls=3',runtime)
        self.assertIn('timeout=45',runtime)
        run=(HERE/'run.py').read_text()
        self.assertIn('not args.approve_live or not args.model',run)
        self.assertIn('attempts=1',run)

    def test_provenance_does_not_pretend_assistant_is_author(self):
        import os
        if os.getenv('GITHUB_ACTIONS')=='true':
            self.assertEqual(execution_info('reader_local')['execution_environment'],'github_actions')
        else:
            self.assertEqual(execution_info('assistant_check')['origin'],'assistant_check')


if __name__=='__main__':
    unittest.main(verbosity=2)
