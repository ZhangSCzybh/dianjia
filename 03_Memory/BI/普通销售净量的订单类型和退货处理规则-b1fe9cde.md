---
id: 普通销售净量的订单类型和退货处理规则-b1fe9cde
title: 普通销售净量的订单类型和退货处理规则
category: BI
subcategory: 销售指标口径
tags:
  - 销售
  - 退货
  - 净销量
  - 订单类型
  - 动销
summary: 普通销售净量以成交数量减退货数量计算，并排除指定订单类型；净销量必须大于 0 才能判定为动销。
status: active
memory_level: long_term
score: 23
created_at: 2026-09-22
updated_at: 2026-09-22
source_dates:
  - 2026-09-22
---

# 普通销售净量的订单类型和退货处理规则

普通销售净量定义为 sale_deal_num - sale_refund_num，并排除 order_type IN (4,5) 的记录。当前和期间动销、生命周期周销量均应使用该普通销售净量。净销量等于 0 或小于 0 时，不应计为动销。
