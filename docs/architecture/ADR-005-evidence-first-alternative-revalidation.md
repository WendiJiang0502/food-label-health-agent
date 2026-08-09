# ADR-005：证据优先的替代品检索与二次验证

状态：Accepted  
日期：2026-08-09

## 背景

替代品推荐不能依靠商品标题、“无乳”等营销词或模型联想。候选商品与当前商品一样，必须具备可追溯标签事实，并重新运行用户的全部硬约束。标签缺失、过期或内容被篡改时，候选不得进入推荐。

## 决策

Milestone 4 使用可替换的 `ProductCatalog` 边界。首个适配器是随包发布的人工审查验收目录，用于离线、确定性地验证完整安全链；目录明确标记为 `curated_verification_catalog`，不表达商品在售、库存或商业推荐。后续商城、厂商或用户上传目录必须实现相同证据合同。

每条候选记录必须包含：

- 商品、地区、品类和使用场景；
- 已确认配料、过敏原声明与可选营养数据；
- 标签确认日期、有效期和确认方式；
- 标签证据 ID、逻辑来源地址和 SHA-256 内容哈希；
- 标签证据完整度。

工作流固定为：

```text
find_alternative_products
→ revalidate_alternatives
→ compare_food_products
→ final_safety_gate
```

`find_alternative_products` 先按品类和地区查询，并排除不完整、过期、未来日期、过旧或哈希不匹配的标签。`revalidate_alternatives` 对剩余每个候选独立调用原有确定性约束服务。只有整体风险为 `compatible` 的候选才能标记 `eligible`；`avoid`、`caution` 和 `unknown` 都不得进入推荐。`compare_food_products` 仅比较单位和包装口径完全一致的营养数据。

## LangGraph 与状态

显式替代品请求进入：

```text
react_orchestrator
→ search_alternatives
→ revalidate_alternatives
→ final_safety_gate
```

使用 `AgentState.alternative_request`、`alternatives` 和 `alternative_comparison`。最终安全门阻断未复核候选、风险不为 `compatible` 的 eligible 候选，以及缺少标签证据的候选。替代品结论不能改变当前商品已经产生的风险等级。

## 未知项与产品边界

- 没有当前且完整的候选标签时返回 `unknown`；
- 没有候选通过二次验证时返回 `unknown`；
- 营养口径或单位不一致时只拒绝该项比较，不换算或猜测；
- “通过复核”仅表示在当前确认标签和规则范围内未发现约束冲突，不表示绝对安全；
- 验收目录中的示例名称不代表真实在售商品。

## 发布阻断评测

以下指标必须全部通过：

- 硬约束违反率为 0；
- 标签证据覆盖率为 100%；
- 候选重新验证率为 100%；
- 推荐理由可追溯率为 100%；
- 固定案例结果准确率为 100%；
- 营养比较口径完整性为 100%。
