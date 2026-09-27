"""固定 Flex 與文字：沒有合併模型 layout、URL 或 action。"""
from datetime import datetime
from zoneinfo import ZoneInfo
from .places import DIETS

MENU=[('查活動','d14:events','查詢地方活動'),('查蔬食','d14:places','尋找蔬食店家'),
      ('留下服務詢問','d14:enquiry','留下服務詢問')]

def text(value):
    if not isinstance(value,str) or len(value.encode('utf-16-le'))//2>4500: raise ValueError('TEXT_BUDGET')
    return {'type':'text','text':value}

def action(label,data,display):
    if len(label.encode('utf-16-le'))//2>20 or len(data)>300: raise ValueError('ACTION_BUDGET')
    return {'type':'postback','label':label,'data':data,'displayText':display}

def card(title,body,buttons):
    actions=[action(*b) for b in buttons]
    alt=(title+'。'+body).replace('\n',' ')[:340]
    return {'type':'flex','altText':alt,'contents':{'type':'bubble',
        'body':{'type':'box','layout':'vertical','spacing':'md','contents':[
            {'type':'text','text':title,'weight':'bold','size':'lg','wrap':True,'scaling':True},
            {'type':'text','text':body,'size':'sm','wrap':True,'scaling':True}]},
        'footer':{'type':'box','layout':'vertical','spacing':'sm','contents':[
            {'type':'button','height':'sm','style':'secondary','action':a} for a in actions]}}}

def help_card(reason=''):
    lead='這次查詢暫時沒有取得可用結果。\n' if reason=='query_unavailable' else ''
    return card('先選這次要做什麼',lead+'LOCAL 目前能查活動、找店家及留下詢問，沒有預約功能。\n查詢與留下詢問都不會自動保存飲食偏好。',MENU)

def area_card(areas):
    return card('想找哪個鄉鎮？','目前只有部分公開店家快照；請選區域。距離與步行路線尚未提供。',
                [(a,'d14:area:'+a,'查'+a+'店家') for a in areas[:5]])

def consent_card(p):
    expiry=datetime.fromisoformat(p['expires_at']).astimezone(ZoneInfo('Asia/Taipei')).strftime('%m/%d %H:%M:%S')
    op=p['operation']
    body=(f'未來找店家時使用：{DIETS[p["dietary_type"]]}。\n只保存一項查詢偏好，不保存長輩身分。\n可查看、更正或忘記。尚未寫入偏好庫。' if op=='save' else
          '移除本帳號目前的飲食偏好，之後不再自動套用；原本的 LINE 訊息與已提交服務詢問另行保留。')
    return card('是否同意記住？' if op=='save' else '確認忘記飲食偏好',body+'\n這張確認有效至 '+expiry+'（臺灣時間）。',
                [('同意記住' if op=='save' else '確認忘記','m14:approve:'+p['token'],'同意這次記憶操作'),
                 ('先不要','m14:cancel:'+p['token'],'取消這次記憶操作')])

def memory_card(result):
    state=result['status'];d=result.get('dietary_type')
    if state in ('saved','memory_saved','already_applied'):
        body=('目前偏好：'+DIETS[d]+'。用途：未來在 LOCAL 找店家時使用。') if d else '目前沒有保存飲食偏好。'
    elif state in ('empty','memory_forgotten'): body='目前沒有保存飲食偏好。後續查詢依當次條件，不再自動套用已撤回的值。'
    elif state=='stale_memory_card': body='這張記憶卡已失效，偏好曾被修改、取消或忘記。請查看目前偏好。'
    elif state=='expired_memory_card': body='這張確認已過期，沒有變更偏好。請重新提出。'
    else: body='這次記憶操作已停止，原本已同意的偏好維持原值。'
    return card('你的飲食偏好',body,[('我的偏好','m14:inspect','查看我的偏好'),
        ('更正偏好','m14:update','更正我的飲食偏好'),('忘記偏好','m14:forget','忘記我的飲食偏好')])

def format_places(result):
    if result['status']=='needs_area': return [area_card(result['available_areas'])]
    c=result['campaign'];deadline=datetime.fromisoformat(c['ends_at']).astimezone(ZoneInfo('Asia/Taipei')).strftime('%Y/%m/%d %H:%M');when='集章期間已截止' if c['status']=='ended' else '依公告仍在集章期間' if c['status']=='active_by_announcement' else '集章尚未開始'
    source='已套用你同意的飲食偏好' if result.get('preference_origin')=='consented_memory' else '依本次條件查詢'
    rows=[source+'：'+DIETS[result['query']['dietary_type']]+'。']
    for p in result['places']:
        rows += [p['name']+'｜'+p['area'],p['address'],'電話：'+p['phone'],p['dietary_scope']]
        sid=p['dietary_evidence'].get(result['query']['dietary_type'])
        if sid and sid!='festival_list': rows.append('素別依據：'+result['sources'][sid]['url'])
    if not result['places']: rows.append(result['message'])
    rows += [f'{when}；公告截止為 {deadline}。店家清單不隨集章截止刪除。',
             '這是精選公開快照，不是全縣餐廳排行；現在營業、供餐與步行距離請另確認。',
             '來源：'+result['sources']['festival_list']['url']]
    return [text('\n'.join(rows)),card('接下來', '查詢結果不等於預約或已存偏好。',
        [('我的偏好','m14:inspect','查看我的偏好'),('更正偏好','m14:update','更正我的飲食偏好'),('其他功能','d14:help','查看其他功能')])]
