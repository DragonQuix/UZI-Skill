# 理杏仁 API 接口文档索引

> 评审 P3-3 修复：原 24 个 md 文件批量入库时缺索引、来源、抓取时间、调用方信息，
> 无法追溯对应 API 的版本。本索引补齐校验信息，并对未接驳代码的文档标注状态。

## 来源与时效

- 供应商：理杏仁开放平台（https://www.lixinger.com/open/api/doc）
- 抓取时间：2026-02-26（部分文档头内 `过期时间: 2026-03-02`）
- 抓取方式：网页剪藏（front-matter 标记 `clippings`），非官方 SDK 推送
- 注意：理杏仁接口可能迭代，使用前请到官方文档页核对最新字段名与限流策略

## 实际调用方

- 唯一代码接入点：`skills/deep-analysis/scripts/lib/lixinger_client.py`
  - Base URL: `https://open.lixinger.com/api`
  - 启用方式：设置 `MX_APIKEY` 或在 `.env` 配置理杏仁 token
- 数据源路由：`skills/deep-analysis/scripts/lib/data_sources.py`（按 tier 选择）
- 缓存：`skills/deep-analysis/scripts/lib/cache.py`

## 文档清单与端点映射

| 文档 | 对应 API 端点 | 代码调用方 | 状态 |
|---|---|---|---|
| 基础信息公司接口大陆API文档开放平台 - 理杏仁.md | `POST /api/cn/company` | `lixinger_client.fetch_basic` 等多个分支 | 启用 |
| 基础信息公司接口香港API文档开放平台 - 理杏仁.md | `POST /api/hk/company` | `lixinger_client` HK 分支 | 启用 |
| 非金融财务报表公司接口大陆API文档开放平台 - 理杏仁.md | `POST /api/cn/company/fs/non_financial` | `fetch_financials` 非金融分支 | 启用 |
| 非金融财务报表公司接口香港API文档开放平台 - 理杏仁.md | `POST /api/hk/company/fs/non_financial` | `fetch_financials` HK 非金融 | 启用 |
| 银行财务报表公司接口大陆API文档开放平台 - 理杏仁.md | `POST /api/cn/company/fs/bank` | `fetch_financials` 银行分支 | 启用 |
| 银行财务报表公司接口香港API文档开放平台 - 理杏仁.md | `POST /api/hk/company/fs/bank` | `fetch_financials` HK 银行 | 启用 |
| 证券财务报表公司接口大陆API文档开放平台 - 理杏仁.md | `POST /api/cn/company/fs/security` | `fetch_financials` 证券分支 | 启用 |
| 证券财务报表公司接口香港API文档开放平台 - 理杏仁.md | `POST /api/hk/company/fs/security` | `fetch_financials` HK 证券 | 启用 |
| 其他金融财务报表公司接口大陆API文档开放平台 - 理杏仁.md | `POST /api/cn/company/fs/other_financial` | `fetch_financials` 其他金融分支 | 启用 |
| 其他金融财务报表公司接口香港API文档开放平台 - 理杏仁.md | `POST /api/hk/company/fs/other_financial` | `fetch_financials` HK 其他金融 | 启用 |
| 保险财务报表公司接口大陆API文档开放平台 - 理杏仁.md | `POST /api/cn/company/fs/insurance` + `/fundamental/insurance` | `fetch_financials` 保险分支 | 启用 |
| 保险财务报表公司接口香港API文档开放平台 - 理杏仁.md | `POST /api/hk/company/fs/insurance` + `/fundamental/insurance` | `fetch_financials` HK 保险 | 启用 |
| 房地产投资信托财务报表公司接口香港API文档开放平台 - 理杏仁.md | `POST /api/hk/company/fs/...` (REIT 专项) | `fetch_financials` HK REIT 分支 | 启用 |
| 理杏仁：大宗交易公司接口（大陆）.md | `POST /api/cn/company/block-deal` | `lixinger_client.fetch_block_deals` | 启用 |
| 理杏仁：公募基金持股股东公司接口（大陆）.md | `POST /api/cn/company/fund-shareholders` | `lixinger_client` 基金股东分支 | 启用 |
| 理杏仁：股东股东人数公司接口（大陆）.md | `POST /api/cn/company/shareholders-num` | `lixinger_client.fetch_shareholders_num` | 启用 |
| 理杏仁：股票所属行业公司接口（大陆）.md | `POST /api/cn/company/industries` | `lixinger_client.fetch_industry` | 启用 |
| 理杏仁：股票所属行业公司接口（香港）.md | `POST /api/hk/company/industries` | `lixinger_client` HK 行业分支 | 启用 |
| 理杏仁：基金公司持股股东公司接口（大陆）.md | 基金管理公司持股 | `lixinger_client` 接驳分支 | 启用 |
| 理杏仁：龙虎榜公司接口（大陆）.md | `POST /api/cn/company/...` (lhb 端点) | `lixinger_client.fetch_lhb_detail` | 启用 |
| 理杏仁：融资融券热度数据公司接口（大陆）.md | `POST /api/cn/company/hot/elr` | `lixinger_client.fetch_hot_elr` | 启用 |
| 理杏仁：限售解禁热度数据公司接口（大陆）.md | `POST /api/cn/company/hot/mtasl` | `lixinger_client.fetch_hot_mtasl` | 启用 |
| 使用理杏仁API需要注意.md | 限流 / token / 字段口径通用说明 | 全代码适用 | 参考 |
| API执行示例.md | 请求体格式示例 | 全代码适用 | 参考 |

## 状态说明

- 启用：代码已实际接驳该端点
- 参考：不对应单一代码调用，但是接驳时必读的口径说明
- 未启用：未来计划接驳（当前无）

如果理杏仁接口迭代，请同时更新此索引与 `lib/lixinger_client.py` 顶部 docstring，
避免文档与代码脱钩。
