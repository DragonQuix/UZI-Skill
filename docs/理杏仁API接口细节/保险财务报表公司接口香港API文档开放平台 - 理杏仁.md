---
title: "保险|财务报表|公司接口|香港|API文档|开放平台 - 理杏仁"
source: "https://www.lixinger.com/open/api/doc?api-key=hk/company/fs/insurance"
author:
published:
created: 2026-02-26
description: "理杏仁定位于理性投资者的数据中心，为投资者提供专业的数据提取、筛选以及可视化服务。"
tags:
  - "clippings"
---
## 财报数据API(过期时间: 2026-03-02 18:41)

简要描述:

- 获取财务数据，如营业收入、ROE等。

请求URL:

- `https://open.lixinger.com/api/hk/company/fs/insurance`

请求方式:

- POST

参数:

| 参数名称 | 必选 | 数据类型 | 说明 |
| --- | --- | --- | --- |
| token | Yes | String | [我的Token](https://www.lixinger.com/open/api/token) 页有用户专属且唯一的Token。 |
| stockCodes | Yes | Array | 股票代码数组。 stockCodes长度>=1且<=100，格式如下：\["01336"\]。  请参考 [股票信息API](https://www.lixinger.com/open/api/detail?api-key=hk/company) 获取合法的stockCode。  需要注意的是，当传入startDate时只能传入一个股票代码。 |
| date | No | String: latest \| YYYY-MM-DD (北京时间) | 信息日期。 用于获取指定日期数据。  由于每个季度的最后一天为财报日，请确保传入正确的日期，例如：2017-03-31、2017-06-30、2017-09-30、2017-12-31 或 latest。  其中，传入 **latest** 会得到最近1.1年内的最新财报数据。  需要注意的是，startDate和date至少要传一个。 |
| startDate | No | String: YYYY-MM-DD (北京时间) | 信息起始时间。 用于获取一定时间范围内的数据。 开始和结束的时间间隔不超过10年  需要注意的是，startDate和date至少要传一个。 |
| endDate | No | String: YYYY-MM-DD (北京时间) | 信息结束时间。 用于获取一定时间范围内的数据。 默认值是上周一。  需要注意的是，请与startDate一起使用。 |
| limit | No | Number | 返回最近数据的数量。 limit仅在请求数据为date range的情况下生效。 |
| metricsList | Yes | Array | 指标数组，指标格式为 **\[granularity\].\[tableName\].\[fieldName\].\[expressionCalculateType\]** 。 比如，你想获取营业总收入累计原始值以及应收账款当期同比值，对应的metricsList设置为：\["q.ps.toi.t", "q.bs.ar.c\_y2y"\]。  需要注意的是，当stockCodes长度大于1时最多只能选取48个指标；当stockCodes长度等于1时最多只能获取128 个指标。  ##### 当前支持:  granularity  - 年:y - 半年:hy - 季度:q  expressionCalculateType  - 资产负债表: 	- 年(y): 		- 当期:t 		- 当期同比:t\_y2y 		- 当期环比:t\_c2c 	- 半年(hy): 		- 当期:t 		- 当期原始值:t\_o 		- 当期同比:t\_y2y 		- 当期环比:t\_c2c 		- 半年:c 		- 半年原始值:c\_o 		- 半年同比:c\_y2y 		- 半年环比:c\_c2c 	- 季度(q): 		- 当期:t 		- 当期原始值:t\_o 		- 当期同比:t\_y2y 		- 当期环比:t\_c2c 		- 单季:c 		- 单季原始值:c\_o 		- 单季同比:c\_y2y 		- 单季环比:c\_c2c - 利润表: 	- 年(y): 		- 累积:t 		- 累积原始值:t\_o 		- 累积同比:t\_y2y 	- 半年(hy): 		- 累积:t 		- 累积原始值:t\_o 		- 累积同比:t\_y2y 		- 累积环比:t\_c2c 		- 半年:c 		- 半年原始值:c\_o 		- 半年同比:c\_y2y 		- 半年环比:c\_c2c 		- 半年年比:c\_2y 		- TTM:ttm 		- TTM原始值:ttm\_o 		- TTM同比:ttm\_y2y 		- TTM环比:ttm\_c2c 	- 季度(q): 		- 累积:t 		- 累积原始值:t\_o 		- 累积同比:t\_y2y 		- 累积环比:t\_c2c 		- 单季:c 		- 单季原始值:c\_o 		- 单季同比:c\_y2y 		- 单季环比:c\_c2c 		- 单季年比:c\_2y 		- TTM:ttm 		- TTM原始值:ttm\_o 		- TTM同比:ttm\_y2y 		- TTM环比:ttm\_c2c - 现金流量表: 	- 年(y): 		- 累积:t 		- 累积原始值:t\_o 		- 累积同比:t\_y2y 	- 半年(hy): 		- 累积:t 		- 累积原始值:t\_o 		- 累积同比:t\_y2y 		- 累积环比:t\_c2c 		- 半年:c 		- 半年原始值:c\_o 		- 半年同比:c\_y2y 		- 半年环比:c\_c2c 		- 半年年比:c\_2y 		- TTM:ttm 		- TTM原始值:ttm\_o 		- TTM同比:ttm\_y2y 		- TTM环比:ttm\_c2c 	- 季度(q): 		- 累积:t 		- 累积原始值:t\_o 		- 累积同比:t\_y2y 		- 累积环比:t\_c2c 		- 单季:c 		- 单季原始值:c\_o 		- 单季同比:c\_y2y 		- 单季环比:c\_c2c 		- 单季年比:c\_2y 		- TTM:ttm 		- TTM原始值:ttm\_o 		- TTM同比:ttm\_y2y 		- TTM环比:ttm\_c2c  tableName.fieldName  - 资产负债表 	- 一、 资产总计: bs.ta 	- 货币资金: bs.cabb 	- 货币资金占比: bs.cabb\_ta\_r 	- 结算备付金: bs.sr 	- 拆出资金: bs.pwbaofi 	- 买入返售金融资产: bs.fahursa 	- 应收保费: bs.pr 	- 应收账款: bs.ar 	- 应收利息: bs.ir 	- 应收分保账款: bs.rir 	- 应收分保未到期责任准备金: bs.uprrfri 	- 应收分保未决赔款准备金: bs.crrfri 	- 应收分保寿险责任准备金: bs.lirrfri 	- 应收分保长期健康险责任准备金: bs.lthirrfri 	- 质押贷款净增加额: bs.niipl 	- 衍生金融资产: bs.dfa 	- 应收分保合同准备金: bs.crorir 	- 保户质押贷款: bs.phpl 	- 长期应收款: bs.ltar 	- 发放贷款及垫款: bs.laatc 	- 定期存款: bs.td 	- 金融投资：: bs.financial\_investing 	- # 指定以公允价值计量且其变动计入损益的金融投资(HK): bs.dfiafvtpol 	- # 以公允价值计量且其变动计入当期损益的金融投资: bs.fiafvtpol 	- # 以摊余成本计量的金融投资: bs.fiaac 	- # 以公允价值计量且其变动计入其他综合收益的债务工具投资: bs.diafvtoci 	- # 指定为以公允价值计量且其变动计入其他综合收益的权益工具投资: bs.deiafvtoci 	- # 持有至到期投资: bs.htmi 	- 长期股权投资: bs.ltei 	- 存出资本保证金: bs.sd 	- 投资性房地产: bs.rei 	- 物业、厂房及设备: bs.ppe 	- 不动产、厂房及设备占总资产比率: bs.ppe\_ta\_r 	- 商誉及无形资产: bs.gwaia 	- (其中) 商誉: bs.gw 	- (其中) 无形资产: bs.ia 	- 使用权资产: bs.roua 	- 递延所得税资产: bs.dita 	- 其他资产: bs.oa 	- 独立账户资产: bs.saa 	- 二、 负债合计: bs.tl 	- 资产负债率: bs.tl\_ta\_r 	- 短期借款: bs.stl 	- 向中央银行借款: bs.bfcb 	- 同业及其他金融机构存放款项: bs.dfbaofi 	- 拆入资金: bs.pfbaofi 	- 交易性金融负债: bs.tfl 	- 衍生金融负债: bs.dfl 	- 卖出回购金融资产: bs.fasurpa 	- 客户存款: bs.cd 	- 代理买卖证券款: bs.stoa 	- 应付账款: bs.ap 	- 预收账款: bs.afc 	- 预收保费: bs.pria 	- 应付手续费及佣金: bs.facp 	- 应付分保账款: bs.rip 	- 应付职工薪酬: bs.sawp 	- 应交税费: bs.tp 	- 应付利息: bs.intp 	- 应付赔付款: bs.cp 	- 应付保单红利: bs.phdp 	- 保户储金及投资款: bs.phd 	- 保险合同准备金: bs.icr 	- 未到期责任准备金: bs.uepr 	- 未决赔款准备金: bs.cr 	- 寿险责任准备金: bs.lir 	- 长期健康险责任准备金: bs.lthir 	- 长期借款: bs.ltl 	- 应付债券: bs.bp 	- 递延所得税负债: bs.ditl 	- 独立账户负债: bs.sal 	- 预计负债(非流动): bs.ncal 	- 其他负债: bs.ol 	- 三、 所有者权益合计: bs.toe 	- 股东权益占比: bs.toe\_ta\_r 	- 股本: bs.sc 	- 股本溢价: bs.spa 	- 其他权益工具: bs.oei 	- (其中) 优先股: bs.psioei 	- (其中) 永续债: bs.pcsioei 	- 资本公积: bs.capr 	- 减： 库存股: bs.is 	- 储备: bs.r 	- 专项储备: bs.rr 	- 其他储备: bs.ors 	- 盈余公积: bs.surr 	- 未分配利润: bs.rtp 	- 股份奖励计划所持股份: bs.shfsas 	- 可换股债券权益部分: bs.ecocb 	- 归属于母公司股东及其他权益持有者的权益合计: bs.tetshaoehopc 	- 归属于母公司普通股股东权益合计: bs.tetoshopc 	- 少数股东权益: bs.etmsh 	- 可赎回少数股东权益: bs.rnci 	- 四、 内含价值: bs.ev 	- (其中) 寿险及健康险业务内含价值: bs.evolahib 	- (其中) 寿险业务内含价值: bs.evolib 	- (其中) 健康险业务内含价值: bs.evohib 	- 四、 员工情况 	- 员工人数: bs.ep\_stn 	- 五、 股本、股东以及估值 	- 市值: bs.mc 	- 总股本: bs.tsc 	- PE-TTM: bs.pe\_ttm 	- PB: bs.pb 	- PS-TTM: bs.ps\_ttm 	- PCF-TTM: bs.pcf\_ttm 	- 股息率: bs.dyr - 利润表 	- 一、 营业收入: ps.oi 	- 已赚保费: ps.ep 	- 保险服务收入: ps.ir 	- 银行业务利息收入: ps.iifb 	- 非银行业务利息收入: ps.nbii 	- 非保险业务手续费及佣金收入: ps.nifaci 	- 对联营企业及合营企业的投资收益: ps.iifaajv 	- (其中) 对联营公司的投资收益: ps.iifa 	- (其中) 对合营企业的投资收益: ps.iifjv 	- 投资收益: ps.ivi 	- 其他收益: ps.oic 	- 公允价值变动收益: ps.ciofv 	- 汇兑收益: ps.ei 	- 资产处置收益: ps.adi 	- 其他业务收入: ps.ooi 	- 二、 营业支出: ps.oe 	- 退保金: ps.s 	- 保险合同赔付支出: ps.ce 	- (减) 摊回保险合同赔付支出: ps.crcfri 	- 提取保险责任准备金净额: ps.iiicr 	- (减) 摊回保险责任准备金: ps.irrcfri 	- 保单红利支出: ps.phdrfpip 	- 分保费用: ps.rie 	- 保险业务手续费及佣金支出: ps.faceoio 	- 保险服务费用: ps.ise 	- 分出保费的分摊: ps.aoripp 	- (减) 摊回保险服务费用: ps.arfri 	- 承保财务损益: ps.iifefici 	- (减) 分出再保险财务损益: ps.nrifefrich 	- 银行业务利息支出: ps.iefb 	- 非银行业务利息支出: ps.nbie 	- 非保险业务手续费及佣金支出: ps.niface 	- 税金及附加: ps.tas 	- 业务及管理费用: ps.baae 	- (减) 摊回分保费用: ps.ercfri 	- 资产减值损失: ps.ailor 	- 信用减值损失: ps.cilor 	- 其他资产减值损失: ps.oail 	- 三、 利润总额: ps.tp 	- 减： 所得税费用: ps.ite 	- 有效税率: ps.ite\_tp\_r 	- 四、 净利润: ps.np 	- 净利润率: ps.np\_s\_r 	- 归属于母公司股东及其他权益持有者的净利润: ps.npatshaoehopc 	- 归属于母公司普通股股东的净利润: ps.npatoshopc 	- 少数股东损益: ps.npatmsh 	- 可赎回少数股东权益利息及回购视同股利分配: ps.adddicwrornci 	- 非国际公认会计准则净利润: ps.nonifrs\_op 	- 非国际公认会计准则归属于母公司股东净利润: ps.nonifrs\_opatoehopc 	- 五、 基本每股收益: ps.beps 	- 稀释每股收益: ps.deps 	- 六、 综合收益总额: ps.tci 	- 归属于母公司股东及其他权益持有者的综合收益总额: ps.tciatshaoehopc 	- 归属于母公司普通股股东的综合收益总额: ps.tciatoshopc 	- 归属于少数股东的综合收益总额: ps.tciatmsh 	- 可赎回少数股东权益的综合收益: ps.tciatrnci 	- 其他综合收益的税后净额: ps.natooci 	- 七、 分红、回购及涨跌幅 	- 分红金额: ps.da 	- H股分红金额: ps.da\_om 	- 分红率: ps.d\_np\_r 	- 回购金额: ps.ra 	- 年度涨跌幅: ps.spc\_a - 现金流量表 	- 经营活动产生的现金流量净额: cfs.ncffoa 	- 投资活动产生的现金流量净额: cfs.ncffia 	- 筹资活动产生的现金流量净额: cfs.ncfffa 	- 现金及现金等价物的净增加额: cfs.niicace 	- 期初现金及现金等价物的余额: cfs.bocaceatpb 	- 汇率变动对现金及现金等价物的影响: cfs.iocacedtfier 	- 期末现金及现金等价物净余额: cfs.bocaceatpe - 财务指标 	- 一、 人均指标 	- 员工人数: m.ep\_stn (expressionCalculateType参考资产负债表) 	- 人均营业收入: m.oi\_pc (expressionCalculateType参考利润表) 	- 人均净利润: m.np\_pc (expressionCalculateType参考利润表) 	- 二、 每股指标 	- 总股本: m.tsc (expressionCalculateType参考资产负债表) 	- 归属于母公司普通股股东的每股收益: m.npatoshopc\_ps (expressionCalculateType参考利润表) 	- 归属于母公司普通股股东的每股股东权益: m.tetoshopc\_ps (expressionCalculateType参考资产负债表) 	- 每股经营活动产生的现金流量净额: m.ncffoa\_ps (expressionCalculateType参考现金流量表) 	- 每股资本公积: m.cr\_ps (expressionCalculateType参考资产负债表) 	- 每股未分配利润: m.rp\_ps (expressionCalculateType参考资产负债表) 	- 每股分红: m.da\_ps (expressionCalculateType参考利润表) 	- 三、 盈利能力 	- 归属于少数股股东的ROE: m.roe\_atomsh (expressionCalculateType参考利润表) 	- 归属于母公司普通股股东的ROE: m.roe\_atoshaopc (expressionCalculateType参考利润表) 	- 净资产收益率(ROE): m.roe (expressionCalculateType参考利润表) 	- 杠杆倍数: m.l (expressionCalculateType参考资产负债表) 	- 总资产收益率(ROA): m.roa (expressionCalculateType参考利润表) 	- 总资产周转率: m.ta\_to (expressionCalculateType参考利润表) 	- 净利润率: m.np\_s\_r (expressionCalculateType参考利润表) 	- 四、 营运能力(周转率) 	- 不动产、厂房及设备周转率: m.ppe\_tor (expressionCalculateType参考利润表) 	- 五、 营运能力(周转天数) 	- 不动产、厂房及设备周转天数: m.ppe\_ds (expressionCalculateType参考利润表) 	- 股东权益周转天数: m.toe\_ds (expressionCalculateType参考利润表) 	- 总资产周转天数: m.ta\_ds (expressionCalculateType参考利润表) 	- 六、 偿债及资本结构 	- 资产负债率: m.tl\_ta\_r (expressionCalculateType参考资产负债表) 	- 七、 现金流量 	- 经投融产生的现金流量净额: m.ncffoaiafa (expressionCalculateType参考现金流量表) |

**返回数据说明:**

| 参数名称 | 数据类型 | 说明 |
| --- | --- | --- |
| date | Date | 财报日期 |
| reportDate | Date | 公告时间 |
| standardDate | Date | 标准财年时间（不同公司的财年不一样，有的年报12月结束，有的却是3月结束，还有的7月结束。例如2017-01-01到2017-06-30结束的年报，调整到2016-Q4，其余的季报和中报都相应的做类似调整。调整后具有通用性。） |
| stockCode | String | 股票代码 |
| reportType | String | 财报类型 |
| currency | String | 货币类型 |
| auditOpinionType | String | 审计意见  - 无保留意见:unqualified\_opinion - 保留意见:qualified\_opinion - 保留意见与解释性说明:qualified\_opinion\_with\_explanatory\_notes - 否定意见:adverse\_opinion - 拒绝表示意见:disclaimer\_of\_opinion - 解释性说明:explanatory\_statement - 无法表示意见:unable\_to\_express\_an\_opinion - 带强调事项段的无保留意见:unqualified\_opinion\_with\_highlighted\_matter\_paragraph |