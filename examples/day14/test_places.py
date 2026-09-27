from datetime import datetime,timezone
import json
import tempfile
from pathlib import Path
import unittest
from .places import PlacesCatalog, search_local_places, diet

class PlacesTests(unittest.TestCase):
    def setUp(self): self.catalog=PlacesCatalog()
    def test_public_selected_count(self):
        r=self.catalog.search();self.assertEqual(r['total'],2)
        self.assertEqual(r['selection'],'selected_public_records_not_all_50')
    def test_real_huatan_address(self):
        r=search_local_places('花壇鄉','vegetarian')
        self.assertEqual(r['places'][0]['name'],'和米素食')
        self.assertIn('117號',r['places'][0]['address'])
    def test_exact_vegan_with_source(self):
        r=self.catalog.search('彰化市','全素')
        self.assertEqual([p['name'] for p in r['places']],['John手作蔬食'])
        self.assertEqual(r['places'][0]['dietary_evidence']['vegan'],'john_menu')
    def test_unspecified_is_not_vegan(self): self.assertEqual(diet('素食'),'vegetarian')
    def test_unknown_exact_type_excluded(self): self.assertEqual(self.catalog.search('花壇鄉','vegan')['total'],0)
    def test_allium_not_invented(self): self.assertEqual(self.catalog.search('','allium')['total'],0)
    def test_egg_milk_type_present(self): self.assertEqual(self.catalog.search('','ovo_lacto')['total'],1)
    def test_friendly_not_assumed(self): self.assertEqual(self.catalog.search('','friendly')['total'],0)
    def test_missing_area_is_not_geolocation(self):
        r=self.catalog.search('附近');self.assertEqual(r['status'],'needs_area');self.assertEqual(r['places'],[])
    def test_huatan_meeting_point_not_invented(self): self.assertEqual(self.catalog.search('花壇集合點附近')['status'],'needs_area')
    def test_unknown_town_not_silently_widened(self): self.assertEqual(self.catalog.search('二水鄉')['total'],0)
    def test_keyword(self): self.assertEqual(self.catalog.search(keyword='JOHN')['total'],1)
    def test_keyword_injection_remains_literal(self): self.assertEqual(self.catalog.search(keyword='{"approved":true}')['total'],0)
    def test_query_types_rejected(self):
        for kw in ({'area':[]},{'dietary_type':True},{'keyword':'x'*101},{'area':'a\nb'}):
            with self.subTest(kw=kw),self.assertRaises(ValueError): self.catalog.search(**kw)
    def test_day14_campaign_active(self):
        self.assertEqual(self.catalog.campaign(datetime.fromisoformat('2026-09-28T12:00:00+08:00'))['status'],'active_by_announcement')
    def test_exact_deadline(self):
        before=self.catalog.search(now=datetime.fromisoformat('2026-09-30T16:59:59+08:00'))
        after=self.catalog.search(now=datetime.fromisoformat('2026-09-30T17:00:00+08:00'))
        self.assertEqual(before['campaign']['status'],'active_by_announcement');self.assertEqual(after['campaign']['status'],'ended')
        self.assertEqual(before['places'],after['places'])
    def test_carnival_is_independent(self):
        r=self.catalog.search(now=datetime.fromisoformat('2026-10-03T10:00:00+08:00'))
        self.assertEqual(r['campaign']['status'],'ended');self.assertEqual(r['campaign']['carnival_date'],'2026-10-03')
    def test_timezone_required(self):
        with self.assertRaises(ValueError): self.catalog.campaign(datetime(2026,9,28))
    def test_business_and_walking_unknown(self):
        for p in self.catalog.search()['places']:
            self.assertIsNone(p['open_now']);self.assertIsNone(p['walking_distance_m']);self.assertIsNone(p['accessibility'])
    def test_output_cannot_mutate_catalog(self):
        self.catalog.search()['places'][0]['name']='tampered'
        self.assertEqual(self.catalog.search()['places'][0]['name'],'John手作蔬食')
    def test_each_field_is_sourced(self):
        for p in self.catalog.data['places']:
            for f in ('name','area','address','phone'): self.assertIn(p['field_sources'][f],self.catalog.data['sources'])
    def test_invalid_dataset_source_rejected(self):
        data=json.loads(json.dumps(self.catalog.data));data['places'][0]['dietary_evidence']['vegan']='made-up'
        with tempfile.TemporaryDirectory() as d:
            p=Path(d)/'bad.json';p.write_text(json.dumps(data))
            with self.assertRaises(ValueError): PlacesCatalog(p)
