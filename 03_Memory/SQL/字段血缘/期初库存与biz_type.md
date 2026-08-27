# 期初库存与 biz_type

## 一句话结论

期初库存的来源可由 `biz_type` 区分；表的 ClickHouse 替换去重键为 `bill_date, brand_id, storage_id, sku_id, source_id, key_id`，业务唯一键是否需额外包含 `biz_type` 必须另行确认。

## 归档信息

* action：update
* target_path：`03_Memory/SQL/字段血缘/期初库存与biz_type.md`
* 归档理由：已具备可复用的来源判定和销售数量公式；唯一键规则保留待验证状态。

---

## 分类

* 一级分类：SQL
* 二级分类：字段血缘
* 标签：`biz_type`、期初库存、销售数量、数据质量
* memory_id：`sql-lineage-opening-inventory-001`

---

## 记忆内容

### 问题 / 场景

核对期初库存来源、月初跑数和销售数量报表时使用。

### 核心结论

`biz_type=-1` 表示系统跑数，`biz_type=-2` 表示进销存跑数；同一业务唯一键出现重复期初库存记录需要排查。

### 使用方法

按库存日期、门店、商品和表的替换去重键检查 `biz_type`、记录数和销售数量组成项；若业务要求区分库存业务类型，再补充 `biz_type` 对账。

## 期初库存来源判定

在当前日期为 08 月 11 日的示例中：

- `biz_type = -1`：系统跑出的期初库存。
- `biz_type = -2`：进销存跑出的期初库存。
- 历史日期（例如 08 月 10 日）的历史 `biz_type` 通常应为 `-2`。

同一业务键、同一日期出现重复期初库存记录，通常表示数据生成或同步存在问题。测试时应按门店、商品、库存日期和 `biz_type` 检查唯一性，并定位重复来源。

## 表结构与替换键

期初库存表：`flowstock.dm_wms_stock_period_12562`

```sql
ENGINE = SharedReplacingMergeTree(..., sync_last_modify_time)
PARTITION BY toYear(bill_date)
ORDER BY (bill_date, brand_id, storage_id, sku_id, source_id, key_id)
```

含义：同一 `ORDER BY` 键的多版本记录，在合并或使用 `FINAL` 查询后，以 `sync_last_modify_time` 较新的版本为准。普通查询在后台合并完成前可能看到多条物理记录，因此不能直接据此认定业务重复。

`biz_type`、`spu_id`、`skc_id` 不在 `ORDER BY` 中。若这些字段代表业务上应独立存在的库存记录，需确认上游是否保证其对应的 `key_id` 或 `source_id` 不同；否则可能发生替换覆盖。

### 物理重复排查

```sql
SELECT
    bill_date,
    brand_id,
    storage_id,
    sku_id,
    source_id,
    key_id,
    count() AS physical_rows,
    min(sync_last_modify_time) AS first_sync_time,
    max(sync_last_modify_time) AS last_sync_time
FROM flowstock.dm_wms_stock_period_12562
WHERE brand_id = {brand_id}
  AND bill_date = {bill_date}
GROUP BY bill_date, brand_id, storage_id, sku_id, source_id, key_id
HAVING physical_rows > 1;
```

使用 `FINAL` 查询同一键时，结果应只保留当前版本；若业务要求 `biz_type` 独立，则需额外按 `biz_type` 对账，不可仅依赖表引擎的替换键。

## 销售数量口径

```text
销售数量 = 订单净销售数量
        + 积分销售数量
        + 储值卡赠送数量
```

测试时需分别核对三类数量，不能只用订单数量替代报表销售数量。

## 建议测试

- 检查当前日期是否只生成一套系统期初数据。
- 检查历史日期是否使用 `biz_type=-2`。
- 检查同一门店、商品、日期是否有重复记录。
- 检查三类销售数量相加后是否等于报表销售数量。

---

## 来源

* 来源日期：2026-08-27
* 来源类型：项目
* 原始记录：[[2026-08-27]]

---

## 记忆价值

| 维度 | 分数 |
|---|---:|
| 可复用性 | 4 |
| 重要性 | 4 |
| 独特性 | 4 |
| 稳定性 | 3 |
| 个人相关性 | 5 |

**总分：20**

**记忆等级：long_term**

---

## 生命周期

* 状态：待验证
* 创建时间：2026-08-27
* 更新时间：2026-08-27（补充期初库存表的替换去重键）
* 建议复查时间：2026-09

---

## 关联记忆

[[店家数仓销售报表测试]]
