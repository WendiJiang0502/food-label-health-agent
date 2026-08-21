# RAG 2.0 真实消融验收记录

日期：2026-08-12  
基准：`rag2_ablation_v1`  
Dense Provider：OpenAI  
Embedding 模型：`text-embedding-3-large`（1024 维）  
Reranker 模型：`gpt-5.6-terra`  
案例数：12

## 结论

RAG 2.0 通过真实四组消融验收，无发布阻断。最终 `hybrid_dense_rerank` 在 11 个有答案案例上实现 Recall@5、MRR、nDCG@5 和 Top-1 全部为 1.0；相对 RAG 1.0，Recall@5 提升 9.09 个百分点，MRR 提升 18.18 个百分点，nDCG@5 提升 15.80 个百分点。

所有 Profile 的官方证据率和无证据拒答准确率均为 100%，版本违规为 0。依据 ADR-007 的预设门禁，生产默认 Profile 切换为 `hybrid_dense_rerank`，并保留 `hybrid_tfidf` 作为显式离线和应急回退。

## 汇总指标

| Profile | Recall@5 | MRR | nDCG@5 | Top-1 | 官方证据率 | 无证据拒答 | 版本违规 | 耗时 |
|---|---:|---:|---:|---:|---:|---:|---:|---:|
| `bm25` | 90.91% | 81.82% | 84.20% | 72.73% | 100% | 100% | 0 | 53.20 ms |
| `hybrid_tfidf` | 90.91% | 81.82% | 84.20% | 72.73% | 100% | 100% | 0 | 137.55 ms |
| `hybrid_dense` | 100% | 93.94% | 95.45% | 90.91% | 100% | 100% | 0 | 29.53 s |
| `hybrid_dense_rerank` | 100% | 100% | 100% | 100% | 100% | 100% | 0 | 85.65 s |

耗时是一次本地串行验收运行的端到端观测值，不作为稳定的线上延迟承诺。当前小样本结果证明了门禁内的提升，但不代表对所有真实查询的泛化质量已经达到 100%。

## 验收判定

- Dense Recall@5 不低于 RAG 1.0：通过（100% 对 90.91%）；
- Reranker Recall@5 不低于 Dense Hybrid：通过（100% 对 100%）；
- Reranker MRR 不低于 Dense Hybrid：通过（100% 对 93.94%）；
- 最终 RAG 2.0 至少一个主要质量指标严格提升：通过；
- 官方证据率和无证据拒答率为 100%：通过；
- 版本违规为 0：通过；
- Provider 均完成、发布阻断为 0：通过。

最终判定：**RAG 2.0 benchmark v1 通过。**

## 默认链路与回退

默认链路为 `hybrid_dense_rerank`，需要服务端配置 `OPENAI_API_KEY`。Dense 或 Reranker Provider 失败时系统保持失败关闭，不会把 RAG 2.0 错误标记为成功，也不会生成无依据结论。

离线运行或应急回退：

```bash
export FOOD_LABEL_RAG_PROFILE=hybrid_tfidf
```

更换 Embedding 模型、向量维度、Reranker 模型、法规语料、融合算法或评测集后，必须重新执行 `food-label-rag-eval --live` 并记录新的验收结果。
