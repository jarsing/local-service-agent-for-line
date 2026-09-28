"""Explicitly approved LINE message validation only; never sends a chat message."""
import argparse
import json
import os
from pathlib import Path
from urllib.request import Request, urlopen
from urllib.error import HTTPError, URLError
from .messages import validate_local_message


def main():
    p = argparse.ArgumentParser()
    p.add_argument('--file', type=Path, required=True)
    p.add_argument('--out', type=Path, required=True)
    p.add_argument('--approve-line-validation', action='store_true')
    a = p.parse_args()
    if not a.approve_line_validation:
        p.error('需 --approve-line-validation；會送出一個真正 LINE API 驗證請求，不發聊天訊息。')
    token = os.environ.get('LINE_CHANNEL_ACCESS_TOKEN')
    if not token:
        p.error('請在私人環境設定 LINE_CHANNEL_ACCESS_TOKEN，不寫在命令列。')
    if a.out.exists():
        p.error('輸出檔已存在，請換新路徑，避免改寫原結果。')
    if a.file.stat().st_size > 65536:
        p.error('只接受小型本篇訊息範例。')
    message = json.loads(a.file.read_text(encoding='utf-8'))
    validate_local_message(message)
    request = Request('https://api.line.me/v2/bot/message/validate/reply',
                      data=json.dumps({'messages': [message]}, ensure_ascii=False).encode(),
                      headers={'Content-Type': 'application/json', 'Authorization': 'Bearer ' + token},
                      method='POST')
    try:
        with urlopen(request, timeout=15) as response:
            status = response.status; body = response.read().decode(); request_id = response.headers.get('x-line-request-id')
    except HTTPError as error:
        status = error.code; body = error.read().decode(errors='replace'); request_id = error.headers.get('x-line-request-id')
    except URLError as error:
        status = None; body = type(error.reason).__name__; request_id = None
    report = {'origin': 'author_line_validation', 'http_status': status, 'response': body,
              'line_request_id': request_id, 'file': a.file.name,
              'scope': 'message object validation, not phone rendering or business completion',
              'passed': status == 200}
    a.out.parent.mkdir(parents=True, exist_ok=True)
    with a.out.open('x', encoding='utf-8') as output:
        json.dump(report, output, ensure_ascii=False, indent=2)
    print(json.dumps({'http_status': status, 'passed': status == 200, 'saved': str(a.out)}, ensure_ascii=False))
    return 0 if status == 200 else 1

if __name__ == '__main__':
    raise SystemExit(main())
