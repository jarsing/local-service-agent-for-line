# Day 24 2026-10-08 官方牌價重算稽核報告 (Post-hoc Repricing Audit)

依據 2026-10-08 Gemini 3.8 Flash 官方公開牌價（輸入 0.75、輸出含思考 3.75 USD / 1M）重算六列成本。原始 Token 用量與毫秒數保持 Attempt 3 凍結快照不變。

| 題號 | 組別 | 預算 | 毫秒 | 輸入 Token | 輸出 Token | 思考 Token | 牌價重算 USD | 路由判定 |
|---|---|---:|---:|---:|---:|---:|---:|---|
| local11 | A | 0 | 3,097.8 | 767 | 29 | 114 | 0.0011115 | PASS |
| local11 | B | 1024 | 4,666.9 | 767 | 29 | 153 | 0.0012578 | PASS |
| local12 | A | 0 | 2,602.4 | 769 | 33 | 79 | 0.0009968 | PASS |
| local12 | B | 1024 | 3,305.1 | 769 | 33 | 116 | 0.0011355 | PASS |
| local19 | A | 0 | 2,899.3 | 781 | 19 | 101 | 0.0010358 | PASS |
| local19 | B | 1024 | 3,367.0 | 781 | 19 | 144 | 0.0011970 | PASS |

## 成對比較結果

| 題號 | 可比較性 | B-A 延遲差 ms | B-A 成本差 USD | 成本增幅 |
|---|---|---:|---:|---:|
| local11 | COMPARABLE | +1,569.1 ms | +0.0001463 | +13.16% |
| local12 | COMPARABLE | +702.7 ms | +0.0001387 | +13.91% |
| local19 | COMPARABLE | +467.6 ms | +0.0001612 | +15.56% |

- complete_cost_rows: 6 / 6 (100%)
- evidence_complete: true
- routing_contract_passed: true (9/9)
- safe_to_deploy: false (保持生產安全防線)
