"""明示模式與核准；雲端不靜默退回 SQLite 或腳本模型。"""
from dataclasses import dataclass
import os

@dataclass(frozen=True)
class Settings:
    backend: str
    project: str
    namespace: str
    sqlite_path: str
    destination: str
    channel_secret: str
    channel_token: str
    actor_key: str
    allowed_users: tuple[str, ...]
    model_mode: str = 'stub'
    model_id: str = ''
    approve_external: bool = False
    model_daily_limit: int = 10

    def validate(self):
        if self.backend not in ('sqlite-test', 'emulator', 'cloud'):
            raise ValueError('LOCAL_BACKEND 必須明示。')
        if self.model_mode not in ('stub', 'gemini'):
            raise ValueError('LOCAL_MODEL_MODE 必須是 stub 或 gemini。')
        if not self.destination or not self.allowed_users or any(not u for u in self.allowed_users):
            raise ValueError('需要 LINE destination 與測試者白名單。')
        if not self.channel_secret or len(self.actor_key.encode()) < 32:
            raise ValueError('需要 LINE 簽章 secret 與至少 32 bytes 的穩定身分 HMAC key。')
        if not 1 <= self.model_daily_limit <= 50:
            raise ValueError('本篇每日每位測試者模型回合上限為 1～50。')
        if self.backend == 'cloud' and not self.approve_external:
            raise ValueError('正式 Firestore 需要明示核准。')
        if self.model_mode == 'gemini' and (not self.model_id or not self.approve_external):
            raise ValueError('真實 Gemini 需要指定模型及外部呼叫核准。')
        if os.environ.get('K_SERVICE') and (self.backend != 'cloud' or self.model_mode != 'gemini'):
            raise ValueError('Cloud Run 展示不可採用本機替身模式。')
        return self

    @classmethod
    def from_env(cls):
        def need(name):
            value = os.environ.get(name, '')
            if not value:
                raise ValueError('缺少必要設定：' + name)
            return value
        return cls(
            backend=need('LOCAL_BACKEND'), project=os.environ.get('GOOGLE_CLOUD_PROJECT', ''),
            namespace=need('LOCAL_NAMESPACE'),
            sqlite_path=os.environ.get('LOCAL_SQLITE_PATH', 'output/day12/local.sqlite3'),
            destination=need('LINE_DESTINATION'), channel_secret=need('LINE_CHANNEL_SECRET'),
            channel_token=os.environ.get('LINE_CHANNEL_ACCESS_TOKEN', ''),
            actor_key=need('LOCAL_ACTOR_KEY'),
            allowed_users=tuple(x.strip() for x in need('LINE_ALLOWED_USER_IDS').split(',') if x.strip()),
            model_mode=need('LOCAL_MODEL_MODE'), model_id=os.environ.get('GEMINI_MODEL', ''),
            approve_external=os.environ.get('LOCAL_APPROVE_EXTERNAL') == 'yes',
            model_daily_limit=int(os.environ.get('LOCAL_MODEL_DAILY_LIMIT', '10')),
        ).validate()
