---
id: 多维报表人数温度聚合与-cube-别名规则-85bd09e1
title: 多维报表人数温度聚合与 Cube 别名规则
category: BI
subcategory: 报表聚合
tags:
  - 多维报表
  - 去重
  - 会员人数
  - 最低温
  - 最高温
  - Cube
  - 别名
summary: 多维报表合计由前端处理，会员人数不能自动去重，温度会按记录平均；Cube 别名变更后需重新选取源字段。
status: active
memory_level: long_term
verification_status: pending
score: 19
created_at: 2025-11-28
updated_at: 2025-11-28
source_dates:
  - 2025-11-28
---

# 多维报表人数温度聚合与 Cube 别名规则

会员成交人数、会员消费人数需要按会员去重，经典报表合计行有后端去重处理，多维报表合计由前端处理无法去重。最低温和最高温到日期粒度，经典报表按天去重，多维报表无法自动处理，会按记录内容求平均，时段数量会影响平均值。Cube 展示别名调整对经典报表查看无影响；多维报表数据不变，但源字段名称仍显示原别名，需要重新选取字段。
