# 总部综合成本价 CASE 优先级

memory_id：`bi-candidate-composite-cost-case-priority-001`

分类：BI / 指标计算

标签：总部综合成本、CASE、成本价、优先级

评分：15

状态：candidate

## 候选原因

已知 `basis_composite_cost_price` 存在总部商品、特定仓库类型、门店/区域/渠道组合和特殊 `storage_id` 分支，但没有完整 CASE SQL，无法确认多条件命中时的最终取值。

## 核心内容

总部综合成本价的 CASE 顺序会直接影响成本、净利润和净利率。成本字段为 0 或 NULL 时是否继续兜底，也需要与实际 SQL 一致。

## 升级条件

取得完整 CASE SQL，并完成至少一组多分支命中和 0/NULL 成本值的验证后，更新 [[商品成本计算]]。
