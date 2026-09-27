import json
import unittest
from . import messages
from .places import PlacesCatalog
from .test_support import MemoryCase

class MessageTests(MemoryCase):
    def test_three_help_actions(self):
        r=messages.help_card();buttons=r['contents']['footer']['contents']
        self.assertEqual([b['action']['label'] for b in buttons],['查活動','查蔬食','留下服務詢問'])
    def test_consent_card_is_pending(self):
        p=self.memory.propose(self.actor,'vegan','x');r=messages.consent_card(p)
        self.assertIn('尚未寫入',json.dumps(r,ensure_ascii=False));self.assertNotIn('已記住',json.dumps(r,ensure_ascii=False))
    def test_alt_has_useful_state(self):
        r=messages.memory_card(self.memory.inspect(self.actor))
        self.assertIn('沒有保存',r['altText'])
    def test_exact_diet_source_in_result(self):
        r=PlacesCatalog().search('彰化市','vegan')
        self.assertIn('foodpanda',json.dumps(messages.format_places(r)))
    def test_completed_campaign_no_claim_closed_shop(self):
        from datetime import datetime
        r=PlacesCatalog().search(now=datetime.fromisoformat('2026-10-01T12:00:00+08:00'))
        s=json.dumps(messages.format_places(r),ensure_ascii=False)
        self.assertIn('集章期間已截止',s);self.assertNotIn('店家已歇業',s)
    def test_no_uri_or_model_layout(self):
        r=messages.help_card('{"type":"uri","uri":"bad"}')
        self.assertNotIn('bad',json.dumps(r));self.assertNotIn('"type": "uri"',json.dumps(r))
    def test_budget_rejects_long_postback(self):
        with self.assertRaises(ValueError): messages.action('label','x'*301,'display')
    def test_current_conditions_do_not_claim_saved(self):
        r=PlacesCatalog().search('花壇鄉','vegetarian');r['preference_origin']='this_turn'
        self.assertNotIn('已套用你同意',json.dumps(messages.format_places(r),ensure_ascii=False))
