---
id: select-formatdatetime-bill_date-y--m--d-as-billdate-name_st-as-namest-code_s-97565ebb
title: SELECT formatDateTime(bill_date,'%Y-%m-%d') as billDate,name_st as nameSt,code_s
category: SQL
subcategory: 查询与数据
tags:
  - select
  - join
summary: SELECT formatDateTime(bill_date,'%Y-%m-%d') as billDate,name_st as nameSt,code_st as codeSt,channel_name_new as channelNameNew,channel_code_new as channelCodeNew,bill_type_desc as billTypeDesc,bill_code as billCode,spu_code as spuCode,sku_c
status: archived
memory_level: long_term
score: 15
created_at: 2026-09-01
updated_at: 2026-09-01
source_dates:
  - 2026-09-01
---

# SELECT formatDateTime(bill_date,'%Y-%m-%d') as billDate,name_st as nameSt,code_s

SELECT formatDateTime(bill_date,'%Y-%m-%d') as billDate,name_st as nameSt,code_st as codeSt,channel_name_new as channelNameNew,channel_code_new as channelCodeNew,bill_type_desc as billTypeDesc,bill_code as billCode,spu_code as spuCode,sku_color_value as skuColorValue,sku_size_value as skuSizeValue,sku_size_group_name as skuSizeGroupName,sku_size_sort_order as skuSizeSortOrder,sku_size_code as skuSizeCode,id_str as idStr,source_deal_order_id_new2 as sourceDealOrderIdNew2,formatDateTime(create_date_sale,'%Y-%m-%d') as createDateSale,name_sale as nameSale,biz_source_name as bizSourceName,bool_dropship_goods_desc as boolDropshipGoodsDesc,split_order_id as splitOrderId,order_sale_date as orderSaleDate,order_source_name as orderSourceName,third_order_id_fix as thirdOrderIdFix,third_porder_id_fix as thirdPorderIdFix,sum(inout_section_in_num) as sumInoutSectionInNum,sum(intout_section_out_num) as sumIntoutSectionOutNum,sum(inout_section_actual_num) as sumInoutSectionActualNum,sum(inout_section_in_money) as sumInoutSectionInMoney,sum(intout_section_out_money) as sumIntoutSectionOutMoney,sum(inout_section_actual_money) as sumInoutSectionActualMoney FROM  (SELECT biz_source_name,bill_code,bill_date,ref_bill_code,original_bill_code,bill_type_desc,split_order_id,up_bill_code,code_st,name_st,channel_code_new,channel_name_new,spu_id,sku_id_dim_sku,spu_code,sku_color_value,sku_size_code,sku_size_value,sku_size_group_name,sku_size_sort_order,name_sale,create_date_sale,id_str,source_deal_order_id_new2,order_source_name,bool_dropship_goods_desc,order_sale_date,third_order_id_fix,third_porder_id_fix,inout_section_in_num,intout_section_out_num,inout_section_in_money,intout_section_out_money,(inout_section_in_num + intout_section_out_num) as inout_section_actual_num,(inout_section_in_money + intout_section_out_money) as inout_section_actual_money FROM  (SELECT biz_source_name,bill_code,bill_date,ref_bill_code,original_bill_code,bill_type_desc,split_order_id,up_bill_code,code_st,name_st,channel_code_new,channel_name_new,spu_id,sku_id_dim_sku,spu_code,sku_color_value,sku_size_code,sku_size_value,sku_size_group_name,sku_size_sort_order,name_sale,create_date_sale,id_str,source_deal_order_id_new2,order_source_name,bool_dropship_goods_desc,order_sale_date,third_order_id_fix,third_porder_id_fix,if(bill_source =3020 or bill_source =3000 or bill_source =3010 or  bill_source =3030  or  bill_source =3040   or  bill_source =3050 ,paper_num ,0) as inout_section_in_num,if(bill_source =2020 or bill_source =2000 or bill_source =2010 or  bill_source =2030  or  bill_source =2040   or  bill_source =2050 ,-paper_num ,0) as intout_section_out_num,if(bill_source =3020 or bill_source =3000 or bill_source =3010 or  bill_source =3030  or  bill_source =3040 , item_amount  ,0) as inout_section_in_money,if(bill_source =2020 or bill_source =2000 or bill_source =2010 or  bill_source =2030  or  bill_source =2040 ,-item_amount ,0) as intout_section_out_money,item_amount,bill_source,paper_num FROM  (SELECT item_amount,biz_source_name,bill_code,bill_date,bill_source,paper_num,ref_bill_code,original_bill_code,bill_type_desc,split_order_id,up_bill_code,code_st,name_st,channel_code_new,channel_name_new,spu_id,sku_id_dim_sku,spu_code,sku_color_value,sku_size_code,sku_size_value,sku_size_group_name,sku_size_sort_order,name_sale,create_date_sale,id_str,source_deal_order_id_new2,order_source_name,if(bool_dropship_goods =1,'是','否') as bool_dropship_goods_desc,if(bill_date_sale ='1970-01-01','',toString(bill_date_sale)) as order_sale_date,if(third_order_id !='1',third_order_id ,'') as third_order_id_fix,if(third_porder_id !='0',third_porder_id ,'') as third_porder_id_fix,bill_date_sale,third_order_id,third_porder_id,bool_dropship_goods FROM  (SELECT item_amount,biz_source_name,bill_code,bill_date,bill_source,paper_num,ref_bill_code,original_bill_code,bill_type_desc,split_order_id,up_bill_code,code_st,name_st,channel_code_new,channel_name_new,spu_id,sku_id_dim_sku,spu_code,sku_color_value,sku_size_code,sku_size_value,sku_size_group_name,sku_size_sort_order,if(bill_date_refund is null or bill_date_refund ='1970-01-01',bill_date_sale,bill_date_refund) as bill_date_sale,if(name_refund is null or name_refund  ='',name_sale,name_refund) as name_sale,if(third_order_id_refund is null or third_order_id_refund  ='',third_order_id,third_order_id_refund) as third_order_id,if(third_porder_id_refund  is null or third_porder_id_refund  ='',third_porder_id,third_porder_id_refund) as third_porder_id,if(bool_dropship_goods_refund  is null or bool_dropship_goods_refund  =0,bool_dropship_goods,bool_dropship_goods_refund) as bool_dropship_goods,if(create_date_refund is null or create_date_refund ='1970-01-01',create_date_sale,create_date_refund) as create_date_sale,if(bill_type  = 20, 
	if(original_bill_code is null or original_bill_code  = '',
    	ref_bill_code , 
        if(ref_bill_type  != '85',original_bill_code,'')),
	if(ref_bill_type  = '90',
    	original_bill_code ,
        if(ref_bill_type  != '85',ref_bill_code, ''))
) as id_str,if (source_deal_order_id_new_refund  is null or source_deal_order_id_new_refund  = 0,
	if(source_deal_order_id_new is null or source_deal_order_id_new   = 0, null, source_deal_order_id_new) ,
	source_deal_order_id_new_refund 
) as source_deal_order_id_new2,if (dict_name_refund   is null or  dict_name_refund   = '' ,dict_name, dict_name_refund) as order_source_name,bill_type,ref_bill_type,dict_name,source_deal_order_id_new,bill_date_refund,name_refund,third_order_id_refund,third_porder_id_refund,bool_dropship_goods_refund,create_date_refund,dict_name_refund,source_deal_order_id_new_refund FROM  (SELECT item_amount,biz_source_name,bill_code,bill_date,sku_id,bill_type,bill_source,paper_num,ref_bill_type,ref_bill_code,original_bill_code,bill_type_desc,split_order_id,up_bill_code,code_st,name_st,channel_code_new,channel_name_new,spu_id,sku_id_dim_sku,spu_code,sku_color_value,sku_size_code,sku_size_value,sku_size_group_name,sku_size_sort_order,bill_date_sale,name_sale,third_order_id,third_porder_id,bool_dropship_goods,create_date_sale,dict_name,source_deal_order_id_new,bill_date_refund,name_refund,third_order_id_refund,third_porder_id_refund,bool_dropship_goods_refund,create_date_refund,dict_name_refund,source_deal_order_id_new_refund FROM   (SELECT item_amount,biz_source_name,bill_code,bill_date,sku_id,bill_type,bill_source,paper_num,ref_bill_type,ref_bill_code,original_bill_code,bill_type_desc,split_order_id,up_bill_code,code_st,name_st,channel_code_new,channel_name_new,spu_id,sku_id_dim_sku,spu_code,sku_color_value,sku_size_code,sku_size_value,sku_size_group_name,sku_size_sort_order,bill_date_sale,name_sale,third_order_id,third_porder_id,bool_dropship_goods,create_date_sale,dict_name,source_deal_order_id_new FROM   (SELECT item_amount,biz_source_name,bill_code,bill_date,sku_id,bill_type,bill_source,paper_num,ref_bill_type,ref_bill_code,original_bill_code,bill_type_desc,split_order_id,up_bill_code,code_st,name_st,channel_code_new,channel_name_new,spu_id,sku_id_dim_sku,spu_code,sku_color_value,sku_size_code,sku_size_value,sku_size_group_name,sku_size_sort_order FROM   (SELECT item_amount,biz_source_name,bill_code,bill_date,sku_id,bill_type,bill_source,paper_num,ref_bill_type,ref_bill_code,original_bill_code,bill_type_desc,split_order_id,up_bill_code,code_st,name_st,if(bill_to_st_ch =1,bl_ch_code ,code_ch) as channel_code_new,if(bill_to_st_ch =1,bl_ch_name  ,name_ch) as channel_name_new,bill_to_st_ch,bl_ch_code,bl_ch_name,code_ch,name_ch FROM  (SELECT item_amount,biz_source_name,bill_code,bill_date,sku_id,bill_type,bill_source,paper_num,ref_bill_type,ref_bill_code,original_bill_code,bill_type_desc,channel_id,split_order_id,bill_to_st_ch,up_bill_code,code_st,name_st,bl_ch_code,bl_ch_name,code_ch,name_ch FROM   (SELECT item_amount,biz_source_name,bill_code,bill_date,sku_id,bill_type,bill_source,paper_num,ref_bill_type,ref_bill_code,original_bill_code,bill_type_desc,storage_id,channel_id,split_order_id,bill_to_st_ch,up_bill_code,code_st,name_st,bl_ch_code,bl_ch_name FROM   (SELECT item_amount,biz_source_name,bill_item_id,bill_id,bill_code,bill_date,sku_id,bill_type,bill_source,paper_num,ref_bill_type,ref_bill_code,original_bill_code,bill_type_desc,storage_id,channel_id,split_order_id,bill_to_st_ch,up_bill_code FROM   (SELECT item_amount,biz_source_name,bill_item_id,bill_id,bill_code,bill_date,sku_id,bill_type,bill_source,paper_num,ref_bill_type,ref_bill_code,original_bill_code,case when bill_source  = 3020 then '采购入库'
when bill_source  = 3000 then '配货入库'
when bill_source  = 3010 then '调拨入库'
when bill_source  = 3030 then '退货入库'
when bill_source  = 3040 then '零售入库'
when bill_source  = 3050 then '归还入库'
when bill_source  = 3099 then '其他入库'
when bill_source  = 2020 then '采购退货'
when bill_source  = 2000 then '配货出库'
when bill_source  = 2010 then  '调拨出库'
when bill_source  = 2030 then  '退货出库'
when bill_source  = 2040 then  '零售出库'
when bill_source  = 2050 then  '外借出库'
when bill_source  = 2099 then  '其他出库'
when bill_source =4000 and diff_num 0 then '盘盈入库'
when bill_type =40 and diff_num >0 then '调整入库'
when bill_type  =40 and diff_num = cast('2026-09-01' as DATE) and bill_date = cast('2026-09-01' as DATE) and bill_date = cast('2026-09-01' as DATE) and bill_date = cast('2026-09-01' as DATE) and bill_date = cast('2026-09-01' as DATE) and bill_date = cast('2026-09-01' as DATE) and bill_date <= cast('2026-09-01' as DATE) and bill_state in (5)))  art )))  art ) lt LEFT JOIN  (SELECT storage_id as storage_id_st,code,name FROM  (SELECT storage_id,code,name FROM flowload.dim_corp_storage_bi art final WHERE brand_id = 10770)  art ) rt ON lt.storage_id=rt.storage_id_st) lt LEFT JOIN  (SELECT dict_name,dict_value FROM flowload.dim_dict_order_source_ds art final) rt ON lt.order_source=rt.dict_value GROUP BY storage_id_st_refund,order_source_refund,source_deal_order_id_new_refund,dict_name_refund,source_deal_order_id,brand_sku_id_refund,id_str_refund,create_date_refund,id_refund,bill_date_refund,name_refund,code_refund,third_order_id_refund,third_porder_id_refund,customer_name_refund,bool_dropship_goods_refund) rt ON lt.ref_bill_code=rt.id_str_refund and lt.sku_id=rt.brand_sku_id_refund)  art )  art )  art )  art )  art  GROUP BY billDate,nameSt,codeSt,channelNameNew,channelCodeNew,billTypeDesc,billCode,spuCode,skuColorValue,skuSizeValue,skuSizeGroupName,skuSizeSortOrder,skuSizeCode,idStr,sourceDealOrderIdNew2,createDateSale,nameSale,bizSourceName,boolDropshipGoodsDesc,splitOrderId,orderSaleDate,orderSourceName,thirdOrderIdFix,thirdPorderIdFix WITH TOTALS ORDER BY billDate asc,nameSt asc,codeSt asc,channelNameNew asc,channelCodeNew asc,billTypeDesc asc,billCode asc,spuCode asc,skuColorValue asc,skuSizeValue asc,skuSizeGroupName asc,skuSizeSortOrder asc,skuSizeCode asc,idStr asc,sourceDealOrderIdNew2 asc,createDateSale asc,nameSale asc,bizSourceName asc,boolDropshipGoodsDesc asc,splitOrderId asc,orderSaleDate asc,orderSourceName asc,thirdOrderIdFix asc,thirdPorderIdFix asc,sumInoutSectionInNum desc  limit 0,1000

