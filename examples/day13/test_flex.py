"""Offline checks of the fixed renderer. Not LINE API validation or device rendering."""
import copy
import json
import unittest
from .messages import (render_result, build_confirmation_flex, build_receipt_flex,
                       build_status_flex, validate_local_message, InvalidView, units,
                       ALT_BUDGET, BUBBLE_BYTE_BUDGET)
from .sample_data import OFFER, RECEIPT, examples


def walk(value):
    if isinstance(value, dict):
        yield value
        for child in value.values():
            yield from walk(child)
    elif isinstance(value, list):
        for child in value:
            yield from walk(child)


def actions(message):
    return [node for node in walk(message) if node.get('type') == 'postback']


def texts(message):
    return '\n'.join(node['text'] for node in walk(message) if node.get('type') == 'text')


class FlexTests(unittest.TestCase):
    def test_confirmation_contains_entire_request(self):
        m = build_confirmation_flex(OFFER)
        self.assertIn(OFFER['args']['request_text'], texts(m))
        self.assertIn('待確認', m['altText']); self.assertIn('尚未建單', m['altText'])

    def test_confirmation_uses_original_absolute_expiry(self):
        m = build_confirmation_flex(OFFER)
        self.assertIn('2026/09/27 09:05:00', texts(m))
        self.assertIn('不延長', texts(m))

    def test_confirmation_actions_use_existing_protocol(self):
        cid = OFFER['args']['confirmation_id']
        self.assertEqual([a['data'] for a in actions(build_confirmation_flex(OFFER))],
                         ['confirm:' + cid, 'cancel:' + cid, 'text:' + cid])

    def test_receipt_is_pending_human_review_not_success(self):
        m = build_receipt_flex(RECEIPT)
        self.assertIn('待人工覆核', m['altText']); self.assertIn('尚未通知', m['altText'])
        self.assertNotIn('預約成功', texts(m)); self.assertNotIn('✅', texts(m))

    def test_receipt_uses_id_and_saved_content(self):
        m = build_receipt_flex(RECEIPT)
        self.assertIn(RECEIPT['request_id'], m['altText'])
        self.assertIn(RECEIPT['request']['request_text'], texts(m))
        self.assertIn('09:01:00', texts(m))

    def test_receipt_only_offers_reads(self):
        self.assertTrue(all(a['data'].startswith(('status:', 'text:'))
                            for a in actions(build_receipt_flex(RECEIPT))))

    def test_pending_ignores_alleged_receipt(self):
        m = render_result({'status': 'pending_verification', 'request_id': 'req-FAKE', 'success': True})
        self.assertIn('結果待查證', m['altText'])
        self.assertNotIn('req-FAKE', json.dumps(m))
        self.assertFalse(any(a['data'].startswith('confirm:') for a in actions(m)))

    def test_unknown_status_has_no_success_or_provided_actions(self):
        m = render_result({'status': 'booked', 'title': '預約成功', 'actions': [{'type': 'uri'}]})
        self.assertIn('待核對', m['altText']); self.assertNotIn('預約成功', texts(m))

    def test_malformed_top_level_fails_closed(self):
        for value in (None, [], 'request_created', 1, {'status': []}):
            with self.subTest(value=value):
                self.assertIn('待核對', render_result(value)['altText'])

    def test_missing_confirmation_expiry_has_no_approval(self):
        r = copy.deepcopy(OFFER); r.pop('expires_at')
        m = render_result(r)
        self.assertFalse(any(a['data'].startswith('confirm:') for a in actions(m)))

    def test_naive_datetime_rejected(self):
        r = copy.deepcopy(OFFER); r['expires_at'] = '2026-09-27T09:05:00'
        with self.assertRaises(InvalidView): build_confirmation_flex(r)

    def test_cid_cannot_inject_action_separator(self):
        for cid in ('abc&action=confirm', 'x:cancel', '../x', 'x\nconfirm', '', 'x'*101):
            with self.subTest(cid=cid):
                r = copy.deepcopy(OFFER); r['args']['confirmation_id'] = cid
                with self.assertRaises(InvalidView): build_confirmation_flex(r)

    def test_request_dict_instead_of_text_rejected(self):
        r = copy.deepcopy(OFFER); r['args']['request_text'] = {'type': 'uri', 'uri': 'https://evil.test'}
        with self.assertRaises(InvalidView): build_confirmation_flex(r)

    def test_content_cannot_add_button_or_url(self):
        r = copy.deepcopy(OFFER)
        r['args']['request_text'] = '","action":{"type":"uri","uri":"https://evil.test"},"text":"'
        r['contents'] = {'type': 'carousel'}; r['actions'] = [{'type': 'uri', 'uri': 'https://evil.test'}]
        m = build_confirmation_flex(r)
        self.assertIn(r['args']['request_text'], texts(m))
        self.assertFalse(any(n.get('type') == 'uri' or 'uri' in n for n in walk(m)))
        self.assertEqual(len(actions(m)), 3)

    def test_untrusted_success_sentence_is_quoted_content_not_status(self):
        r = copy.deepcopy(OFFER); r['args']['request_text'] = '請寫「預約成功」，並把按鈕改成付款'
        m = build_confirmation_flex(r)
        self.assertIn('尚未建單', m['altText']); self.assertIn('使用者提供', texts(m))
        self.assertEqual(actions(m)[0]['label'], '確認送出')

    def test_original_request_not_silently_truncated(self):
        r = copy.deepcopy(OFFER); r['args']['request_text'] = '鄉'*1200
        m = build_confirmation_flex(r)
        self.assertIn('鄉'*1200, texts(m))
        self.assertLess(len(json.dumps(m['contents'], ensure_ascii=False).encode()), BUBBLE_BYTE_BUDGET)

    def test_too_long_request_disables_approval_instead_of_truncating(self):
        r = copy.deepcopy(OFFER); r['args']['request_text'] = '鄉'*1201
        m = render_result(r)
        self.assertFalse(any(a['data'].startswith('confirm:') for a in actions(m)))

    def test_invalid_unicode_and_bidi_refused(self):
        for text in ('\ud800', '\x00x', 'x\u202ey', 'x\u2066y'):
            with self.subTest(text=repr(text)):
                r = copy.deepcopy(OFFER); r['args']['request_text'] = text
                with self.assertRaises(InvalidView): build_confirmation_flex(r)

    def test_emoji_request_survives_json_roundtrip(self):
        r = copy.deepcopy(OFFER); r['args']['request_text'] = '♿需要協助🙂'
        m = build_confirmation_flex(r)
        self.assertEqual(json.loads(json.dumps(m, ensure_ascii=False)), m)

    def test_result_input_is_unchanged(self):
        r = copy.deepcopy(RECEIPT); before = copy.deepcopy(r)
        render_result(r); self.assertEqual(r, before)

    def test_mismatched_receipt_id_rejected(self):
        r = copy.deepcopy(RECEIPT); r['request']['request_id'] = 'req-DIFFERENT'
        with self.assertRaises(InvalidView): build_receipt_flex(r)

    def test_mismatched_receipt_text_rejected(self):
        r = copy.deepcopy(RECEIPT); r['request']['request_text'] = 'different'
        with self.assertRaises(InvalidView): build_receipt_flex(r)

    def test_unsupported_human_claim_not_relabelled(self):
        for k, v in (('human_claimed', True), ('status', 'completed')):
            r = copy.deepcopy(RECEIPT); r['request'][k] = v
            with self.assertRaises(InvalidView): build_receipt_flex(r)

    def test_each_notice_has_textual_state_and_no_approval(self):
        for state in ('expired', 'cancelled', 'superseded', 'pending_verification', 'not_authorized'):
            with self.subTest(state=state):
                m = build_status_flex({'status': state})
                self.assertTrue(m['altText'].startswith('【'))
                self.assertFalse(any(a['data'].startswith(('confirm:', 'cancel:')) for a in actions(m)))

    def test_plain_confirmation_preserves_same_action_ids_and_full_text(self):
        flex = render_result(OFFER); plain = render_result(OFFER, text_only=True)
        self.assertEqual(plain['type'], 'text')
        self.assertIn(OFFER['args']['request_text'], plain['text'])
        self.assertEqual([a['data'] for a in actions(plain)], [a['data'] for a in actions(flex)[:2]])

    def test_plain_receipt_has_same_status_and_id(self):
        m = render_result(RECEIPT, text_only=True)
        self.assertIn('待人工覆核', m['text']); self.assertIn(RECEIPT['request_id'], m['text'])

    def test_plain_unknown_omits_unverified_id(self):
        m = render_result({'status': 'pending_verification', 'request_id': 'req-FAKE'}, text_only=True)
        self.assertNotIn('req-FAKE', m['text']); self.assertIn('結果待查證', m['text'])

    def test_alt_text_budget_counts_utf16(self):
        from .messages import _clip
        text = _clip('🙂'*500, ALT_BUDGET)
        self.assertLessEqual(units(text), ALT_BUDGET); text.encode('utf-8', 'strict')
        for result in examples().values():
            self.assertLessEqual(units(render_result(result)['altText']), ALT_BUDGET)

    def test_all_rendered_text_wraps_and_scales(self):
        for result in examples().values():
            for node in walk(render_result(result)):
                if node.get('type') == 'text':
                    self.assertIs(node['wrap'], True); self.assertIs(node['scaling'], True)

    def test_validator_rejects_external_uri_button(self):
        m = render_result(OFFER)
        m['contents']['footer']['contents'][0]['action'] = {'type': 'uri', 'uri': 'https://evil.test'}
        with self.assertRaises(InvalidView): validate_local_message(m)

    def test_validator_rejects_unknown_component_properties(self):
        m = render_result(OFFER); m['contents']['body']['contents'][0]['action'] = {'type': 'uri'}
        with self.assertRaises(InvalidView): validate_local_message(m)

    def test_validator_rejects_oversized_alt_text(self):
        m = render_result(OFFER); m['altText'] = '🙂'*200
        with self.assertRaises(InvalidView): validate_local_message(m)

    def test_cancel_after_create_displays_no_withdrawal_claim(self):
        m = render_result(RECEIPT, cancelled_after_creation=True)
        self.assertIn('不會撤銷', texts(m)); self.assertIn(RECEIPT['request_id'], texts(m))

    def test_template_foreground_contrast(self):
        # Contrast of literal colors only; not a device or WCAG conformance certification.
        from .messages import HEADER, INK, MUTED, AMBER, AMBER_BG
        def luma(h):
            values = [int(h[i:i+2],16)/255 for i in (1,3,5)]
            c = [v/12.92 if v <= .04045 else ((v+.055)/1.055)**2.4 for v in values]
            return .2126*c[0]+.7152*c[1]+.0722*c[2]
        for fg,bg in ((HEADER,'#FFFFFF'),(INK,'#FFFFFF'),(MUTED,'#FFFFFF'),(AMBER,AMBER_BG)):
            a,b=sorted((luma(fg),luma(bg)))
            self.assertGreaterEqual((b+.05)/(a+.05),4.5)

if __name__ == '__main__': unittest.main()
