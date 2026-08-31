---
id: 销售报表sql口径-净销售减退款-支付比例拆分-空标签过滤-7a0413df
title: 销售报表SQL口径：净销售减退款、支付比例拆分、空标签过滤
category: BI
subcategory: 报表口径
tags:
  - 销售指标
  - 净销售
  - 退款
  - 支付比例
  - 订单标签
  - 剔除商品
summary: 销售报表中销售金额按净销售减退款计算，基础KPI金额排除剔除商品，支付比例按order_id+sku_id+item_id计算，订单标签过滤使用空标签条件。
status: active
memory_level: long_term
score: 1
created_at: 2026-08-31
updated_at: 2026-08-31
source_dates:
  - 2026-08-31
---

# 销售报表SQL口径：净销售减退款、支付比例拆分、空标签过滤

四类报表SQL（商品零售明细、零售支付明细、零售商品销售成本、全渠道销售统计）的共同注意点：销售指标使用净销售减退款；基础KPI金额排除剔除商品；支付比例按order_id+sku_id+item_id计算，但部分主表关联只使用订单id和item_id；订单标签过滤最终使用空标签条件；大量FINAL、重复扫描和复杂JOIN会增加查询成本。
