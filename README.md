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

## Agent 的模型选择与迭代过程

这套 Agent 不是一开始就把图片、法规和用户问题全部交给一个大模型。开发过程先为每个子任务建立可复现基线，再根据真实失败案例决定是否引入模型；新方案只有通过对应质量门、且不会越过安全边界后，才进入默认或可选链路。

### 当前模型与 Provider 选择

| 子任务 | 当前选择 | 为什么这样选 | 回退或边界 |
| --- | --- | --- | --- |
| 中国食品包装 OCR | 默认腾讯云 `GeneralAccurateOCR`，营养表按需调用 `RecognizeTableAccurateOCR` | 17 张真实中国食品标签测试中 API 成功率为 17/17，平均云端耗时 1.111 秒；坐标信息可以支持多栏配料和营养表恢复 | 所有关键字段仍需质量门与人工确认；本地可切换 PP-OCRv6 |
| 本地 OCR | PP-OCRv6 medium 检测器 + small 识别器，必要时回退完整 medium 管线和 PP-StructureV3 | 快速路径减少普通标签延迟，复杂、畸变或营养表不完整时再使用更重的模型，避免每张图片都承担完整表格模型成本 | 配料锚点、单位或五项核心营养素不完整时失败关闭，不让 OCR 直接产生健康结论 |
| Agent Planner | 默认确定性 Planner；可选 OpenAI `gpt-5.6-terra` | 确定性基线易测试且离线可用；模型只用于多个合法动作之间的排序。16 个案例中，受保护模型由 68.75% 提升到 93.75%，主要改善标签声称冲突处理 | 模型只能返回合法 `action_id`，不能生成工具参数、改写风险或跳过安全门；异常时回退确定性策略 |
| 法规向量召回 | OpenAI `text-embedding-3-large`，1024 维 | 相比仅 BM25/TF-IDF，更能处理中文口语改写；在当前 12 个案例消融中将 Recall@5 从 90.91% 提升到 100% | 法域、日期、标准版本和来源先在本地过滤；离线或故障时显式切回 `hybrid_tfidf` |
| 法规独立重排 | OpenAI `gpt-5.6-terra` | Dense 召回解决“找得到”，独立重排进一步解决“第一条是否正确”；当前小样本中 MRR 从 93.94% 提升到 100% | 只能重排已通过本地过滤的官方候选，不能补写条款或恢复已排除证据 |

`gpt-5.6-terra` 和 `text-embedding-3-large` 是当前经过项目内基准验收的配置，不代表已经在所有候选模型中证明全局最优。目前没有完成跨厂商、跨模型的质量—延迟—成本横向评测；因此模型名均保留为环境变量配置，后续替换必须重新运行相同消融和发布门禁。

详细验收数据分别记录在[腾讯云 OCR 匿名评测](docs/ocr/TENCENT_OCR_EVALUATION_2026-08-05.md)、[模型 Planner 消融评测](docs/evaluation/PLANNER_EVALUATION_2026-08-12.md)和 [RAG 2.0 四组消融评测](docs/evaluation/RAG2_EVALUATION_2026-08-12.md)中。

### 第 1 步：先不用 LLM，建立可审计的 Agent 骨架

最初版本采用显式 `AgentState`、纯函数路由和固定安全节点，而不是让 LLM 自由规划。原因是食品标签包含图片质量、过敏原、法规版本和用户约束；如果第一版直接依赖自由生成，很难判断错误来自 OCR、检索、规则还是模型。这个阶段先固定了 `validate_input`、人工确认、确定性风险判断和 `final_safety_gate`，为之后的每次模型升级留下可比较基线。

### 第 2 步：从本地 PP-OCRv6 快速实现，迭代为证据化级联 OCR

早期选择 PP-OCRv6，是因为它可以本地运行，便于保留图片隐私，也能获得文字框坐标。真实包装测试很快暴露出三个问题：多栏文本返回顺序不等于阅读顺序、营养数值会与错误单位配对、褶皱和透视会让快速模型输出“看似完整”的错误结果。

因此 OCR 不再是一次模型调用，而被改成级联流程：先检查图片质量，再运行快速检测和识别；只有配料锚点、营养口径、单位和核心营养素完整时才接受，否则进入完整模型或 PP-StructureV3。之后接入腾讯云高精度 OCR；它能够返回文字、置信度和坐标，在 17 张真实中国标签的匿名评测中完成了 17/17 次 API 调用，且没有放行不完整营养表，因此被设为 Web CLI 默认 Provider。这个决定表示它达到当前“识别后人工确认”的工程门槛，不表示已经通过与 PP-OCRv6 的大样本精度横评；本地方案仍然保留，原图不持久化，任何识别结果也不能绕过用户确认。

