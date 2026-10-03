import copy
import tempfile
import unittest
from decimal import Decimal
from pathlib import Path
from .cost_ledger import (
    RateCard, calculate_text_cost, demo_rows, price_row, validate_comparable,
    IDENTITY_KEYS, select_cases, summarize_ledger, adapt_genai_usage,
    evaluate_latency_budget, format_cost_summary, generate_cases_template
)

class LedgerContracts(unittest.TestCase):
    def setUp(self):
        self.rate = RateCard.read(Path(__file__).with_name('pricing.checked.json'))
        self.row = demo_rows()[0]

    def test_official_rate_scope_math(self):
        result = calculate_text_cost(self.row['usage'], self.rate, self.row['model_id'], Decimal('32'))
        self.assertEqual(Decimal(result['raw_usd']), Decimal('0.00055'))
        self.assertEqual(Decimal(result['estimated_twd']), Decimal('0.0176'))

    def test_thinking_charged_once(self):
        row = demo_rows()[1]
        result = calculate_text_cost(row['usage'], self.rate, row['model_id'], Decimal('32'))
        self.assertEqual(result['billed_output_tokens'], 350)
        self.assertEqual(Decimal(result['raw_usd']), Decimal('0.001175'))

    def test_unknown_model_no_fallback_price(self):
        with self.assertRaises(ValueError):
            calculate_text_cost(self.row['usage'], self.rate, 'another-model', Decimal(32))

    def test_missing_thinking_is_not_assumed_zero(self):
        del self.row['usage']['thoughts_token_count']
        with self.assertRaises(ValueError):
            price_row(self.row, self.rate, Decimal(32))

    def test_bad_counts(self):
        for value in (True, -1, 1.2, '10', None):
            with self.subTest(value=value):
                row = copy.deepcopy(self.row)
                row['usage']['prompt_token_count'] = value
                with self.assertRaises(ValueError):
                    price_row(row, self.rate, Decimal(32))

    def test_cache_requires_separate_pricing(self):
        self.row['usage']['cached_content_token_count'] = 10
        with self.assertRaises(ValueError):
            price_row(self.row, self.rate, Decimal(32))

    def test_grounding_is_outside_this_ledger(self):
        self.row['usage']['grounding_used'] = True
        with self.assertRaises(ValueError):
            price_row(self.row, self.rate, Decimal(32))

    def test_output_semantics_must_be_explicit(self):
        self.row['usage']['output_semantics'] = 'includes_thoughts'
        with self.assertRaises(ValueError):
            price_row(self.row, self.rate, Decimal(32))

    def test_unknown_failure_cost_not_zero(self):
        self.row.update(contract_status='FAIL', usage=None)
        result = price_row(self.row, self.rate, Decimal(32))
        self.assertIsNone(result['cost'])
        self.assertFalse(result['quality_eligible'])

    def test_failed_quality_still_keeps_known_cost(self):
        self.row['contract_status'] = 'FAIL'
        result = price_row(self.row, self.rate, Decimal(32))
        self.assertIsNotNone(result['cost'])
        self.assertFalse(result['quality_eligible'])

    def test_synthetic_demo_has_no_latency_or_model_grade(self):
        for row in demo_rows():
            self.assertIsNone(row['latency_ms'])
            self.assertEqual(row['contract_status'], 'NOT_RUN')
            self.assertEqual(row['origin'], 'synthetic_fixture')

    def test_pair_requires_same_identity(self):
        a = {k: 'fixed-' + k for k in IDENTITY_KEYS}
        a.update(attempts=1, thinking_budget=0)
        b = dict(a, thinking_budget=1024)
        validate_comparable(a, b)
        for key in IDENTITY_KEYS:
            with self.subTest(key=key):
                bad = dict(b)
                bad[key] = 'changed'
                with self.assertRaises(ValueError):
                    validate_comparable(a, bad)

    def test_pair_must_keep_attempt_policy(self):
        a = {k: 'same' for k in IDENTITY_KEYS}
        a.update(attempts=1, thinking_budget=0)
        b = dict(a, thinking_budget=1024, attempts=2)
        with self.assertRaises(ValueError):
            validate_comparable(a, b)

    def test_original_case_mapping_is_preserved(self):
        selected = select_cases(Path(__file__).resolve().parents[2] / 'eval/local20.json')
        self.assertEqual([r['case_id'] for r in selected], ['local11', 'local12', 'local19'])

    def test_imported_capture_needs_provenance(self):
        self.row['origin'] = 'imported_capture'
        with self.assertRaises(ValueError):
            price_row(self.row, self.rate, Decimal(32))

    def test_nonfinite_or_zero_fx_is_rejected(self):
        for fx in ('NaN', 'Infinity', '0', '-1'):
            with self.subTest(fx=fx):
                with self.assertRaises(ValueError):
                    price_row(self.row, self.rate, Decimal(fx))

    def test_summarize_ledger_totals(self):
        rows = demo_rows()
        priced = [price_row(r, self.rate, Decimal('32')) for r in rows]
        # Add an unknown usage row
        priced.append({'case_id': 'fail-case', 'contract_status': 'FAIL', 'cost': None})
        summary = summarize_ledger(priced)
        self.assertEqual(summary['total_rows'], 3)
        self.assertEqual(summary['priced_rows'], 2)
        self.assertEqual(summary['missing_usage_rows'], 1)
        self.assertEqual(summary['total_billed_output_tokens'], 100 + 350)
        self.assertEqual(Decimal(summary['total_raw_usd']), Decimal('0.00055') + Decimal('0.001175'))
        self.assertEqual(Decimal(summary['total_estimated_twd']), Decimal('0.0176') + Decimal('0.0376'))

    def test_adapt_genai_usage(self):
        raw = {
            'prompt_token_count': 1200,
            'candidates_token_count': 150,
            'thoughts_token_count': 300,
            'cached_content_token_count': 0,
            'grounding_used': False,
            'output_semantics': 'candidates_excludes_thoughts'
        }
        adapted = adapt_genai_usage(raw)
        self.assertEqual(adapted['prompt_token_count'], 1200)
        self.assertEqual(adapted['thoughts_token_count'], 300)
        # Rejects if semantics is wrong
        bad_raw = dict(raw, output_semantics='includes_thoughts')
        with self.assertRaises(ValueError):
            adapt_genai_usage(bad_raw)

    def test_evaluate_latency_budget(self):
        # Within safe margin (>1500ms remaining of 5000ms budget)
        safe = evaluate_latency_budget(2500, 5000)
        self.assertEqual(safe['status'], 'SAFE')
        self.assertTrue(safe['within_budget'])
        # Warning margin (<1500ms remaining)
        warn = evaluate_latency_budget(4200, 5000)
        self.assertEqual(warn['status'], 'WARNING')
        self.assertTrue(warn['within_budget'])
        # Timeout risk (exceeded 5000ms)
        risk = evaluate_latency_budget(5500, 5000)
        self.assertEqual(risk['status'], 'TIMEOUT_RISK')
        self.assertFalse(risk['within_budget'])

    def test_format_cost_summary(self):
        priced = price_row(self.row, self.rate, Decimal('32'))
        summary_str = format_cost_summary(priced)
        self.assertIn('gemini-2.5-flash', summary_str)
        self.assertIn('1000 in', summary_str)
        self.assertIn('NT$', summary_str)

    def test_generate_cases_template(self):
        dataset_path = Path(__file__).resolve().parents[2] / 'eval/local20.json'
        templates = generate_cases_template(dataset_path)
        self.assertEqual(len(templates), 6)
        # Check that we have A and B for local11, local12, local19
        cases = [(r['case_id'], r['setting'], r['thinking_budget']) for r in templates]
        expected = [
            ('local11', 'A', 0), ('local11', 'B', 1024),
            ('local12', 'A', 0), ('local12', 'B', 1024),
            ('local19', 'A', 0), ('local19', 'B', 1024)
        ]
        self.assertEqual(cases, expected)

if __name__ == '__main__':
    unittest.main()
