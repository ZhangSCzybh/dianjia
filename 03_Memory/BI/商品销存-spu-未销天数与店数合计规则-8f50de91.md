---
id: 商品销存-spu-未销天数与店数合计规则-8f50de91
title: 商品销存 SPU 未销天数与店数合计规则
category: BI
subcategory: 进销存报表
tags:
  - 商品销存
  - SPU
  - SKU
  - 未销天数
  - 店铺销售分析
  - 合计行
summary: SPU 粒度未销天数取其 SKU 未销天数最小值；多维店数和会员人数合计无法去重，建议看明细或使用经典模式。
status: active
memory_level: long_term
verification_status: pending
score: 19
created_at: 2025-11-28
updated_at: 2025-11-28
source_dates:
  - 2025-11-28
---

# 商品销存 SPU 未销天数与店数合计规则

商品销存分析只选到SPU粒度时，系统从该SPU下所有SKU的未销天数取最小值；所有SKU都为空时SPU也为空。店铺销售分析中店数最小粒度为店铺，加入时间等维度后不能简单求和，经典报表后端会对合计行去重，多维报表前端自定义展示无法按店数去重；会员人数同理。此类字段建议不看多维合计行或使用经典模式。
