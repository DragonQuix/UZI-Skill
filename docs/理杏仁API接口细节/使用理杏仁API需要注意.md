使用理杏仁API需要注意:

1. 在请求的headers里面设置Content-Type为application/json。
2. 请求headers的accept-encoding必须包含gzip, 其他选项可为deflate, br, *。
3. 每分钟最大请求次数为1000次，如果超过1000次，请求将失败返回状态码 429(Too Many Request)。
4. 抓取爬虫一般需要有重试机制，以避免在网络问题或者出现其他不可知问题时造成爬虫挂掉。
5. 理杏仁开放平台每分钟检查一次服务器状态，理论上任何时候服务器出现问题，我们将在一分钟内发现问题，如果您发现有接口请求问题，请稍作等待，如果还是有问题请及时与我们联系。
6. 请参考[股票信息API](https://www.lixinger.com/open/api/detail?api-key=cn/company)获取合法的stockCode。stockCode仅在请求数据为date range的情况下生效。
7. 获取一定时间范围内的数据。开始和结束的时间间隔不超过10年。

