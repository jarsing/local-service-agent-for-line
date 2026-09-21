"""不用金鑰的確認流程演練。所有人物、版本與時間均為合成教學資料。"""
from datetime import datetime, timedelta, timezone
import json
from confirmation import ConfirmationStore, Identity, Operation


def main() -> None:
    now = datetime(2026, 9, 22, 1, 0, tzinfo=timezone.utc)
    owner = Identity("demo-user-a", "demo-session-a")
    operation = Operation("draft-demo-1", 1, "demo-event-a", "catalog-v1",
                          "請問集合地點在哪裡？",
                          {"name": "教學走讀", "time": "07:30~11:00"})
    rows = []
    for label, version in (("內容維持原版", "catalog-v1"), ("等待期間資料已更新", "catalog-v2")):
        store = ConfirmationStore()
        offer = store.issue(owner=owner, operation=operation,
                            current_catalog_version="catalog-v1",data_status="adopted",now=now)
        result = store.decide(confirmation_id=offer["confirmation_id"],actor=owner,
                              current_operation=operation,current_catalog_version=version,
                              data_status="adopted",permitted=True,approved=True,
                              now=now+timedelta(seconds=10))
        rows.append({"scenario": label, "status": result["status"],
                     "execution_allowed": result["execution_allowed"]})
    print(json.dumps({"kind":"LOCAL_DAY08_OFFLINE_DEMO", "model_calls":0,
                      "source_kind":"synthetic_fixture", "scenarios":rows},ensure_ascii=False,indent=2))

if __name__ == "__main__":
    main()
