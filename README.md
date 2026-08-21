# Food Label Health Agent

一个以食品标签健康信息解释为核心的多模态 Agent。目标架构为：

- 单个模块化 MCP Server
- LangGraph 状态机
- 混合 RAG（关键词 + 向量 + 重排 + 版本过滤）
- 确定性过敏原规则引擎

当前阶段已完成工程骨架、Agent 状态协议、安全路由、配料树状规范化、中国八类常见致敏物质的确定性规则，以及从图片上传、人工确认到个人约束评估的网页闭环。平台默认使用腾讯云高精度 OCR，也可由部署者切换到本地 PP-OCRv6；任何模型识别结果仍必须经过证据检查和必要的人工确认。法规层已经具备官方标准注册、结构化 PDF 分片、版本/适用日期过滤，以及 BM25 与领域 TF-IDF 向量召回的混合检索；融合重排同时记录关键词、向量、主题、标准号和权威等级信号。配料解释会绑定具体官方条款，并由最终安全门阻断失效引用和风险降级。营养事实层会规范化营养素、数值、单位、计量口径和原始行证据，并以确定性规则比较用户自行设置的营养上限；不同口径不自动换算。包装声称层已支持“无糖、低糖、无蔗糖、不添加糖、不添加蔗糖”的非等价解释，并交叉核对已确认的配料与糖含量。添加剂解释词典 `cn.v2` 已覆盖常见改性淀粉、乳化剂、抗氧化剂、抗结剂、增味剂和着色剂，并将身份词典事实与 GB 2760 法规来源分开呈现；OCR 行内断开的已知名称会在保留原始证据位置的同时完成规范化。没有食品类别、实际用量和标准明细表证据时，不生成合规或健康安全结论。

当前主流程还加入了受约束 ReAct 编排节点：它只能在四个已批准 MCP 工具中动态选择法规检索、配料解释、声称解释和一致性验证，并受步骤数与工具调用数双重预算约束。默认策略保持完全确定性；部署者也可启用模型辅助 Planner，让模型仅从策略生成的合法动作 ID 中提出下一步，再由系统校验并生成不可篡改的工具参数。标签确认、规范化、确定性约束评估和最终安全门仍是不可跳过的固定节点。API 返回只包含工具名、决策原因码、模型调用元数据和压缩后的工具观察，不记录或暴露模型思维链。

法规检索现已默认使用经真实消融验收的 RAG 2.0 链路：中文 Dense Embedding 与 BM25 通过 RRF 融合，再由独立模型只对已通过法域、日期和版本过滤的 evidence ID 进行重排。RAG 1.0 的 `hybrid_tfidf` 保留为可复现、无需远程 Provider 的显式回退链路。

OCR、人工确认、约束评估、法规解释和替代品复核现在共用一份可恢复的 `AgentState`。每次安全停点都会追加 SQLite 检查点；`workflow_trace` 记录 LangGraph 节点转换，`agent_trace` 记录 MCP 工具选择。可重试工具失败最多自动重试一次，仍失败则输出 `unknown` 并阻断肯定结论。每个完成结果还包含 `release_gate`，用于确认必经节点和 `final_safety_gate` 未被绕过。

替代品层已经实现 `find_alternative_products`、`compare_food_products` 和 `revalidate_alternatives` 三个真实 MCP 工具，以及 `search_alternatives → revalidate_alternatives → final_safety_gate` 安全路径。正式 CLI 默认通过 `ProductCatalog` 从 Open Food Facts 查找中国商品，仅接受具有配料文字、配料图片、社区完成状态和数据版本的记录；实时源失败或无可用证据时，显式降级到随包的人工审查验收目录。所有候选仍先检查完整度、日期和内容哈希，再逐一重跑相同的过敏原与营养约束；只有 `compatible` 候选能够展示。这不表示商品在售、有库存或绝对安全。

Milestone 4 已加入按节点裁剪的四层上下文构建器、Token 预算，以及 SQLite 短期工作流检查点。检查点采用随机能力令牌保护并强制移除原始图片。长期记忆只在用户明确勾选授权后保存其主动选择的约束；用户可查看、单项删除，或清除全部内容并撤销授权。浏览器只保留该本地资料的访问令牌，不保存食品图片、完整对话、模型内部推理或未经确认的健康推断。

## 设计原则

- 标签事实、规则判断和模型解释分层；
- 高风险结论必须可追溯；
- OCR 关键字段不可靠时先请求确认；
- 过敏原安全门不能被 LLM 跳过；
- 法规按法域、版本和适用日期检索；
- 替代品先经过硬约束过滤，再进行偏好排序。

## 本地验证

核心安全协议只依赖 Python 标准库：

```bash
PYTHONPATH=src python3 -m unittest discover -s tests -v
PYTHONPATH=src python3 -m food_label_agent
```

安装完整开发依赖后，可继续接入 LangGraph 和 MCP SDK：

```bash
python3 -m venv .venv
source .venv/bin/activate
python3 -m pip install -e '.[dev]'
```

启动本地平台：

```bash
food-label-platform
```

