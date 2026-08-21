# Food Label Health Agent

一个面向中国食品标签的证据优先多模态 Agent。用户拍摄或上传包装标签，系统先完成 OCR 与人工确认，再结合个人明确选择的过敏原和健康关注，解释配料、营养成分、包装声称与可追溯的法规依据；当证据不足时返回 `unknown` 或要求确认，而不是补全一个看似确定的答案。

项目同时提供消费者网页、Starlette API、LangGraph 工作流、模块化 MCP Server、法规 RAG、替代品复核和统一发布评测。当前版本为本地单用户原型，不构成医疗诊断、治疗建议、商品合规认证或绝对安全保证。

## 当前已经实现

| 能力 | 当前行为 |
| --- | --- |
| 标签识别 | 腾讯云高精度 OCR 为默认 Provider，可切换 PP-OCRv6；保留置信度、坐标和质量问题 |
| 人工确认 | 低置信度关键字段必须由用户核对，确认前不进入安全结论 |
| 配料理解 | 树状规范化复合配料，保留原始文本与证据位置，识别中国八类常见致敏物质 |
| 个人约束 | 将用户主动选择的过敏原、健康关注和营养上限转成确定性检查条件 |
| 营养解释 | 规范化营养素、数值、单位和计量口径；不同口径不擅自换算 |
| 包装声称 | 区分“无糖、低糖、无蔗糖、不添加糖、不添加蔗糖”，并与配料和营养表交叉核对 |
| 添加剂说明 | 使用版本化词典解释常见功能类别，并把词典事实与 GB 2760 法规证据分开 |
| 法规检索 | 按中国法域、适用日期和标准版本过滤；BM25 + Dense Embedding 经 RRF 融合后独立重排 |
| 替代品 | 先确认同类用途，再逐一重跑相同硬约束；证据不完整或风险未知的候选不会进入推荐 |
| 可恢复工作流 | `AgentState`、SQLite 检查点、能力令牌、节点轨迹和 MCP 工具轨迹 |
| 消费者网页 | 首次档案设置、回访健康主页、拍照识别、结果证据、滑动概览、历史摘要与历史详情 |
| 发布门禁 | 统一评测过敏原、OCR、RAG、Agent、替代品与最终安全门，并固定版本信息 |

## Agent 的开发思路

### 1. 先建立不可绕过的安全骨架，再引入模型

LLM 不是事实来源，也不是最终裁决者。输入校验、标签确认、字段规范化、过敏原与营养规则、证据版本检查和 `final_safety_gate` 都是固定节点。模型只能在策略允许的动作空间内辅助排序或解释，不能删除风险、修改用户确认的事实或跳过安全节点。

### 2. 把“标签事实、规则判断、语言解释”分层

- **标签事实**：OCR 原文、用户确认文本、坐标、营养表行列和包装声称。
- **规则判断**：确定性过敏原匹配、营养上限比较、证据完整度和一致性检查。
- **语言解释**：在前两层结果和适用法规证据之上生成面向用户的说明。

这种分层让系统可以单独测试每一层，也能在模型或网络不可用时保留安全的降级路径。

### 3. 所有肯定结论都必须有证据边界

法规条款必须先通过法域、日期、版本和来源过滤。配料解释绑定具体 evidence ID；添加剂在缺少食品类别、实际用量或标准明细表时只解释常见功能，不判断合规。`compatible` 只表示当前已确认信息未触发既定约束，不等于绝对安全。

### 4. 用受约束 ReAct 处理“下一步该查什么”

核心编排器只允许选择法规检索、配料解释、声称解释和一致性验证四类批准动作，并受步骤数和工具调用数预算限制。默认 Planner 完全确定性；可选模型 Planner 只能从策略预先生成的合法动作 ID 中选择，工具参数仍由系统生成并校验。API 和轨迹只记录动作、原因码、调用元数据和压缩观察，不保存或暴露模型思维链。

### 5. 失败关闭，而不是失败开放

OCR 质量不足时要求重拍或确认；法规 Provider、工具或模型失败时最多进行受控重试，之后返回 `unknown`。最终安全门会阻断失效引用、风险降级、缺失必经节点和未独立复核的替代品。

### 6. 替代品不是搜索排序，而是重新验算

候选商品先经过来源、版本、内容哈希和标签完整度检查，再以原用户约束重新运行过敏原与营养规则。只有同类用途且结果为 `compatible` 的候选能够展示；库存、在售状态和绝对安全不在当前系统的保证范围内。

