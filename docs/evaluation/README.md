# 评测与验证

先区分三个问题：程序是否按规则执行、真实资料是否足够、真实用户能否完成任务。它们不能用一个通过率替代。

## 当前商品证据验证（2026-10-05）

- [统一流程隔离验证](../../artifacts/evidence-refactor-2026-10-05/local-validation.json)：只读正式来源、临时数据库，66 条受支持官网候选进入索引，不提升推荐资格。
- [50 组模拟评测与界面验证](../../artifacts/evidence-ui-evaluation-2026-10-05/report.md)：合成规则期望及真实资料覆盖分开统计；不是独立人工商品标注集。
- [公开来源扩充](../../artifacts/public-expansion-2026-10-04/report.md)：记录来源、数量和资料限制。
- [配料字段与糖缺口](../../artifacts/sugar-ingredient-enrichment-2026-10-04/report.md)：正向配料证据不等于总糖数值或成分缺失证明。
- [国内 API 小样本方案](domestic-pilot-v1.md)：验证接口是否能提供有用字段，不用接口命中率替代精确 SKU 核实。

## 可复现命令

在安装开发依赖后，从仓库根目录运行：

```bash
.venv/bin/python -m pytest -q --cov=food_label_agent --cov-branch --cov-fail-under=70
food-label-eval --profile development --json /tmp/food-label-evaluation.json
food-label-conversation-eval --json /tmp/conversation-evaluation.json
```

普通测试默认使用离线检索配置；对话评测加入 `--live` 才调用真实模型并产生费用。正式发布还需要独立 OCR 数据：

```bash
food-label-eval --profile release \
  --ocr-images /secure/private-label-benchmark \
  --json /tmp/release-evaluation.json
```

真人任务与结果模板位于 [任务定义](../../src/food_label_agent/evaluation/data/m9_pilot_tasks.json) 和 [真人结果模板](../../evaluation/pilot/m9_human_results.template.json)。不得用合成用户替代真人结果。

## 历史基线

下列文档按日期保留，以便追溯当时数据、方法与阻断项；其测试数、延迟和覆盖率不是最新重跑结果。

| 主题 | 历史报告 |
| --- | --- |
| Planner / 法规 RAG | [Planner](PLANNER_EVALUATION_2026-08-12.md)、[RAG2](RAG2_EVALUATION_2026-08-12.md) |
| 多轮对话 | [对话基线](CONVERSATION_AGENT_EVALUATION_2026-09-11.md)、[M8](CONVERSATION_AGENT_M8_EVALUATION_2026-09-11.md) |
| 封闭试用准备 | [完整评测](PREPILOT_FULL_EVALUATION_2026-09-12.md)、[M9 就绪评测](M9_CLOSED_PILOT_READINESS_2026-09-12.md) |
| 替代品目录 | [目录与留出集](ALTERNATIVE_CATALOG_EXPANSION_2026-09-12.md) |
| 标签与内部试点数据 | [真实标签采集](REAL_LABEL_COLLECTION_V1.md)、[内部数据集](INTERNAL_PILOT_DATASET_V1.md) |

下一阶段需要独立真实查询与商品标注，并固定样本对照 RAG 开关、召回方式和重排方式。观察可用候选召回、误通过、未知率、延迟与费用，不能只比较商品总数。
