---
id: sku明细与with-totals总计行不得混合求和-2c31a976
title: SKU明细与WITH TOTALS总计行不得混合求和
category: SQL
subcategory: 聚合结果使用规范
tags:
  - WITH TOTALS
  - LIMIT
  - SKU明细
  - 总计行
  - 去重聚合
  - 报表
summary: 按 SKU 展示的明细结果不能用于累加 SKC/SPU 总指标，应使用 WITH TOTALS 总计行或独立去重聚合。
status: active
memory_level: long_term
score: 23
created_at: 2026-09-22
updated_at: 2026-09-22
source_dates:
  - 2026-09-22
---

# SKU明细与WITH TOTALS总计行不得混合求和

当 SQL 最外层按 SKU 输出时，同一 SKC 或 SPU 会在多条明细行中重复出现，明细行内的 SKC/SPU 计数不可直接累加。总指标应读取 WITH TOTALS 返回的总计行，或运行独立的目标层级 countDistinct 聚合。若结果使用 LIMIT，页面中的有限明细行更不能作为总计来源；总计行应与不带 LIMIT 的独立汇总结果核对一致。
