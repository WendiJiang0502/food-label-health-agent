# 文档导航

当前功能与启动步骤以 [项目 README](../README.md) 为入口。架构决策解释为什么这样实现，带日期的评测和历史记录只代表当时版本。

| 你要了解什么 | 阅读入口 |
| --- | --- |
| 产品目标与界面约束 | [产品上下文](../PRODUCT.md)、[设计系统](../DESIGN.md)、[长期产品方向](product/FINAL_AGENT_NORTH_STAR.md) |
| Agent 与双 RAG 的结构 | [架构决策目录](architecture/README.md) |
| 本轮入口、证据与补齐重构 | [ADR-012](architecture/ADR-012-unified-product-evidence-flow.md) |
| 部署、持久化、备份 | [国内部署](DEPLOYMENT_CN.md) |
| 腾讯 / Paddle OCR 配置 | [腾讯指南](ocr/TENCENT_CLOUD_CONFIGURATION_GUIDE.md)、[Paddle 指南](ocr/PP-OCRv6_CONFIGURATION_GUIDE.md) |
| 怎么评测、如何理解数字 | [评测导航](evaluation/README.md) |
| 法规语料来源 | [官方来源清单](regulations/OFFICIAL_SOURCE_MANIFEST.md) |
| 发布前还有什么条件 | [生产验证计划](PRODUCTION_VALIDATION_PROGRAM.md)、[隐私与合规清单](PRIVACY_COMPLIANCE_READINESS.md) |
| 过去发生了什么 | [历史记录](archive/README.md) |

## 文档维护约定

- README 只展示当前阶段、运行方式、关键验证和未解决事项；不要在文末反复追加功能段落。
- 新架构决策使用唯一且递增的 ADR 编号，并加入目录。
- 评测写明日期、数据集、执行范围和限制，原始结果留在 `artifacts/`。
- 没有实质变化时不新增仓库日报；历史流水记录不作为当前状态页。
- 代码使用的 JSON 数据集、审核样本与原始验证产物不是重复说明文档，不因精简导航而删除。