然后访问 `http://127.0.0.1:8000`。项目 CLI 默认使用腾讯云 OCR；这个默认值只包含 Provider 选择，不包含任何密钥。凭证继续由腾讯云 SDK 的环境变量或 `~/.tencentcloud/credentials` 提供。上传图片会发送到腾云 OCR，本平台不持久化原图。如需本地识别，可显式设置 `FOOD_LABEL_OCR_PROVIDER=paddle`。

正式 CLI 同时默认设置 `FOOD_LABEL_PRODUCT_CATALOG=hybrid`：优先访问 Open Food Facts，不可用时使用内置验收目录。生产部署应用可识别应用与联系方式的 User-Agent：

```bash
export FOOD_LABEL_PRODUCT_CATALOG=hybrid
export FOOD_LABEL_OPENFOODFACTS_USER_AGENT='LabelLensHealth/0.2 (contact: ops@example.com)'
food-label-platform
```

可显式改为 `openfoodfacts` 禁用回退，或改为 `curated` 仅运行离线验收目录。Open Food Facts 是社区维护的开放数据，应核对实物标签并遵守其 ODbL 数据库许可要求。

工作流检查点和经授权的长期记忆默认保存在 `~/.local/share/food-label-health-agent/agent-data.sqlite3`，文件权限设为仅当前用户可读写。可用 `FOOD_LABEL_DATA_DIR` 指定其他数据目录。当前能力令牌方案用于本地单用户原型；多用户部署仍需在 API 前增加账户认证、加密密钥管理和数据隔离。

### 可选的模型辅助 Planner

默认的 `deterministic` 模式不调用远程模型。启用 OpenAI Planner 时，确认后的标签事实、用户约束和候选动作摘要会发送给 OpenAI；原始图片不会发送给 Planner，请求设置 `store: false`。模型不能创建工具参数、修改过敏原结果或跳过最终安全门；无凭证、超时、拒答、非法动作或无效结构都会自动回退到确定性策略。

```bash
export FOOD_LABEL_PLANNER_PROVIDER=openai
export FOOD_LABEL_PLANNER_MODEL=gpt-5.6-terra
export FOOD_LABEL_PLANNER_REASONING_EFFORT=low
export OPENAI_API_KEY='由部署环境注入，不要写入仓库'
food-label-platform
```

三种 Planner 消融评测分别记录确定性基线、原始模型提议和策略保护后的模型提议。`planner_benchmark_v2` 包含 16 个场景，分别覆盖安全优先级、标签冲突、证据缺口和多重约束；其中包含正确动作不在第一候选位的非平凡案例。报告同时给出分类准确率、模型相对基线的 lift、非法动作率和 fallback 率。离线模式不会调用远程服务；正式模型评测必须显式启用：

```bash
food-label-planner-eval
FOOD_LABEL_PLANNER_PROVIDER=openai food-label-planner-eval --live
```

### RAG 2.0（默认法规检索链路）

RAG 2.0 使用同一个服务端 `OPENAI_API_KEY`，但拥有独立配置。默认 Profile 为 `hybrid_dense_rerank`；法规查询和已通过本地版本过滤的候选官方条款会发送至 OpenAI，食品原图不会发送给 RAG Provider。部署时必须注入 API Key；Provider 不可用时链路会失败关闭，不会生成无依据结论。

```bash
export FOOD_LABEL_RAG_PROFILE=hybrid_dense_rerank
export FOOD_LABEL_RAG_EMBEDDING_MODEL=text-embedding-3-large
export FOOD_LABEL_RAG_EMBEDDING_DIMENSIONS=1024
export FOOD_LABEL_RAG_RERANKER_MODEL=gpt-5.6-terra
```

2026-08-12 的四组真实消融已通过，完整记录见 [`docs/evaluation/RAG2_EVALUATION_2026-08-12.md`](docs/evaluation/RAG2_EVALUATION_2026-08-12.md)。后续更换模型、维度、语料或重排策略时，应重新运行：

```bash
PYTHONPATH=src .venv/bin/python \
  -m food_label_agent.evaluation.rag_ablation --live
```

不带 `--live` 时只运行 BM25 与 RAG 1.0 基线，不调用远程模型。RAG 2.0 Provider 失败不会生成无依据结论；应急或离线运行可显式设置 `FOOD_LABEL_RAG_PROFILE=hybrid_tfidf` 回退。

### Milestone 6 统一评测与发布门禁

开发过程中运行统一离线评测：

```bash
food-label-eval \
  --profile development \
  --json artifacts/evaluation.json \
  --markdown artifacts/evaluation.md
```

该命令一次检查过敏原规则、法规混合检索、Agent 工具轨迹、替代品独立复核、最终安全门和已知失败案例，并在报告中固定 Git、规则、词典、法规索引、OCR 与 MCP 工具版本。开发模式可以不运行私有 OCR 数据，但会明确标记为警告，不能据此宣称 OCR 已达到发布质量。

正式发布必须提供仓库外的匿名标注实物标签目录：

```bash
food-label-eval \
  --profile release \
  --ocr-images /secure/private-label-benchmark \
  --json artifacts/release-evaluation.json \
  --markdown artifacts/release-evaluation.md
```

