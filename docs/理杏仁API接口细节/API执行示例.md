API执行示例，通过时间范围获取：

```
{
	"token": "XXXXXXXXXXXXXXXXXXXXXXXXXXXXXX",
	"startDate": "2025-02-26",
	"endDate": "2025-02-28",
	"stockCodes": [
		"300750"
	],
	"metricsList": [
		"pe_ttm",
		"mc",
		"pe_ttm.y3.cvpos"
	]
}
```

返回数据：

```
{
  "code": 1,
  "message": "success",
  "data": [
    {
      "date": "2025-02-28T00:00:00+08:00",
      "mc": 1163817274977.3,
      "pe_ttm": 23.7626,
      "stockCode": "300750",
      "pe_ttm.y3.cvpos": 0.4532
    },
    {
      "date": "2025-02-27T00:00:00+08:00",
      "mc": 1188916625970,
      "pe_ttm": 24.2751,
      "stockCode": "300750",
      "pe_ttm.y3.cvpos": 0.5083
    },
    {
      "date": "2025-02-26T00:00:00+08:00",
      "mc": 1182839940992.82,
      "pe_ttm": 24.151,
      "stockCode": "300750",
      "pe_ttm.y3.cvpos": 0.4966
    }
  ]
}
```