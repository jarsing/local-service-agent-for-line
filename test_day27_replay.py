"""獨立本機探測；不計入原 Repo 的 155 項測試。"""
import json
import sqlite3
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
from replay_day27 import run, require
from examples.day22.circuit_breaker import SecurityStore

class ReplayTests(unittest.TestCase):
    def setUp(self):
        base = Path('out/day27/replay-tests')
        base.mkdir(parents=True, exist_ok=True)
        self.temp=tempfile.TemporaryDirectory(dir=base)
        self.out=Path(self.temp.name)/'new'
    def tearDown(self):self.temp.cleanup()
    def test_same_order_and_state(self):
        r=run(self.out)
        self.assertEqual(r['status'],'PASS')
        self.assertEqual(len({e['request_id'] for e in r['events']}),1)
        self.assertEqual(r['final_state'],'human_claimed')
        self.assertFalse(r['second_claim_succeeded'])
        with sqlite3.connect(self.out/'demo.sqlite3') as db:
            self.assertEqual(db.execute('PRAGMA integrity_check').fetchone()[0],'ok')
            self.assertEqual(db.execute('SELECT COUNT(*) FROM requests').fetchone()[0],1)
    def test_existing_output_preserved(self):
        run(self.out);before=(self.out/'report.json').read_bytes()
        with self.assertRaises(FileExistsError):run(self.out)
        self.assertEqual(before,(self.out/'report.json').read_bytes())
    def test_changed_core_refused(self):
        with patch('replay_day27.EXPECTED_CORE_SHA256','0'*64):
            with self.assertRaisesRegex(RuntimeError,'CORE_VERSION_MISMATCH'):run(self.out)
        self.assertFalse(self.out.exists())
    def test_failure_recorded(self):
        with patch.object(SecurityStore,'claim',return_value=True):
            with self.assertRaisesRegex(RuntimeError,'PAUSED_CLAIM_ACCEPTED'):run(self.out)
        self.assertEqual(json.loads((self.out/'report.json').read_text())['status'],'FAIL')
    def test_require_does_not_accept_truthy(self):
        with self.assertRaises(RuntimeError):require(1,'NOT_A_BOOLEAN')

if __name__=='__main__':unittest.main(verbosity=2)
