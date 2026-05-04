# 股票信息API

简要描述:

- 获取股票详细信息。

请求URL:

- `https://open.lixinger.com/api/hk/company`

请求方式:

- POST

参数:

|    参数名称     | 必选 | 数据类型 |                             说明                             |
| :-------------: | :--: | :------: | :----------------------------------------------------------: |
|      token      | Yes  |  String  | [我的Token](https://www.lixinger.com/open/api/token)页有用户专属且唯一的Token。 |
|   stockCodes    |  No  |  Array   | 股票代码数组。默认值为所有股票代码。格式如下：["00700"]。请参考[股票信息API](https://www.lixinger.com/open/api/detail?api-key=hk/company)获取合法的stockCode。 |
|   fsTableType   |  No  |  String  | 财报类型，比如，'bank'。当前支持:非金融: non_financial银行: bank证券: security保险: insurance房地产投资信托: reit其他金融: other_financial |
|  mutualMarkets  |  No  |  Array   |       互联互通类型，比如：'[ah]'。当前支持:港股通: ah        |
| includeDelisted |  No  | Boolean  |               是否包含退市股。 默认值是false。               |
|    pageIndex    | Yes  |  Number  |                    页面索引。 默认值是0。                    |

**返回数据说明:**

|     参数名称     | 数据类型 |                             说明                             |
| :--------------: | :------: | :----------------------------------------------------------: |
|      total       |  Number  |                           公司总数                           |
|       name       |  String  |                           公司名称                           |
|    stockCode     |  String  |                           股票代码                           |
|     areaCode     |  String  |                           地区代码                           |
|      market      |  String  |                             市场                             |
|     exchange     |  String  |                            交易所                            |
|   fsTableType    |  String  |                           财报类型                           |
|  mutualMarkets   |  String  |                           互联互通                           |
| mutualMarketFlag | Boolean  |                      是否是互联互通标的                      |
|     ipoDate      |   Date   |                           上市时间                           |
|   delistedDate   |   Date   |                           退市时间                           |
|  listingStatus   |  String  | 上市状态正常上市 :normally_listed已退市 :delisted暂停上市 :listing_suspendedST板块 :special_treatment*ST :delisting_risk_warning已发行未上市 :issued_but_not_listed预披露 :pre_disclosure未过会 :unauthorized发行失败 :issue_failure进入退市整理期 :delisting_transitional_period暂缓发行 :ipo_suspension暂缓上市 :ipo_listing_suspension停止转让 :transfer_suspended正常转让 :normally_transferred投资者适当性管理标识 :investor_suitability_management_implemented非上市 :non_listed特定债券转让 :transfer_as_specific_bond协议转让 :transfer_under_agreement其它 :others |
|   sharesPerLot   |  Number  |                           每手股数                           |
|    stockCodeA    |  String  |                 AH同时上市公司对应的A股代码                  |