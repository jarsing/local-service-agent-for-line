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

def find_dataset_path() -> Path:
    candidates = [
        Path(__file__).resolve().parents[2] / 'eval/local20.json',
        Path(__file__).resolve().parent / 'eval/local20.json',
        Path(__file__).resolve().parent.parent / 'eval/local20.json',
        Path(__file__).resolve().parent / 'local20.json',
    ]
    for p in candidates:
        if p.exists():
            return p
    return candidates[0]


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
        selected = select_cases(find_dataset_path())
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

    def test_adapt_genai_usage_strict_missing_fields(self):
        # Missing prompt tokens fails
        with self.assertRaises(ValueError):
            adapt_genai_usage({'candidates_token_count': 100, 'thoughts_token_count': 0})
        # Missing candidates tokens fails
        with self.assertRaises(ValueError):
            adapt_genai_usage({'prompt_token_count': 100, 'thoughts_token_count': 0})
        # Missing thoughts tokens fails if thinking_budget is not explicitly 0
        raw_no_thoughts = {
            'prompt_token_count': 100,
            'candidates_token_count': 50,
            'cached_content_token_count': 0,
            'grounding_used': False
        }
        with self.assertRaises(ValueError):
            adapt_genai_usage(raw_no_thoughts)
        # When thinking_budget=0 is explicitly declared, thoughts count can be safely inferred as 0
        adapted_zero = adapt_genai_usage(raw_no_thoughts, thinking_budget=0)
        self.assertEqual(adapted_zero['thoughts_token_count'], 0)

    def test_evaluate_latency_budget(self):
        # Default 2000ms SLA (LINE Webhook standard):
        # 1200ms -> SAFE (remaining 800ms >= 500ms warning margin)
        safe = evaluate_latency_budget(1200)
        self.assertEqual(safe['status'], 'SAFE')
        self.assertTrue(safe['within_budget'])
        self.assertEqual(safe['budget_ms'], 2000)

        # 1700ms -> WARNING (remaining 300ms < 500ms margin)
        warn = evaluate_latency_budget(1700)
        self.assertEqual(warn['status'], 'WARNING')
        self.assertTrue(warn['within_budget'])

        # 2100ms -> TIMEOUT_RISK (exceeded 2000ms)
        risk = evaluate_latency_budget(2100)
        self.assertEqual(risk['status'], 'TIMEOUT_RISK')
        self.assertFalse(risk['within_budget'])

        # Unmeasured latency
        unmeasured = evaluate_latency_budget(None)
        self.assertEqual(unmeasured['status'], 'NOT_MEASURED')
        self.assertIsNone(unmeasured['latency_ms'])

        # Custom budget (e.g. 5000ms agent round)
        custom_safe = evaluate_latency_budget(2500, budget_ms=5000, warning_margin_ms=1000)
        self.assertEqual(custom_safe['status'], 'SAFE')

    def test_format_cost_summary(self):
        priced = price_row(self.row, self.rate, Decimal('32'))
        summary_str = format_cost_summary(priced)
        self.assertIn('gemini-2.5-flash', summary_str)
        self.assertIn('1000 in', summary_str)
        self.assertIn('NT$', summary_str)

    def test_imported_capture_strict_hash_validation(self):
        valid_sha = 'a' * 64
        valid_commit = '16c93739b7fc2e68d6a0c4548bdd565895b93322'
        base_row = {
            'origin': 'imported_capture',
            'case_id': 'local11',
            'input_sha256': valid_sha,
            'model_id': 'gemini-2.5-flash',
            'endpoint': 'generateContent',
            'prompt_sha256': valid_sha,
            'tools_sha256': valid_sha,
            'catalog_sha256': valid_sha,
            'scorer_sha256': valid_sha,
            'code_sha': valid_commit,
            'config_base_sha256': valid_sha,
            'raw_record_sha256': valid_sha,
            'grade_record_sha256': valid_sha,
            'thinking_budget': 0,
            'attempts': 1,
            'contract_status': 'PASS',
            'latency_scope': 'agent_round',
            'latency_ms': 1200,
            'usage': self.row['usage']
        }
        # Valid row prices successfully
        priced = price_row(base_row, self.rate, Decimal(32))
        self.assertEqual(priced['cost_status'], 'ESTIMATED_FROM_IMPORTED_USAGE')

        # Placeholder string like '<待同次執行回填>' is strictly rejected
        bad_placeholder = dict(base_row, raw_record_sha256='<待同次執行回填>')
        with self.assertRaises(ValueError):
            price_row(bad_placeholder, self.rate, Decimal(32))

        # Malformed short SHA is rejected
        bad_short = dict(base_row, prompt_sha256='abcdef')
        with self.assertRaises(ValueError):
            price_row(bad_short, self.rate, Decimal(32))

        # Malformed commit SHA is rejected
        bad_commit = dict(base_row, code_sha='not-a-git-sha!')
        with self.assertRaises(ValueError):
            price_row(bad_commit, self.rate, Decimal(32))

    def test_generate_cases_template(self):
        templates = generate_cases_template(find_dataset_path())
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
