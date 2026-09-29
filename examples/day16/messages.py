"""Never render arbitrary model prose/URLs/actions as a verified receipt."""
from examples.day14.messages import MENU, card, text, format_places


def document_messages(result):
    status = result.get("status")
    if result.get("tool") == "search_local_places":
        # Existing source-backed renderer; not the document's claimed store facts.
        content = format_places(result)
        # Replace management controls with the read/help menu for this document turn.
        return content[:1] + [card(
            "文件僅供查詢", "這份文件沒有替你同意記憶或建立服務單。\n需要其他服務，請由本人重新選擇入口。", MENU)]
    if status == "document_unavailable":
        body = "本次文件查詢暫不可用，並不代表查無資料。請稍後再試或選擇既有功能。"
    elif status == "document_action_denied":
        body = "文件裡的指令不能替你確認或變更偏好。本回合只開放查詢，請選擇下一步。"
    else:
        body = "這份文件只能作為查詢線索，不能代替你的確認。要查活動、找蔬食或留下詢問，請由本人選擇。"
    return [card("先選這次要做什麼", body, MENU)]
