"""真正 Firestore 模擬器；不可用就整組回非零，不退回 SQLite。"""
import os,secrets,tempfile,unittest
from pathlib import Path
from google.cloud import firestore  # 明確依賴；沒有 SDK 不能列成通過。
from firestore_store import FirestoreStore
from contract_checks import ContractChecks


class EmulatorTests(ContractChecks,unittest.TestCase):
    def setUp(self):
        self.store=FirestoreStore('demo-local-day11','day11-test-'+secrets.token_hex(10))
        self.addCleanup(self.store.close);self.init_contract()

class EmulatorProcessTests(unittest.TestCase):
    def test_six_actual_cross_process_cases(self):
        from demo import run_demo
        with tempfile.TemporaryDirectory() as temp:
            folder,report=run_demo(Path(temp),backend='emulator',origin=os.getenv('LOCAL_EXECUTION_ORIGIN','reader_local'))
            self.assertTrue(report['success'],report)
            self.assertEqual(len(report['cases']),6)
            for c in report['cases']:self.assertNotEqual(*c['pids'])

    def test_memory_and_real_firestore_normal_restart_contrast(self):
        from comparison import run_comparison
        with tempfile.TemporaryDirectory() as temp:
            folder,report=run_comparison(Path(temp),backend='emulator',
                origin=os.getenv('LOCAL_EXECUTION_ORIGIN','reader_local'))
            self.assertTrue(report['success'],report)
            self.assertTrue(report['firestore_emulator_passed'])
            self.assertFalse(report['firestore_cloud_passed'])
            self.assertEqual(report['rows'][1]['status'],'already_created')

if __name__=='__main__':unittest.main()
