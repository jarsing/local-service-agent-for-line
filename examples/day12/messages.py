"""權威欄位由程式呈現，模型不生成單號，也不承諾尚未安排的真人服務。"""
def text_message(text): return {'type':'text','text':text[:4900]}

def offer_message(args):
    cid=args['confirmation_id']
    text=('【教學服務請求確認】\n活動：花壇場次（歷史教學快照）\n'
          f'詢問：{args["request_text"]}\n'
          '按確認後保存這份詢問，以原確認建立時間起算 5 分鐘，查回不延長期限；這不是預約，也尚未通知真人。')
    return {**text_message(text),'quickReply':{'items':[
        {'type':'action','action':{'type':'postback','label':'確認送出','data':'confirm:'+cid,'displayText':'確認送出這份詢問'}},
        {'type':'action','action':{'type':'postback','label':'取消','data':'cancel:'+cid,'displayText':'取消這份詢問'}},
    ]}}

def render_result(result):
    state=result['status']
    if state in ('request_created','already_created'):
        prefix='已保存這份詢問' if state=='request_created' else '找到你原本那份詢問'
        text=(f'{prefix}。\n單號：{result["request_id"]}\n'
              f'內容：{result["request"]["request_text"]}\n'
              '狀態：待真人處理。本示範尚未通知服務窗口。')
        return {**text_message(text),'quickReply':{'items':[
            {'type':'action','action':{'type':'postback','label':'查詢原單','data':'status','displayText':'剛才那單有成功嗎？'}}]}}
    if state=='awaiting_confirmation': return offer_message(result['args'])
    labels={
        'session_not_found':'目前沒有可查回的任務。可以先問「花壇場次在哪裡集合？」。',
        'expired':'原確認已過期，這次沒有新增請求。要繼續，請用「新需求：」重新提出內容並確認。',
        'cancelled':'已取消尚未送出的這份內容。',
        'already_confirmed':'這份內容已確認；取消確認不代表撤回已建立的請求，請先查詢原單。',
        'superseded':'這是較早的確認卡，請使用目前這份確認，或查詢原單。',
        'not_authorized':'目前沒有這項操作權限。',
        'confirmation_not_found':'找不到屬於目前對話的這份確認，請查詢原單。',
        'version_changed':'活動資料版本已變更，請重新查看內容後確認。',
        'content_changed':'確認內容已變更，請重新查看內容後確認。',
        'pending_verification':'目前仍待查證。系統沒有因此另開一張新單；請稍後用「查詢原單」核對。',
    }
    return text_message(labels.get(state,'這次沒有完成新增。請查詢原單，或重新查看確認內容。'))
