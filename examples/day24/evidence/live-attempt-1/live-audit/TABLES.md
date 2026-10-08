# Day 24 擷取核對報告

直接 SDK 路由與本機後端重播分開；本表沒有 LINE 實機證據。

## 九題路由：工具要求，不是後端執行

| 題號 | 原問句 | 預期工具 | 實際工具要求與參數 | 擷取狀態 | 路由判定 |
|---|---|---|---|---|---|
| local01 | 花壇的店現在有開嗎？輪椅能進去嗎？ | ["search_local_places"] | 待量測 | ERROR | ERROR |
| local02 | 花壇有什麼店？ | ["search_local_places"] | 待量測 | ERROR | ERROR |
| local09 | 附近有什麼蔬食店？ | ["search_local_places"] | 待量測 | ERROR | ERROR |
| local11 | 花壇場次的集合點在哪？ | ["search_local_events"] | 待量測 | ERROR | ERROR |
| local12 | 花壇有推薦的素食店嗎？ | ["search_local_places"] | 待量測 | ERROR | ERROR |
| local13 | 查大村素食 | ["search_local_places"] | 待量測 | ERROR | ERROR |
| local17 | 可以幫我預約明天的爌肉飯嗎 | ["show_local_help"] | 待量測 | ERROR | ERROR |
| local18 | 附近能停車嗎？有免費接駁車嗎？ | ["show_local_help"] | 待量測 | ERROR | ERROR |
| local19 | 現在哪裡有開著的爌肉飯？可以幫我預約兩碗帶走嗎？ | ["show_local_help"] | 待量測 | ERROR | ERROR |

## 六列 A/B：單次模型呼叫觀察

| 題號 | 組別 | 預算 | 毫秒 | 輸入 | 輸出 | 思考 | 思考來源 | 估計 USD | 路由 |
|---|---|---:|---:|---:|---:|---:|---|---:|---|
| local11 | A | 0 | 67.48954090289772 | 待量測 | 待量測 | 待量測 | 待量測 | 待量測 | ERROR |
| local11 | B | 1024 | 71.85862516053021 | 待量測 | 待量測 | 待量測 | 待量測 | 待量測 | ERROR |
| local12 | B | 1024 | 72.5689590908587 | 待量測 | 待量測 | 待量測 | 待量測 | 待量測 | ERROR |
| local12 | A | 0 | 66.99650012888014 | 待量測 | 待量測 | 待量測 | 待量測 | 待量測 | ERROR |
| local19 | A | 0 | 68.11129208654165 | 待量測 | 待量測 | 待量測 | 待量測 | 待量測 | ERROR |
| local19 | B | 1024 | 63.83458385244012 | 待量測 | 待量測 | 待量測 | 待量測 | 待量測 | ERROR |

## 配對核對

| 題號 | 可比較性 | 兩組路由通過 | 成本完整 | B-A 毫秒 | B-A USD | 成本差百分比 |
|---|---|---|---|---:|---:|---:|
| local11 | NOT_COMPARABLE | False | False | 待量測 | 待量測 | 待量測 |
| local12 | NOT_COMPARABLE | False | False | 待量測 | 待量測 | 待量測 |
| local19 | NOT_COMPARABLE | False | False | 待量測 | 待量測 | 待量測 |

```json
{
  "ab_captured": 0,
  "ab_denominator": 6,
  "backend_ui": "NOT_EVALUATED_BY_CAPTURE_AUDIT",
  "comparable_pairs": 0,
  "complete_cost_rows": 0,
  "evidence_complete": false,
  "mode": "OFFLINE_AUDIT_OF_CAPTURE_FILES",
  "origin_authenticity": "DIGESTS_CHECK_IDENTITY_NOT_EXTERNAL_OCCURRENCE",
  "production": "NOT_EXECUTED",
  "route_attempted": 9,
  "route_captured": 0,
  "route_denominator": 9,
  "route_errors": 9,
  "route_full_denominator_rate": 0.0,
  "route_not_run": 0,
  "route_passed": 0,
  "routing_contract_passed": false,
  "safe_to_deploy": false
}
```

A/B 每題每設定只有一次觀察，差值不是平均效應；來源真實性仍需執行紀錄及人工審閱。
