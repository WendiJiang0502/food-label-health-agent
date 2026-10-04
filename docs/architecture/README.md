# 架构决策目录

技术形态：Python 模块化单体，Starlette 网页/API，LangGraph 受控工作流，独立知识刷新进程。法规语料与商品证据分别检索，确定性规则负责约束与最终安全门。

## Agent 与安全工作流

| 决策 | 主题 |
| --- | --- |
| [ADR-001](ADR-001-agent-state-and-safety-routing.md) | Agent 状态与安全路由 |
| [ADR-002](ADR-002-constrained-react-tool-loop.md) | 受约束 ReAct 与工具轨迹 |
| [ADR-004](ADR-004-context-checkpoints-and-consented-memory.md) | 检查点与授权记忆 |
| [ADR-006](ADR-006-policy-guarded-model-planner.md) | 策略保护的模型 Planner |

## 法规与商品知识

| 决策 | 主题 |
| --- | --- |
| [ADR-003](ADR-003-versioned-hybrid-regulation-retrieval.md) | 版本化法规混合检索 |
| [ADR-007](ADR-007-rag2-dense-independent-reranker.md) | 向量召回与独立重排 |
| [ADR-005](ADR-005-evidence-first-alternative-revalidation.md) | 替代品证据门与独立复核 |
| [ADR-008](ADR-008-product-knowledge-refresh.md) | 商品知识库与月度复查 |
| [ADR-009](ADR-009-product-evidence-rag.md) | 商品证据 RAG |
| [ADR-010](ADR-010-product-intent-field-evidence-evaluation.md) | 查询意图、字段证据与评测 |
| [ADR-011](ADR-011-batch-product-admission.md) | 批次准入与异常复核 |
| [ADR-012](ADR-012-unified-product-evidence-flow.md) | 入口统一、官网证据投影与补齐回流 |

[2026-10-05 顶层审查](reviews/2026-10-05-top-down-architecture-review.md) 记录重构前发现的问题。后续已实现的修复以 ADR-012 和当前代码为准；旧审查中的运行状态不是最新发布承诺。