## 更新 2026-09-01

## 查询口径
- 数据源为 flowload.dm_wms_bill_all_ds，主过滤为 brand_id=10770、bill_date=2026-09-01、bill_state=5、bill_source in (2040,3040)。其中 3040 映射零售入库，2040 映射零售出库。外层将出库 paper_num 和 item_amount 取负，并计算实际数量/金额。
- 通过 dm_wms_bill_all_ds 自关联推导 up_bill_code；再关联 dim_corp_storage_bi 两次补店仓和渠道、dim_goods_sku_bi 补 SKU 属性、dm_order_item_sale_bi_ds 补销售/退款订单字段、dim_dict_order_source_ds 补订单来源。销售与退款订单分别按原单号/关联单号和 SKU 关联。
- 最终按 25 个维度分组，WITH TOTALS 后排序并 LIMIT 0,1000；因此结果粒度接近单据明细，只有完全相同维度的行才会合并。

## KA 验证
- flowdata-ka ClickHouse 25.12.1.1645，原 SQL 耗时 1.051 秒，返回 6 行。
- 汇总：3040 入库 3 行、3 件、19.89；2040 出库 3 行、4 件、21；净变动 -1 件、-1.11。结果店仓均为艺尚小镇店、渠道均为总部。
- EXPLAIN 显示 brand_id 分区裁剪为 3/149 parts，主键 bill_date+brand_id 将 granules 从 15 降到 3，日期条件有效。

## 风险与优化建议
- 内层重复扫描 dm_wms_bill_all_ds 并多次使用 FINAL，查询文本约 45 层 SELECT、10 次 JOIN；数据量扩大后 CPU、内存和延迟会明显上升。建议先物化一次带日期/品牌/状态/来源过滤的明细 CTE 或中间表，再复用订单号集合和维表。
- bill_state in (5,7) 外层又限定 bill_state in (5)，实际只保留 5，应删除冗余条件。日期单日范围可直接写 bill_date=toDate('2026-09-01')。
- 3040/2040 的入出库金额和数量符号逻辑正确，但需确认 paper_num 是否允许负数；否则出库取负后会出现符号反转。
- INNER JOIN up_bill_code 和 SKU 维表会丢失无匹配明细；订单、店仓、渠道使用 LEFT JOIN，缺失时会输出空字段。建议增加基表行数与最终行数对账，以及未匹配 SKU/订单的监控。
- WITH TOTALS 配合 JSONEachRow/导出时要确认客户端对 totals 行的处理；LIMIT 应放在确认 totals 展示需求后使用。
