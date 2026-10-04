# 薄荷接口首次验证

2026-10-04：本地Key已通过真实接口认证。共2次请求（条码搜索1次、商品详情1次），均成功。未修改正式知识库，尚未完成批量适配。

条码6973662540013命中SO ACAI 燕麦300g，食物编码fd304993。详情返回热量375 kcal、蛋白质12g、脂肪8.6g、碳水56.2g、膳食纤维11.6g；搜索文档标注主要营养值按100g。数据尚未对照包装核实。

重要：ingredients字段是营养素列表，不等同于包装配料表。糖、钠等大量字段返回0，但没有字段完整性标识，不能将这些0直接当作已核实的零含量，不能支持无糖、低钠等推荐结论。完整配料和包装证据仍需验证。

官方文档：https://ai.boohee.com/docs/
文档来源：https://api.boohee.com/open-interface/v1/panel/docs-index?code=boohee.ai
认证：X-Api-Key。路径：/open-apis/v1/food/search 与 /open-apis/v1/food/detail。详情查询已开启with_ingredients、with_materials及with_units。

原始响应独立保存在probe.json和detail.json，不含请求密钥。请求次数不等同于计费额度，实际扣费以供应商后台为准。
