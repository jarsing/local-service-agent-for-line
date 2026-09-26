"""先驗原始位元組；身分來自已驗簽的 LINE direct user 事件，不來自模型。"""
import base64
import hashlib
import hmac
from .inherit import Actor

def signature(secret: str, body: bytes) -> str:
    return base64.b64encode(hmac.new(secret.encode(), body, hashlib.sha256).digest()).decode()

def verify_signature(secret: str, body: bytes, given: str) -> bool:
    if not isinstance(given, str):
        return False
    try:
        return hmac.compare_digest(signature(secret, body).encode('ascii'), given.encode('ascii'))
    except UnicodeEncodeError:
        return False

def make_actor(settings, raw_user_id: str) -> Actor:
    # 同一頻道與使用者跨 revision 使用同一 key。此摘要不是登入憑證。
    data = (settings.destination + '\0' + raw_user_id).encode()
    uid = hmac.new(settings.actor_key.encode(), data, hashlib.sha256).hexdigest()
    return Actor(tenant_id='line:' + settings.destination, user_id=uid, session_id='dialog:' + uid)
