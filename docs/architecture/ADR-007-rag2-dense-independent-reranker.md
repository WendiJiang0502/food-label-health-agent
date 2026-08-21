# ADR-007：中文 Dense Retrieval 与独立 Reranker

状态：Accepted，真实消融通过并已切换默认
日期：2026-08-12

## 背景

RAG 1.0 使用 BM25、人工领域概念扩展和 TF-IDF 余弦相似度，再通过固定权重合并主题、标准号和权威等级信号。它可离线运行且安全，但不能充分处理中文口语化改写；原有 `rerank_score` 只是公式加权，并不是独立模型重排。

## 决策

保留 RAG 1.0 作为可复现 fallback，新增四个可评测 Profile：

1. `bm25`：纯关键词基线；
2. `hybrid_tfidf`：现有 RAG 1.0；
3. `hybrid_dense`：BM25 与 Dense Embedding 通过 RRF 融合；
4. `hybrid_dense_rerank`：对 Dense Hybrid 候选运行独立模型重排。

Dense Provider 默认使用 OpenAI `text-embedding-3-large`，通过 `dimensions=1024` 控制索引体积。向量在本地进行 L2 归一化并使用余弦相似度；文档向量在进程内按文本缓存。OpenAI 官方 Embeddings 指南说明了批量输入、余弦检索和 `dimensions` 参数：[Vector embeddings](https://developers.openai.com/api/docs/guides/embeddings#obtaining-the-embeddings)。

独立 Reranker 使用 Responses API 严格 JSON Schema，只能返回已过滤候选的 `evidence_id` 排序。它不能生成条款、修改法规版本或回答用户问题。请求设置 `store: false`。

## 安全顺序

```text
jurisdiction/date/topic/explicit-standard filter
→ BM25 + Dense candidate retrieval
→ Reciprocal Rank Fusion
→ independent reranker over at most 20 evidence IDs
→ local evidence/result serialization
```

法域、适用日期、明确指定标准号和主题过滤在任何远程 Embedding 或 Reranker 调用之前完成。失效、尚未生效或错误法域的条款不会进入模型候选集。模型不能把被过滤条款重新加入结果。

如果 Dense 或 Reranker Provider 不可用，调用返回结构化工具失败，由现有 MCP 重试与最终安全门处理；系统不会悄悄把失败的 RAG 2.0 标记为成功。部署者可以显式切回 `hybrid_tfidf`。

## 数据处理

启用远程 RAG 2.0 时，法规查询和已通过本地安全过滤的官方候选条款会发送至 OpenAI。原始食品图片不会发送给 RAG Provider。健康接口和网页隐私提示会披露当前 Profile、模型以及是否存在远程处理。

## 消融评测

`rag2_ablation_v1` 使用 12 个条款级中文问题，不再只判断是否命中正确标准号，而是检查具体 `evidence_id`。它覆盖：

- 复合配料与配料排序；
- 添加剂名称标示；
- 当前与未来版本的过敏原提示；
- 核心营养素、营养表格式和计量口径；
- 氢化油与反式脂肪；
- 无糖声称；
- 营养标签豁免；
- 无适用版本时的正确拒答。

每个 Profile 记录 Recall@5、MRR、nDCG@5、Top-1、官方证据率、无证据拒答、版本违规和端到端耗时。RAG 2.0 只有同时满足以下条件才通过：

- Dense Recall@5 不低于 RAG 1.0；
- Reranker Recall@5 和 MRR 不低于 Dense Hybrid；
- 最终 RAG 2.0 相比 RAG 1.0 至少一个主要质量指标严格提升；
- 官方证据率和无证据拒答率为 100%；
- 版本违规为 0。

离线统一评测只运行 BM25 与 RAG 1.0，不会意外调用远程服务。真实四组消融必须显式运行 `food-label-rag-eval --live`。2026-08-12 的验收运行全部通过，结果记录于 [`../evaluation/RAG2_EVALUATION_2026-08-12.md`](../evaluation/RAG2_EVALUATION_2026-08-12.md)。

## 后果

Dense 与 Reranker 是可替换 Provider，不进入法规数据模型。未来可以接入本地中文 embedding 或 cross-encoder，而不改变法规条款、MCP 合同、安全过滤和评测数据。真实消融证明质量提升且安全门无回归后，默认 Profile 已切换为 `hybrid_dense_rerank`；`hybrid_tfidf` 继续作为显式离线和应急回退。
