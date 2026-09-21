"""Day 8 人機協同確認介面生成器。

生成展示人機確認卡片、版本對照與狀態結果的靜態 CONFIRM.html，
供本機瀏覽器檢視與操作截圖。
"""
from __future__ import annotations

import html
import json
from pathlib import Path
from typing import Any

from adapter import CatalogCatalogState, DEFAULT_EVENT_ID
from confirmation import ConfirmationStore, Identity, Operation, operation_fingerprint


def build_html_report(
    offer: dict[str, Any],
    normal_result: dict[str, Any],
    conflict_result: dict[str, Any],
    output_path: Path | str | None = None,
) -> Path:
    if output_path is None:
        output_path = Path(__file__).parent / "CONFIRM.html"
    ev = offer["operation"]["displayed_event"]
    op = offer["operation"]
    fingerprint = offer["operation_fingerprint"]

    html_content = f"""<!DOCTYPE html>
<html lang="zh-TW">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>LOCAL Day 8｜人機協同內容確認展示</title>
<style>
  :root {{
    --bg: #f8fafc;
    --card-bg: #ffffff;
    --text-main: #0f172a;
    --text-muted: #64748b;
    --border: #e2e8f0;
    --primary: #2563eb;
    --primary-hover: #1d4ed8;
    --success: #16a34a;
    --warning: #d97706;
    --danger: #dc2626;
    --code-bg: #f1f5f9;
  }}
  * {{ box-sizing: border-box; margin: 0; padding: 0; }}
  body {{ font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, "Helvetica Neue", Arial, sans-serif; background: var(--bg); color: var(--text-main); line-height: 1.6; padding: 24px 16px; }}
  .container {{ max-width: 900px; margin: 0 auto; }}
  header {{ margin-bottom: 24px; padding-bottom: 16px; border-bottom: 1px solid var(--border); }}
  h1 {{ font-size: 1.5rem; font-weight: 700; margin-bottom: 8px; }}
  .subtitle {{ color: var(--text-muted); font-size: 0.95rem; }}
  .badge {{ display: inline-block; padding: 4px 10px; border-radius: 9999px; font-size: 0.8rem; font-weight: 600; text-transform: uppercase; }}
  .badge-awaiting {{ background: #fef3c7; color: #92400e; }}
  .badge-success {{ background: #dcfce7; color: #166534; }}
  .badge-warning {{ background: #ffedd5; color: #9a3412; }}

  .card {{ background: var(--card-bg); border: 1px solid var(--border); border-radius: 12px; padding: 20px; margin-bottom: 24px; box-shadow: 0 1px 3px rgba(0,0,0,0.05); }}
  .card-title {{ font-size: 1.15rem; font-weight: 600; margin-bottom: 16px; display: flex; align-items: center; justify-content: space-between; }}

  .field-grid {{ display: grid; grid-template-columns: 140px 1fr; gap: 12px; font-size: 0.95rem; margin-bottom: 16px; }}
  .field-label {{ color: var(--text-muted); font-weight: 500; }}
  .field-value {{ color: var(--text-main); font-weight: 500; }}
  .highlight {{ background: #eff6ff; padding: 2px 6px; border-radius: 4px; font-family: ui-monospace, SFMono-Regular, Menlo, monospace; color: var(--primary); }}

  .btn-group {{ display: flex; gap: 12px; margin-top: 16px; border-top: 1px solid var(--border); padding-top: 16px; }}
  .btn {{ padding: 10px 18px; border-radius: 8px; font-size: 0.9rem; font-weight: 600; cursor: pointer; border: 1px solid transparent; transition: all 0.15s ease; }}
  .btn-primary {{ background: var(--primary); color: #fff; }}
  .btn-primary:hover {{ background: var(--primary-hover); }}
  .btn-outline {{ background: #fff; border-color: var(--border); color: var(--text-main); }}
  .btn-outline:hover {{ background: #f8fafc; }}
  .btn-danger {{ background: #fee2e2; color: var(--danger); border-color: #fecaca; }}

  .code-block {{ background: var(--code-bg); padding: 12px; border-radius: 8px; font-family: ui-monospace, SFMono-Regular, Menlo, monospace; font-size: 0.85rem; overflow-x: auto; margin-top: 12px; }}

  .grid-two {{ display: grid; grid-template-columns: 1fr 1fr; gap: 20px; }}
  @media (max-width: 768px) {{ .grid-two {{ grid-template-columns: 1fr; }} }}
</style>
</head>
<body>
<div class="container">
  <header>
    <div style="display:flex; justify-content:space-between; align-items:center; margin-bottom:8px;">
      <h1>LOCAL Day 8｜人機協同內容確認展示</h1>
      <span class="badge badge-awaiting">AWAITING_CONFIRMATION</span>
    </div>
    <div class="subtitle">Google ADK Tool Confirmation × 應用端版本與操作指紋重新核對</div>
  </header>

  <!-- 待確認卡片 -->
  <section class="card">
    <div class="card-title">
      <span>1. 出示確認請求（由 Gemini + ADK 發起）</span>
      <span class="badge badge-awaiting">待核對 Offer</span>
    </div>
    <div class="field-grid">
      <div class="field-label">目標活動</div>
      <div class="field-value"><strong>{html.escape(ev.get("name", ""))}</strong>（{html.escape(ev.get("area", ""))}・{html.escape(ev.get("venue", ""))}）</div>

      <div class="field-label">活動日期</div>
      <div class="field-value">{html.escape(ev.get("date", ""))}</div>

      <div class="field-label">出示活動時段</div>
      <div class="field-value"><span class="highlight">{html.escape(ev.get("time", ""))}</span></div>

      <div class="field-label">詢問草稿文字</div>
      <div class="field-value">「{html.escape(op.get("request_text", ""))}」</div>

      <div class="field-label">接收窗口</div>
      <div class="field-value">{html.escape(op.get("destination", ""))}</div>

      <div class="field-label">綁定目錄版本</div>
      <div class="field-value"><code>{html.escape(op.get("catalog_version", ""))}</code></div>

      <div class="field-label">操作指紋 (SHA-256)</div>
      <div class="field-value"><code style="font-size:0.8rem;">{fingerprint[:24]}...</code></div>
    </div>

    <div class="btn-group">
      <button class="btn btn-primary" type="button">✔ 確認內容（送出同意）</button>
      <button class="btn btn-outline" type="button">⚡ 模擬等待中切換新版 (08:00~11:00)</button>
      <button class="btn btn-danger" type="button">✖ 取消</button>
    </div>
  </section>

  <!-- 兩情境對照卡片 -->
  <div class="grid-two">
    <section class="card" style="border-top: 4px solid var(--success);">
      <div class="card-title">
        <span>情境 A：資料未變，正常接受</span>
        <span class="badge badge-success">RECORDED</span>
      </div>
      <p style="font-size:0.9rem; color:var(--text-muted); margin-bottom:12px;">
        使用者看過 07:30~11:00，按下確認時伺服器目錄版本仍為 <code>{html.escape(op.get("catalog_version", ""))}</code>。
      </p>
      <div class="field-grid" style="grid-template-columns: 100px 1fr; font-size:0.85rem;">
        <div class="field-label">判定狀態</div>
        <div class="field-value"><strong>{normal_result.get("status")}</strong></div>
        <div class="field-label">執行權限</div>
        <div class="field-value"><code>execution_allowed: {str(normal_result.get("execution_allowed")).lower()}</code></div>
        <div class="field-label">收據版本</div>
        <div class="field-value"><code>{normal_result.get("receipt", {}).get("catalog_version")}</code></div>
      </div>
      <div class="code-block">{json.dumps(normal_result, ensure_ascii=False, indent=2)}</div>
    </section>

    <section class="card" style="border-top: 4px solid var(--warning);">
      <div class="card-title">
        <span>情境 B：等待中換版，拒絕舊版</span>
        <span class="badge badge-warning">VERSION_CHANGED</span>
      </div>
      <p style="font-size:0.9rem; color:var(--text-muted); margin-bottom:12px;">
        使用者看過 07:30~11:00，但在按下前系統已採用 08:00~11:00（版本更新），按鈕送出的舊確認被拒絕。
      </p>
      <div class="field-grid" style="grid-template-columns: 100px 1fr; font-size:0.85rem;">
        <div class="field-label">判定狀態</div>
        <div class="field-value"><strong>{conflict_result.get("status")}</strong></div>
        <div class="field-label">執行權限</div>
        <div class="field-value"><code>execution_allowed: {str(conflict_result.get("execution_allowed")).lower()}</code></div>
        <div class="field-label">處理方式</div>
        <div class="field-value">出示新版時段，提示重新核對</div>
      </div>
      <div class="code-block">{json.dumps(conflict_result, ensure_ascii=False, indent=2)}</div>
    </section>
  </div>
</div>
</body>
</html>
"""
    out = Path(output_path)
    with open(out, "w", encoding="utf-8") as f:
        f.write(html_content)
    return out


