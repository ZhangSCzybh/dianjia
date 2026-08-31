---
id: 四类clickhouse报表sql执行结果验证-09f2a2a1
title: 四类ClickHouse报表SQL执行结果验证
category: BI
subcategory: 报表查询
tags:
  - 商品零售明细
  - 零售支付明细
  - 零售商品销售成本
  - 全渠道销售统计
  - ClickHouse
summary: 在flowdata-ka集群执行四类只读报表SQL，使用品牌10770和2026-08-01至2026-08-31过滤条件，返回聚合结果并验证正确性。
status: active
memory_level: long_term
score: 0
created_at: 2026-08-31
updated_at: 2026-08-31
source_dates:
  - 2026-08-31
---

# 四类ClickHouse报表SQL执行结果验证

在flowdata-ka集群执行四类只读报表SQL，均使用品牌10770和2026-08-01至2026-08-31过滤条件：商品零售明细返回290行聚合结果，覆盖147个订单、12个门店、30个SPU、68个SKU；零售支付明细返回401行聚合结果，包含支付类型101/110/118拆分及礼品卡折扣分摊；零售商品销售成本返回393行聚合结果，并行计算标准成本、综合成本和订单实际成本及三套毛利；全渠道销售统计返回38个渠道与商品类目组合及totals，一级渠道结果为线下门店和私域。