### 第 3 步：先用确定性规则解决高风险判断

过敏原、营养阈值、包装声称冲突和证据完整度最先实现为版本化规则，而不是提示词。这样做是因为这些任务需要稳定复现、明确拒答和逐条测试。LLM 不负责判断“是否含乳”或把 `avoid` 改成 `compatible`；它之后只参与合法动作排序和证据组织。这个阶段也把 OCR 原文、用户确认事实、规则结果和自然语言解释拆开，避免模型把识别猜测写回事实层。

### 第 4 步：法规检索从 BM25 演进到混合检索

第一版法规检索使用 BM25，优点是离线、快速、结果可解释，但对标准编号和原词匹配依赖较强。第二版加入领域概念扩展和 TF-IDF 余弦召回，再用固定权重融合主题、标准号和权威等级；这提供了一个不依赖远程模型的 RAG 1.0 基线，也暴露出中文口语改写召回不足、所谓“重排”其实只是公式加权的问题。

RAG 2.0 因此增加 `text-embedding-3-large` 稠密召回，并用独立的 `gpt-5.6-terra` 重排器处理候选顺序。四组 Profile 的消融结果显示，最终 `hybrid_dense_rerank` 在当前小样本上同时改善 Recall@5、MRR、nDCG@5 和 Top-1，才被切换为生产默认；`hybrid_tfidf` 继续作为离线测试和应急路径。远程模型调用前始终先完成法域、日期、版本和官方来源过滤，所以语义相似度不会改变法规适用性。

### 第 5 步：从固定工具顺序到确定性 ReAct

固定调用所有工具虽然简单，但会产生无关法规检索，也无法针对不同标签决定先解释配料、检查声称还是验证一致性。项目先实现确定性 ReAct：系统根据已确认事实生成合法动作，逐步调用四类白名单 MCP 工具，并限制最大步骤数和调用数。这样先验证“动态选择工具”本身是否可靠，而不是同时引入模型变量。

### 第 6 步：只把动作排序交给模型 Planner

确定性 Planner 在复杂冲突中常机械选择第一候选，因此加入 `gpt-5.6-terra` 作为可选动作提议器。模型收到的是策略生成的候选 `action_id` 和用途摘要，不接收原始图片，也不能创建工具名或参数。项目比较了确定性基线、原始模型提议和 Policy 保护后的模型提议：16 个非平凡案例中准确率从 68.75% 提升至 93.75%，非法动作率、策略违规率和 fallback 率均为 0。

这次结果支持“模型适合处理合法动作之间的语义排序”，但没有证明食品安全结论应交给模型。当前模型 Planner 仍不是默认必需依赖；无凭证、超时、拒答、结构错误或非法动作都会回退到确定性策略。

### 第 7 步：把模型改进变成可回归的工程过程

后续改进不再以“换了更强模型”作为完成标准，而是要求保留版本、数据集、动作轨迹和失败案例。统一评测分别覆盖 OCR 字段完整度与数值对齐、过敏原召回、RAG Recall/MRR/nDCG、Planner 动作准确率与非法动作率、替代品独立复核以及最终安全门。已修复问题进入回归集；Provider 失败必须表现为结构化 `unknown`、受控回退或阻断，而不是用流畅文本掩盖错误。

当前仍需补足的证据包括：更大的匿名真实 OCR 数据集、Planner 与 RAG 的跨模型成本和延迟对比、真实限流/超时恢复矩阵，以及比现有 16/12 个案例更大的困难负例集。这些是下一轮模型选择的依据，而不是只依据模型发布名称升级。

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

正式 CLI 当前默认设置 `FOOD_LABEL_PRODUCT_CATALOG=official_cn_expanded`：优先使用经过人工审核、可从中国大陆访问的品牌官网或官方旗舰店标签证据；品类不足时，再补充 Open Food Facts 中带中国地区标记、已完成配料审核且具有版本日期的商品。补充商品仍会逐件经过同一套字段、时效、哈希和个人约束复核。建议配置可识别应用与联系方式的 User-Agent：

```bash
export FOOD_LABEL_PRODUCT_CATALOG=official_cn_expanded
export FOOD_LABEL_OPENFOODFACTS_USER_AGENT='LabelLensHealth/0.2 (contact: ops@example.com)'
food-label-platform
```

可显式改为 `official_cn` 仅使用人工审核的中国官方目录，改为 `openfoodfacts` 仅使用实时社区目录，或改为 `curated` 仅运行离线验收目录。Open Food Facts 是社区维护的开放数据；界面会标明来源，购买和食用前仍应核对当前实物包装，并遵守其 ODbL 数据库许可要求。

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
