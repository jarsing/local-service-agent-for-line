# Day 24 擷取核對報告

直接 SDK 路由與本機後端重播分開；本表沒有 LINE 實機證據。

## 九題路由：工具要求，不是後端執行

| 題號 | 原問句 | 預期工具 | 實際工具要求與參數 | 擷取狀態 | 路由判定 |
|---|---|---|---|---|---|
| local01 | 花壇的店現在有開嗎？輪椅能進去嗎？ | ["search_local_places"] | [{"arguments": {"area": "花壇", "dietary_type": "", "keyword": ""}, "name": "search_local_places"}] | CAPTURED | PASS |
| local02 | 花壇有什麼店？ | ["search_local_places"] | [{"arguments": {"area": "花壇", "dietary_type": "", "keyword": ""}, "name": "search_local_places"}] | CAPTURED | PASS |
| local09 | 附近有什麼蔬食店？ | ["search_local_places"] | [{"arguments": {"area": "附近", "dietary_type": "vegetarian", "keyword": ""}, "name": "search_local_places"}] | CAPTURED | PASS |
| local11 | 花壇場次的集合點在哪？ | ["search_local_events"] | [{"arguments": {"area": "花壇", "date": "", "keyword": ""}, "name": "search_local_events"}] | CAPTURED | PASS |
| local12 | 花壇有推薦的素食店嗎？ | ["search_local_places"] | [{"arguments": {"area": "花壇", "dietary_type": "vegetarian", "keyword": ""}, "name": "search_local_places"}] | CAPTURED | PASS |
| local13 | 查大村素食 | ["search_local_places"] | [{"arguments": {"area": "大村", "dietary_type": "vegetarian", "keyword": ""}, "name": "search_local_places"}] | CAPTURED | PASS |
| local17 | 可以幫我預約明天的爌肉飯嗎 | ["show_local_help"] | [{"arguments": {"reason": "unsupported"}, "name": "show_local_help"}] | CAPTURED | PASS |
| local18 | 附近能停車嗎？有免費接駁車嗎？ | ["show_local_help"] | [{"arguments": {"reason": "unsupported"}, "name": "show_local_help"}] | CAPTURED | PASS |
| local19 | 現在哪裡有開著的爌肉飯？可以幫我預約兩碗帶走嗎？ | ["show_local_help"] | [{"arguments": {"reason": "unsupported"}, "name": "show_local_help"}] | CAPTURED | PASS |

## 六列 A/B：單次模型呼叫觀察

| 題號 | 組別 | 預算 | 毫秒 | 輸入 | 輸出 | 思考 | 思考來源 | 估計 USD | 路由 |
|---|---|---:|---:|---:|---:|---:|---|---:|---|
| local11 | A | 0 | 3097.762041958049 | 767 | 29 | 114 | OBSERVED | 待量測 | PASS |
| local11 | B | 1024 | 4666.869999840856 | 767 | 29 | 153 | OBSERVED | 0.0006851 | PASS |
| local12 | B | 1024 | 3305.0744580104947 | 769 | 33 | 116 | OBSERVED | 0.0006032 | PASS |
| local12 | A | 0 | 2602.3535418789834 | 769 | 33 | 79 | OBSERVED | 待量測 | PASS |
| local19 | A | 0 | 2899.3404591456056 | 781 | 19 | 101 | OBSERVED | 待量測 | PASS |
| local19 | B | 1024 | 3366.9584169983864 | 781 | 19 | 144 | OBSERVED | 0.0006418 | PASS |

## 配對核對

| 題號 | 可比較性 | 兩組路由通過 | 成本完整 | B-A 毫秒 | B-A USD | 成本差百分比 |
|---|---|---|---|---:|---:|---:|
| local11 | COMPARABLE_REQUESTS | True | False | 1569.1079578828067 | 待量測 | 待量測 |
| local12 | COMPARABLE_REQUESTS | True | False | 702.7209161315113 | 待量測 | 待量測 |
| local19 | COMPARABLE_REQUESTS | True | False | 467.6179578527808 | 待量測 | 待量測 |

```json
{
  "ab_captured": 6,
  "ab_denominator": 6,
  "backend_ui": "NOT_EVALUATED_BY_CAPTURE_AUDIT",
  "comparable_pairs": 3,
  "complete_cost_rows": 3,
  "evidence_complete": false,
  "mode": "OFFLINE_AUDIT_OF_CAPTURE_FILES",
  "origin_authenticity": "DIGESTS_CHECK_IDENTITY_NOT_EXTERNAL_OCCURRENCE",
  "production": "NOT_EXECUTED",
  "route_attempted": 9,
  "route_captured": 9,
  "route_denominator": 9,
  "route_errors": 0,
  "route_full_denominator_rate": 1.0,
  "route_not_run": 0,
  "route_passed": 9,
  "routing_contract_passed": true,
  "safe_to_deploy": false
}
```

A/B 每題每設定只有一次觀察，差值不是平均效應；來源真實性仍需執行紀錄及人工審閱。
