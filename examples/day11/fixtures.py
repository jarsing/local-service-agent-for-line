"""合成活動與可信入口；不是現場使用者同意、正式活動來源或登入系統。"""
from dataclasses import asdict
from domain import grant_key,catalog_key
from upstream import Actor,Operation

ACTOR=Actor('demo-community','demo-visitor','demo-conversation')

def sample_operation():
    """沿用 Day 9 的 v2 教學快照；日期與內容不是本篇新查到的活動。"""
    import json
    from upstream import REPO
    source = json.loads((REPO / 'examples/day09/fixtures.json').read_text('utf-8'))
    adopted = source['snapshots']['v2']
    event = adopted['event']
    return Operation(draft_id='demo-day11-draft', revision=1, event_id=event['id'],
        catalog_version=adopted['catalog_version'],
        request_text='請問花壇場次的集合地點在哪裡？',
        displayed_event={name: event[name] for name in ('name','area','venue','date','time')})


def seed_authority(store,actor=ACTOR,operation=None):
    """只供獨立合成示範命名空間初始化；不是 Agent 工具。"""
    operation=operation or sample_operation()
    def seed(tx):
        oldg=tx.get('grants',grant_key(actor));oldc=tx.get('catalogs',catalog_key(actor,operation.event_id))
        if oldg or oldc:raise RuntimeError('此示範空間已有資料；請另選新空間，不覆寫權限。')
        tx.create('grants',grant_key(actor),{'actor':{'tenant_id':actor.tenant_id,
            'user_id':actor.user_id},'allowed':True})
        tx.create('catalogs',catalog_key(actor,operation.event_id),{
            'catalog_version':operation.catalog_version,'data_status':'adopted',
            'displayed_event':operation.displayed_event})
    store.atomic(seed)
