---
title: "基础信息|公司接口|大陆|API文档|开放平台 - 理杏仁"
source: "https://www.lixinger.com/open/api/doc?api-key=cn/company"
author:
published:
created: 2026-02-26
description: "理杏仁定位于理性投资者的数据中心，为投资者提供专业的数据提取、筛选以及可视化服务。"
tags:
  - "clippings"
---
## 股票信息API(过期时间: 2026-03-02 18:41)续订

简要描述:

- 获取股票详细信息。

请求URL:

- `https://open.lixinger.com/api/cn/company`

请求方式:

- POST

参数:

| 参数名称 | 必选 | 数据类型 | 说明 |
| --- | --- | --- | --- |
| token | Yes | String | [我的Token](https://www.lixinger.com/open/api/token) 页有用户专属且唯一的Token。 |
| stockCodes | No | Array | 股票代码数组。 默认值为所有股票代码。格式如下：\["300750","600519","600157"\]。  请参考 [股票信息API](https://www.lixinger.com/open/api/detail?api-key=cn/company) 获取合法的stockCode。 |
| fsTableType | No | String | 财报类型，比如，'bank'。  ##### 当前支持:  - 非金融: non\_financial - 银行: bank - 保险: insurance - 证券: security - 其他金融: other\_financial |
| mutualMarkets | No | Array | 互联互通类型，比如：'\[ha\]'。  ##### 当前支持:  陆股通: ha |
| includeDelisted | No | Boolean | 是否包含退市股。 默认值是false。 |
| pageIndex | Yes | Number | 页面索引。 默认值是0。 |

**返回数据说明:**

| 参数名称 | 数据类型 | 说明 |
| --- | --- | --- |
| total | Number | 公司总数 |
| name | String | 公司名称 |
| stockCode | String | 股票代码 |
| areaCode | String | 地区代码 |
| market | String | 市场 |
| exchange | String | 交易所 |
| fsTableType | String | 财报类型 |
| mutualMarkets | String | 互联互通 |
| mutualMarketFlag | Boolean | 是否是互联互通标的 |
| marginTradingAndSecuritiesLendingFlag | Boolean | 是否是融资融券标的 |
| ipoDate | Date | 上市时间 |
| delistedDate | Date | 退市时间 |
| listingStatus | String | 上市状态  - 正常上市:normally\_listed - 已退市:delisted - 暂停上市:listing\_suspended - ST板块:special\_treatment - \*ST:delisting\_risk\_warning - 已发行未上市:issued\_but\_not\_listed - 预披露:pre\_disclosure - 未过会:unauthorized - 发行失败:issue\_failure - 进入退市整理期:delisting\_transitional\_period - 暂缓发行:ipo\_suspension - 暂缓上市:ipo\_listing\_suspension - 停止转让:transfer\_suspended - 正常转让:normally\_transferred - 投资者适当性管理标识:investor\_suitability\_management\_implemented - 非上市:non\_listed - 特定债券转让:transfer\_as\_specific\_bond - 协议转让:transfer\_under\_agreement - 其它:others |

