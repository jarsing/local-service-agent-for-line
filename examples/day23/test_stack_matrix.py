"""Deterministic local tests; illustrative numeric inputs are not measurements."""
import ast
import copy
import json
import math
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from .stack_matrix import ROOT, METRICS, assess, evaluate, latency_check, measure_local, read_options, write_report


class StackMatrixTests(unittest.TestCase):
    def setUp(self):
        self.options, _ = read_options()
        self.needs = {'model_perimeter': False, 'relational_joins': False}

    def test_community_keeps_four_declared_designs(self):
        r = evaluate()
        self.assertEqual(len(r['rows']), 4)
        self.assertTrue(all(x['decision'] == 'CANDIDATE' for x in r['rows']))

    def test_governed_retains_vertex_only(self):
        r = evaluate('governed')
        self.assertEqual([x['option_id'] for x in r['rows'] if x['decision'] == 'CANDIDATE'], ['vertex-run'])

    def test_reporting_retains_sql_only(self):
        r = evaluate('reporting')
        self.assertEqual([x['option_id'] for x in r['rows'] if x['decision'] == 'CANDIDATE'], ['sql-run'])

    def test_scale_zero_is_optional_not_universal(self):
        r = evaluate(require_scale_zero=True)
        self.assertEqual([x['option_id'] for x in r['rows'] if x['decision'] == 'CANDIDATE'], ['run-zero', 'sql-run'])

    def test_conflicting_needs_can_leave_no_candidate(self):
        r = evaluate('governed', require_scale_zero=True)
        self.assertFalse(any(x['decision'] == 'CANDIDATE' for x in r['rows']))

    def test_missing_latency_stays_unknown(self):
        self.assertEqual(latency_check(None), 'NEEDS_MEASUREMENT')

    def test_latency_boundary_is_inclusive(self):
        self.assertEqual(latency_check(2000), 'PASS')

    def test_slow_latency_fails(self):
        self.assertEqual(latency_check(2000.1), 'FAIL')

    def test_boolean_is_not_latency(self):
        with self.assertRaises(ValueError): latency_check(False)

    def test_nonfinite_latency_rejected(self):
        for value in (math.nan, math.inf, -math.inf):
            with self.subTest(value=value), self.assertRaises(ValueError): latency_check(value)

    def test_negative_or_string_latency_rejected(self):
        for value in (-1, '0'):
            with self.subTest(value=value), self.assertRaises(ValueError): latency_check(value)

    def test_budget_must_be_positive_even_when_latency_missing(self):
        for value in (0, -1, False):
            with self.subTest(value=value), self.assertRaises(ValueError): latency_check(None, value)

    def test_options_have_no_manufactured_cloud_metrics(self):
        for row in evaluate()['rows']:
            self.assertEqual(set(row['measurements']), set(METRICS))
            self.assertTrue(all(v is None for v in row['measurements'].values()))
            self.assertEqual(row['latency_status'], 'NEEDS_MEASUREMENT')
            self.assertIsNone(row['measured_cost'])

    def test_candidates_never_certify_deployment_or_winner(self):
        r = evaluate()
        self.assertIsNone(r['performance_winner'])
        self.assertTrue(all(x['deployment_status'] == 'NOT_VERIFIED' for x in r['rows']))

    def test_missing_state_contract_excludes(self):
        option = copy.deepcopy(self.options[0]); option['durable_state'] = False
        self.assertEqual(assess(option, self.needs)['decision'], 'EXCLUDED')

    def test_runtime_change_requires_project_regression(self):
        option = copy.deepcopy(self.options[0]); option['orchestrator'] = 'antigravity_sdk'
        self.assertIn('RUNTIME_CHANGE_REQUIRES_REGRESSION', assess(option, self.needs)['reasons'])

    def test_options_are_not_mutated(self):
        original = copy.deepcopy(self.options[0])
        assess(self.options[0], self.needs)
        self.assertEqual(original, self.options[0])

    def test_schema_and_duplicate_ids_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            p = Path(tmp) / 'options.json'
            for doc in ({'schema_version':'unknown','options':self.options},
                        {'schema_version':'local-stack-matrix-v1','options':[self.options[0],self.options[0]]}):
                p.write_text(json.dumps(doc))
                with self.assertRaises(ValueError): read_options(p)

    def test_numeric_flags_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            p = Path(tmp) / 'options.json'
            bad = copy.deepcopy(self.options); bad[0]['atomic_changes'] = 1
            p.write_text(json.dumps({'schema_version':'local-stack-matrix-v1','options':bad}))
            with self.assertRaises(ValueError): read_options(p)

    def test_unknown_profile_rejected(self):
        with self.assertRaises(ValueError): evaluate('everyone')

    def test_current_source_and_options_hashes_are_present(self):
        r = evaluate()
        for key in ('source_sha256', 'options_sha256'):
            self.assertRegex(r[key], '^[0-9a-f]{64}$')

    def test_output_is_not_overwritten(self):
        with tempfile.TemporaryDirectory() as tmp:
            p = Path(tmp) / 'run'
            write_report(evaluate(), p, 'decisions.json')
            with self.assertRaises(FileExistsError): write_report(evaluate(), p, 'decisions.json')

    def test_probe_bounds_rejected(self):
        for n in (0, 21, True):
            with self.subTest(n=n), self.assertRaises(ValueError): measure_local(n)

    def test_real_local_probe_does_not_become_cloud_measurement(self):
        r = measure_local(1)
        self.assertEqual(r['origin'], 'local_process_measurement')
        self.assertEqual(len(r['samples']), 1)
        self.assertGreater(r['samples'][0]['fresh_process_wall_ms'], 0)
        self.assertIsNone(r['cloud_run_cold_start_p95_ms'])
        self.assertIsNone(r['model_latency_ms'])
        self.assertEqual(r['network_calls'], 0)

    def test_cli_eval_and_probe_are_separate(self):
        script = ROOT / 'stack_matrix.py'
        r = subprocess.run([sys.executable, str(script), '--eval', '--profile','governed'], capture_output=True, text=True)
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertEqual(json.loads(r.stdout)['profile'], 'governed')
        bad = subprocess.run([sys.executable, str(script), '--probe', '--profile','governed'], capture_output=True, text=True)
        self.assertEqual(bad.returncode, 2)

    def test_source_imports_only_standard_library(self):
        tree = ast.parse((ROOT / 'stack_matrix.py').read_text())
        names = set()
        for node in ast.walk(tree):
            if isinstance(node, ast.Import): names.update(n.name.split('.')[0] for n in node.names)
            elif isinstance(node, ast.ImportFrom) and node.module: names.add(node.module.split('.')[0])
        self.assertFalse(names - sys.stdlib_module_names)


if __name__ == '__main__':
    unittest.main()
