---
id: 盘点单作废冲销与提交规则-bd9fdfdf
title: 盘点单作废冲销与提交规则
category: Projects
subcategory: 库存盘点
tags:
  - 盘点单
  - 作废
  - 冲销
  - 提交
  - 库存恢复
summary: 未提交盘点单可作废，已提交盘点单只能冲销，提交会按盘点结果更新门店库存。
status: active
memory_level: long_term
score: 25
created_at: 2026-09-01
updated_at: 2026-09-01
source_dates:
  - 2026-09-01
---

# 盘点单作废冲销与提交规则

盘点差异核对并处理错盘、漏盘后再提交盘点单，系统会按盘点明细自动更新门店账面库存。状态为未提交的盘点单可以作废并重新盘点；状态为已提交的盘点单不能作废，只能冲销，冲销后账面库存恢复到盘点前状态，再重新安排盘点。