### 7. 隐私与可观测性同时设计

原始图片只用于 OCR，应用不持久化图片。短期工作流通过随机能力令牌访问，SQLite 检查点会移除原始图片。长期约束记忆只有在用户明确授权后保存，并支持查看、删除和撤销。`workflow_trace` 与 `tool_trace` 用于验证系统走过了哪些节点和工具，但不记录完整对话或模型内部推理。

## 端到端工作流

```text
上传标签
  → validate_input
  → extract_label (OCR + 质量证据)
  → confirm_label（必要时暂停等待人工确认）
  → normalize_label
  → evaluate_safety（确定性规则）
  → react_orchestrator
      ↳ retrieve_regulations
      ↳ interpret_label
      ↳ interpret_claims
      ↳ verify_consistency
  → final_safety_gate
  → 结果、依据与可选替代品
```

替代品使用独立安全路径：

```text
search_alternatives → revalidate_alternatives → final_safety_gate
```

## 系统分层

| 层 | 主要目录 | 职责 |
| --- | --- | --- |
| Web / API | `src/food_label_agent/web` | 消费者 UI、上传、确认、结果、历史记录和 HTTP API |
| Agent 编排 | `src/food_label_agent/graph` | `AgentState`、LangGraph 拓扑、路由、受约束 ReAct、Planner 与运行时 |
| MCP 边界 | `src/food_label_agent/mcp` | 版本化工具契约和进程内/外一致的业务工具入口 |
| OCR | `src/food_label_agent/ocr` | Provider 配置、图像质量、字段解析、营养表坐标与证据质量 |
| 配料与规则 | `src/food_label_agent/ingredients` | 配料规范化、过敏原检查、添加剂和证据化解释 |
| 营养与声称 | `src/food_label_agent/nutrition`、`claims` | 营养事实规范化、阈值规则、包装声称解释和一致性检查 |
| 法规 RAG | `src/food_label_agent/regulations` | 官方文档注册、PDF 分片、BM25、Dense Retrieval、重排和版本过滤 |
| 替代品 | `src/food_label_agent/alternatives` | 商品目录、类别识别、来源审核、搜索、比较和重新验证 |
| 持久化 | `src/food_label_agent/persistence` | SQLite 检查点、长期授权记忆和能力令牌 |
| 可观测性 | `src/food_label_agent/observability` | 工作流和工具轨迹的结构化记录 |
| 评测 | `src/food_label_agent/evaluation`、`evaluation` | 离线/真实评测、回归案例、消融和发布门禁 |

## Web 体验与本地数据

- 第一次打开网页时设置个人饮食关注；有使用记录后直接进入健康主页。
- 标签分析前会显示本次使用的档案，用户可以临时调整或返回修改。
- 结果页区分主要结论、其他约束、添加剂、包装声称、法规依据和替代品。
- 浏览器历史仅保存结构化摘要，不保存上传图片；历史条目可以进入详情查看当时实际保留的字段。
- 健康记录和个人档案保存在本设备，并提供明确授权、清除与撤销入口。

## 核心设计原则

- 标签事实、规则判断和模型解释分层。
- 高风险结论必须可追溯。
- OCR 关键字段不可靠时先请求确认。
- 过敏原安全门不能被 LLM 跳过。
- 法规按法域、版本和适用日期检索。
- 替代品先经过硬约束过滤，再进行偏好排序。
- 证据不足时明确返回未知，不用流畅文案掩盖缺口。

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

然后访问 `http://127.0.0.1:8000`。项目 CLI 默认使用腾讯云 OCR；这个默认值只包含 Provider 选择，不包含任何密钥。凭证继续由腾讯云 SDK 的环境变量或 `~/.tencentcloud/credentials` 提供。上传图片会发送到腾讯云 OCR，本平台不持久化原图。如需本地识别，可显式设置 `FOOD_LABEL_OCR_PROVIDER=paddle`。

正式 CLI 当前默认设置 `FOOD_LABEL_PRODUCT_CATALOG=official_cn`，只使用经过人工审核、可从中国大陆访问的品牌官网或官方旗舰店标签证据。需要实验 Open Food Facts 实时目录时，可显式切换为 `hybrid`；该模式优先访问 Open Food Facts，不可用时回退到内置验收目录，并应配置可识别应用与联系方式的 User-Agent：

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
