"""唯讀公開資料工具：活動截止不刪店家；列於快照不等於現在營業。"""
from __future__ import annotations
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path

DIETS = {'any':'不限','vegetarian':'蔬食（未指定細類）','vegan':'全素','ovo_lacto':'蛋奶素',
         'lacto':'奶素','allium':'五辛素','friendly':'蔬食友善'}
ALIASES = {'':'any','不限':'any','蔬食':'vegetarian','素食':'vegetarian','全素':'vegan','純素':'vegan',
           '蛋奶素':'ovo_lacto','奶素':'lacto','五辛素':'allium','蔬食友善':'friendly'}

def diet(value: str, *, allow_any=True) -> str:
    if not isinstance(value,str) or len(value)>40: raise ValueError('INVALID_DIET')
    result=ALIASES.get(value.strip(),value.strip())
    if result not in DIETS or (not allow_any and result=='any'): raise ValueError('INVALID_DIET')
    return result

def bounded(value, name, maximum=80):
    if not isinstance(value,str) or len(value)>maximum or any(ord(c)<32 for c in value):
        raise ValueError('INVALID_'+name.upper())
    return value.strip()

class PlacesCatalog:
    def __init__(self, path:Path|None=None):
        raw=(path or Path(__file__).with_name('data')/'places.json').read_bytes()
        self.data=json.loads(raw);self.sha256=hashlib.sha256(raw).hexdigest()
        if self.data.get('schema_version')!=1: raise ValueError('CATALOG_SCHEMA')
        ids=set()
        for p in self.data['places']:
            if p['place_id'] in ids: raise ValueError('DUPLICATE_PLACE')
            ids.add(p['place_id'])
            for d in p['dietary_options']:
                diet(d,allow_any=False)
                if p['dietary_evidence'][d] not in self.data['sources']: raise ValueError('MISSING_SOURCE')
            for sid in p['field_sources'].values():
                if sid not in self.data['sources']: raise ValueError('MISSING_SOURCE')

    def campaign(self, now=None):
        now=now or datetime.now(timezone.utc)
        if now.tzinfo is None: raise ValueError('AWARE_TIME_REQUIRED')
        c=self.data['campaign']
        start=datetime.fromisoformat(c['starts_at']);end=datetime.fromisoformat(c['ends_at'])
        state='not_started' if now<start else 'active_by_announcement' if now<end else 'ended'
        return {**c,'status':state,'evaluated_at':now.isoformat()}

    def search(self, area='', dietary_type='', keyword='', *, now=None):
        area=bounded(area,'area');keyword=bounded(keyword,'keyword');d=diet(dietary_type)
        aliases={'花壇':'花壇鄉','彰化市區':'彰化市','彰化縣花壇鄉':'花壇鄉'}
        area=aliases.get(area,area)
        base={'tool':'search_local_places','query':{'area':area,'dietary_type':d,'keyword':keyword},
              'catalog_version':self.data['catalog_version'],'catalog_sha256':self.sha256,
              'selection':self.data['selection'],'campaign':self.campaign(now),
              'available_areas':sorted({p['area'] for p in self.data['places']}),
              'unknown_fields':['open_now','walking_distance_m','coordinates','accessibility'],
              'sources':self.data['sources']}
        if area in ('附近','這附近','集合點附近','花壇集合點附近','彰化'):
            return {**base,'status':'needs_area','places':[], 'total':0,
                    'message':'請指定鄉鎮。本資料沒有集合點座標與步行路線，無法判斷最近或少走路。'}
        rows=[p for p in self.data['places'] if (not area or p['area']==area)
              and (d=='any' or d in p['dietary_options'])
              and (not keyword or keyword.casefold() in (p['name']+' '+p['address']).casefold())]
        rows=sorted(rows,key=lambda p:p['place_id'])
        # Fresh JSON copy: caller cannot mutate the source catalog.
        return json.loads(json.dumps({**base,'status':'ok' if rows else 'not_found','places':rows[:5],
            'total':len(rows),'message':'依來源條件比對，不是距離或營業中排名。' if rows else
            '這份精選快照沒有符合資料；可改查其他已收錄區域，不代表當地沒有店家。'},ensure_ascii=False))

def search_local_places(area:str='',dietary_type:str='',keyword:str='')->dict:
    """查精選公開蔬食店家。area 為鄉鎮；dietary_type 是明示素別；keyword 比對店名／地址。
    空條件不限；來源未記載的嚴格素別不推定。回傳來源、集章時效與未知營業／距離欄位。
    """
    return PlacesCatalog().search(area,dietary_type,keyword)
