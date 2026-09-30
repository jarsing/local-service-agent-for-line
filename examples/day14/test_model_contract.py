"""標準函式庫檢查：驗指令／Context 邊界，不把它當 Gemini 自然語言命中率。"""
import json
import unittest
from .model_contract import INSTRUCTION, POLICY_VERSION, session_state, expanded_instruction, instruction_sha256, SUITES
from .places import PlacesCatalog

class ModelContractTests(unittest.TestCase):
    def context(self, dietary='vegetarian', revision=2):
        return session_state({'revision':revision,'dietary_type':dietary,'owner':'SYNTHETIC_PRIVATE_OWNER'},PlacesCatalog())
    def test_context_contains_only_public_catalog_and_revision(self):
        s=self.context();self.assertEqual(set(s),{'day14_preference_revision','day14_catalog_context'})
        c=json.loads(s['day14_catalog_context'])
        self.assertEqual(c['coverage'],'selected_public_records')
        self.assertIn('花壇鄉',c['available_areas'])
    def test_saved_diet_not_injected_into_prompt(self):
        a=self.context('vegan');b=self.context('ovo_lacto')
        self.assertEqual(expanded_instruction(a),expanded_instruction(b))
        self.assertNotIn('SYNTHETIC_PRIVATE_OWNER',expanded_instruction(a))
    def test_revision_is_internal_not_instruction_value(self):
        a=self.context(revision=5);b=self.context(revision=6)
        self.assertNotEqual(a['day14_preference_revision'],b['day14_preference_revision'])
        self.assertEqual(expanded_instruction(a),expanded_instruction(b))
    def test_template_placeholder_is_resolved(self):
        x=expanded_instruction(self.context())
        self.assertNotIn('{day14_catalog_context}',x)
        self.assertIn(PlacesCatalog().data['catalog_version'],x)
    def test_boolean_revision_rejected(self):
        with self.assertRaises(ValueError):self.context(revision=True)
    def test_negative_revision_rejected(self):
        with self.assertRaises(ValueError):self.context(revision=-1)
    def test_policy_is_named_and_hashed(self):
        self.assertEqual(POLICY_VERSION,'day17-service-outcomes-v1')
        self.assertEqual(len(instruction_sha256()),64)
    def test_negation_and_reported_speech_rules_are_present(self):
        # Text-contract coverage only; no assertion about actual model understanding.
        for text in ('不要記住','轉述','條件句','先分開兩個問題'):
            self.assertIn(text,INSTRUCTION)
    def test_no_model_side_approval_capability_is_in_policy(self):
        self.assertIn('再等使用者按明確同意',INSTRUCTION)
        self.assertIn('不建立記憶提案',INSTRUCTION)
    def test_each_live_suite_is_explicit_and_four_calls_max(self):
        for name,cases in SUITES.items():
            self.assertEqual(len(cases),4)
            self.assertEqual(len({c['case'] for c in cases}),4)
    def test_expected_answers_do_not_enter_context(self):
        value=expanded_instruction(self.context())
        for text in ('effective_filter','expected_tool','SYNTHETIC_PRIVATE_OWNER'):
            self.assertNotIn(text,value)
    def test_lifecycle_omission_is_checked_not_just_final_results(self):
        a,b=SUITES['lifecycle'][2:]
        self.assertEqual(a['diet_argument'],'');self.assertEqual(b['diet_argument'],'')
        self.assertEqual(a['effective_filter'],'vegetarian');self.assertEqual(b['effective_filter'],'any')
