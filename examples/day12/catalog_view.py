"""沿用 Day 9 教學快照；不把活動地點改稱集合點，也不改寫歷史日期。"""
import json
from .inherit import REPO, search_catalog

class CatalogView:
    def __init__(self):
        source = REPO / 'examples/day09/fixtures.json'
        raw = json.loads(source.read_text(encoding='utf-8'))
        self.snapshot = raw['snapshots'][raw['default_label']]
        self.event = self.snapshot['event']
        self.source = 'Day 9 fixtures.json / snapshots/' + raw['default_label']
        # 只建立查詢 view；Day 5 load_catalog 的原始 schema 沒有被偷偷放寬。
        # 直接重用 search_catalog，並保留此快照缺少 meeting_point 的事實。
        self.data = {'version': self.snapshot['catalog_version'], 'events': [{
            **self.event, 'meeting_point': None, 'meeting_time': None,
            'accessibility': None, 'source': self.source,
            'data_scope': 'historical_teaching_snapshot',
        }]}

    def search(self, args):
        return search_catalog(self.data, args)

    def format_result(self, result):
        if result.get('status') != 'ok' or not result.get('events'):
            return '這份教學快照沒有符合條件的活動。可以用「花壇場次」查詢；它不是即時活動／預約名單。'
        e = result['events'][0]
        return (f'【教學快照，非目前報名資訊】\n{e["name"]}｜{e["area"]}\n'
                f'資料日期：{e["date"]}\n活動時段：{e["time"]}\n'
                f'活動地點：{e["venue"]}\n集合時間與集合點：這份快照未提供。\n'
                f'來源：{e["source"]}\n'
                '需要留下詢問，可輸入「需要協助：」加上內容；接著會先請你確認。')