发布模式会在工作区未提交、OCR 样本不足、明确过敏原召回低于 100%、数字召回低于 100%、营养素数值错位、低质量图片漏阻断，或任一规则/RAG/Agent/替代品/安全门回归时返回非零退出码。OCR 标注文件与图片同名并追加 `.json`，可用 `expect_blocked: true` 标记应被质量门拦截的图片。已修复的线上或验收失败必须加入 `src/food_label_agent/evaluation/data/regression_cases.json`，之后自动成为永久阻断回归。

### 服务器端启用 PP-OCRv6

普通用户不需要配置 OCR。部署者安装可选 OCR 依赖与 PaddlePaddle 推理引擎后，只在服务器环境中设置：

```bash
export FOOD_LABEL_OCR_PROVIDER=paddle
export FOOD_LABEL_OCR_VERSION=PP-OCRv6
export FOOD_LABEL_OCR_DEVICE=cpu
export FOOD_LABEL_OCR_CACHE_DIR=.paddlex
export FOOD_LABEL_OCR_FAST_PATH=true
export PADDLE_PDX_MODEL_SOURCE=bos  # 中国大陆部署可优先使用
# 可选：启用营养表行列恢复；会额外加载 PP-StructureV3 模型
# export FOOD_LABEL_OCR_TABLE_PARSER=ppstructure
# export FOOD_LABEL_OCR_TABLE_OCR_VERSION=PP-OCRv5
food-label-platform
```

快速路径默认使用 PP-OCRv6 medium 检测器与 small 识别器，并关闭首轮文字行方向判断。只有配料、营养口径以及带正确单位的核心营养素同时完整时才接受结果；否则自动回退到完整 medium 管线，再按需调用 PP-StructureV3。相同图片在同一服务进程内会命中短期哈希缓存。

真实 `.env`、私有标签样本、OCR 输出和模型缓存均被 Git 排除。完整安装与生产说明见下方配置教程。

### 导入官方法规 PDF

先在法规注册表中登记标准版本及官方来源，再将下载的标准 PDF 转换为带页码和哈希的条款索引：

```bash
food-label-regulations-ingest \
  --document-id GB7718-2011 \
  --pdf /path/to/GB7718-2011.pdf \
  --output src/food_label_agent/regulations/data/GB7718-2011.json
```

当前内置索引、来源和覆盖边界见 `docs/regulations/OFFICIAL_SOURCE_MANIFEST.md`。检索结果只使用查询日期仍适用的标准版本；没有适用官方证据时返回 `unknown`。

### 服务器端启用腾讯云 OCR

普通用户不需要配置云端密钥。部署者为服务账号配置腾讯云官方凭证链后执行：

```bash
python3 -m pip install -e '.[cloud-ocr,dev]'
export FOOD_LABEL_OCR_PROVIDER=tencent
export FOOD_LABEL_TENCENT_REGION=ap-guangzhou
export FOOD_LABEL_TENCENT_TABLE_ENABLED=true
food-label-platform
```

主管线使用 `GeneralAccurateOCR` 返回文字、置信度与原图坐标。检测到营养内容后才调用 `RecognizeTableAccurateOCR` 恢复表格单元格，从而控制延迟和调用次数。图片会发送至腾讯云完成识别；当前应用不持久化原图，界面会明确披露处理方式。配置和安全细节见腾讯云 OCR 教程。

## 文档

- [中英双语产品说明书](./Food_Label_Health_Agent_Product_Spec_Bilingual.md)
- [ADR-001：Agent 状态与安全路由](./docs/architecture/ADR-001-agent-state-and-safety-routing.md)
- [ADR-002：受约束 ReAct 与工具轨迹](./docs/architecture/ADR-002-constrained-react-tool-loop.md)
- [ADR-003：版本化法规混合检索](./docs/architecture/ADR-003-versioned-hybrid-regulation-retrieval.md)
- [ADR-004：节点上下文、检查点与授权记忆](./docs/architecture/ADR-004-context-checkpoints-and-consented-memory.md)
- [ADR-005：证据优先的替代品检索与二次验证](./docs/architecture/ADR-005-evidence-first-alternative-revalidation.md)
- [ADR-006：策略保护的模型辅助 Planner](./docs/architecture/ADR-006-policy-guarded-model-planner.md)
- [ADR-007：中文 Dense Retrieval 与独立 Reranker](./docs/architecture/ADR-007-rag2-dense-independent-reranker.md)
- [PP-OCRv6 配置教程](./docs/ocr/PP-OCRv6_CONFIGURATION_GUIDE.md)
- [腾讯云 OCR 配置教程](./docs/ocr/TENCENT_CLOUD_CONFIGURATION_GUIDE.md)
- [腾讯云 OCR 匿名评测记录](./docs/ocr/TENCENT_OCR_EVALUATION_2026-08-05.md)
- [模型辅助 Planner 真实消融验收记录](./docs/evaluation/PLANNER_EVALUATION_2026-08-12.md)
- [法规官方来源与索引清单](./docs/regulations/OFFICIAL_SOURCE_MANIFEST.md)
- [产品上下文](./PRODUCT.md)
- [界面设计系统](./DESIGN.md)