def generate_demo_html(output_file: str | Path | None = None) -> Path:
    from datetime import datetime, timezone
    catalog_state = CatalogCatalogState("v1")
    store = ConfirmationStore()
    now = datetime(2026, 9, 22, 1, 0, tzinfo=timezone.utc)
    owner = Identity("demo-user-1", "demo-session-1")

    ev = catalog_state.get_event(DEFAULT_EVENT_ID)
    op = Operation(
        draft_id="draft-handoff-01",
        revision=1,
        event_id=DEFAULT_EVENT_ID,
        catalog_version=catalog_state.catalog_version,
        request_text="請問這場活動的集合地點在哪裡？",
        displayed_event={
            "name": ev["name"],
            "area": ev["area"],
            "venue": ev["venue"],
            "date": ev["date"],
            "time": ev["time"],
        },
    )
    offer = store.issue(
        owner=owner,
        operation=op,
        current_catalog_version=catalog_state.catalog_version,
        data_status=catalog_state.data_status,
        now=now,
    )

    # 模擬情境 A
    normal = store.decide(
        confirmation_id=offer["confirmation_id"],
        actor=owner,
        current_operation=op,
        current_catalog_version=catalog_state.catalog_version,
        data_status="adopted",
        permitted=True,
        approved=True,
        now=now,
    )

    # 模擬情境 B（發出新 offer 後換版）
    store_b = ConfirmationStore()
    offer_b = store_b.issue(
        owner=owner,
        operation=op,
        current_catalog_version="v-0337e2296139",
        data_status="adopted",
        now=now,
    )
    catalog_state.switch_to("v2")
    ev2 = catalog_state.get_event(DEFAULT_EVENT_ID)
    op2 = Operation(
        draft_id="draft-handoff-01",
        revision=1,
        event_id=DEFAULT_EVENT_ID,
        catalog_version=catalog_state.catalog_version,
        request_text="請問這場活動的集合地點在哪裡？",
        displayed_event={
            "name": ev2["name"],
            "area": ev2["area"],
            "venue": ev2["venue"],
            "date": ev2["date"],
            "time": ev2["time"],
        },
    )
    conflict = store_b.decide(
        confirmation_id=offer_b["confirmation_id"],
        actor=owner,
        current_operation=op2,
        current_catalog_version=catalog_state.catalog_version,
        data_status="adopted",
        permitted=True,
        approved=True,
        now=now,
    )

    return build_html_report(offer, normal, conflict, output_path=output_file)


if __name__ == "__main__":
    p = generate_demo_html()
    print(f"Generated demo HTML: {p.resolve()}")
