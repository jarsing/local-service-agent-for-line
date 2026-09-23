"""服務端回覆政策；獨立實作，不從 Day 1 規格讀取預期答案。"""
from __future__ import annotations
from typing import Any


def pending_verification() -> dict[str, Any]:
    return {
        'reply_state': 'pending_verification',
        'claim_completed': False,
        'next_step': 'reconcile_by_idempotency_key',
        'retry_policy': 'reuse_same_idempotency_key',
    }


def pending_result(observation: str) -> dict[str, Any]:
    # request_created=None 表示本次未能判定，不能因逾時填 False。
    return {'status': 'pending_verification', **pending_verification(),
            'observation': observation, 'request_created': None,
            'human_claimed': False}


def error_result(status: str) -> dict[str, Any]:
    return {'status': status, 'claim_completed': False,
            'request_created': False, 'human_claimed': False}


def client_text(result: dict[str, Any]) -> str:
    """應用端固定狀態文案；不是 Gemini 原文，也不是已送到 LINE 的證據。"""
    if result.get('status') == 'pending_verification':
        return '這次還沒拿到可確認的結果，先保留原送出鍵核對；目前狀態是待查證。'
    if result.get('status') in ('request_created', 'already_created'):
        return f"請求已保存在本機，單號 {result['request_id']}。目前尚未通知真人窗口。"
    return f"本次狀態：{result.get('status', 'unknown')}，請先處理確認或權限問題。"
