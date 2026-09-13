# Food Label Health Agent

一个面向中国大陆预包装食品的证据优先 Agent。用户拍摄或上传食品包装后，系统先执行 OCR，再让用户逐项确认标签文字；只有确认过的配料、过敏原和营养数据才能进入确定性安全规则、法规检索、自然语言解释与受控对话。

项目的目标不是给食品打一个不透明的“健康分”，而是保留一条可以检查的链路：

```text
包装图片 → OCR 草稿 → 用户确认 → 结构化标签事实
  → 确定性风险规则 → 适用法规证据 → 受控 Agent 解释
```

> 当前状态：`v0.3` 封闭测试候选版。核心标签检查与自由对话已具备受监督封测基础；替代品正式证据、独立 OCR 发布集、生产部署及真人试用结果仍是发布阻断项。项目不构成医疗诊断、治疗建议、商品合规认证或绝对安全保证。

## 当前进度

截至 2026-09-13，当前候选版本的可复核结果如下：

| 项目 | 当前结果 | 判断 |
| --- | ---: | --- |
| 自动化测试 | 606/606 | 通过 |
| 代码覆盖率 | 82.68%，门槛 70% | 通过 |
| 离线多轮对话评测 | 112/112 | 通过 |
| 严重风险降级 | 0 | 通过 |
| 未确认事实泄漏 | 0 | 通过 |
| 未授权工具调用 | 0 | 通过 |
| 提示词注入突破 | 0 | 通过 |
| 工具失败后编造 | 0 | 通过 |
| 高危症状召回 | 100% | 通过 |
| 替代意图独立留出集 | 140 条、14 类、每类 10 条 | 已建立 |
| 替代意图 Top-1 / Macro Recall | 95% / 95% | 通过 |
| 替代品精确 SKU + 规格 | 0/93 | 阻断 |
| 替代品双人实物背标 | 0/93 | 阻断 |
| 当前可购买证据 | 0/93 | 阻断 |
| 独立 OCR 发布集 | 0；现有 9 张为开发集 | 阻断 |
| 真人封闭试用 | 0 人、0 个任务 | 尚未开始 |

最近一次 Terra 全集评测的硬安全指标全部通过，证据一致率为 98.48%；完整响应 P95 为 7312.64 ms，仍略高于封测试用目标 7000 ms，因此需要在真人试用中继续观测。

完整依据见：

- [M9 封闭试用就绪评测](docs/evaluation/M9_CLOSED_PILOT_READINESS_2026-09-12.md)
- [封闭测试前完整评测](docs/evaluation/PREPILOT_FULL_EVALUATION_2026-09-12.md)
- [替代品目录扩充与独立留出评测](docs/evaluation/ALTERNATIVE_CATALOG_EXPANSION_2026-09-12.md)
- [隐私与合规发布清单](docs/PRIVACY_COMPLIANCE_READINESS.md)

## 已实现能力

| 能力 | 当前行为 |
| --- | --- |
| OCR | 默认接入腾讯云高精度 OCR，可切换 PP-OCRv6；保留置信度、坐标和图片质量问题 |
| 人工校对 | 低置信度字段必须确认；文字草稿和步骤可在当前标签页恢复，原图不会被草稿保存 |
| 配料结构 | 解析复合配料与括号结构，保留原始文字和问题位置，文字类错误可在校对区定位 |
| 过敏原 | 使用版本化确定性规则检查中国八类常见致敏物质及交叉接触提示 |
| 营养数据 | 规范化营养素、数值、单位和每 100 克、每 100 毫升或每份口径，不擅自跨口径比较 |
| 包装声称 | 区分无糖、低糖、无蔗糖、不添加糖等声称，并与配料和营养表交叉核对 |
| 法规 RAG | 先按法域、日期、标准版本和官方来源过滤，再执行混合召回与独立重排 |
| 受控 Agent | LangGraph + 白名单 MCP 工具；模型只能在策略允许的动作中选择，不能生成任意工具参数 |
| 自由对话 | 支持指代追问、矛盾处理、标签纠错、两个已确认商品的同口径对比和安全降级 |
| 替代品 | 用户先确认替代用途，再按相同硬约束重新验证；证据不足的商品不会包装成安全推荐 |
| 持久化 | SQLite 工作流检查点、短期对话、显式授权记忆、在线备份和完整性检查 |
| 可观测性 | 记录模型、延迟、Token、估算成本、工具状态和安全边界，不记录对话或标签原文 |
| 发布门禁 | 统一检查规则、RAG、Agent、OCR、替代品、失败语料和最终安全门 |

## 模型与 Provider

| 子任务 | 当前选择 | 边界与回退 |
| --- | --- | --- |
| 自由对话 | OpenAI Responses API + `gpt-5.6-terra`，`low` | 原图不发送给对话模型；请求使用 `store: false`；普通对话需要明确远程处理同意 |
| Agent Planner | 默认确定性 Planner；可选 `gpt-5.6-terra` | 模型只返回合法 `action_id`；异常、超时或非法动作自动回退确定性策略 |
| 法规向量召回 | `text-embedding-3-large`，1024 维 | 远程不可用时可显式切换 `hybrid_tfidf`；不能绕过版本与来源过滤 |
| 法规重排 | `gpt-5.6-terra` | 只重排已通过本地过滤的候选，不能补写法规条款 |
| 云端 OCR | 腾讯云 `GeneralAccurateOCR`；营养表按需使用 `RecognizeTableAccurateOCR` | OCR 只生成草稿，关键字段仍须质量门和人工确认 |
| 本地 OCR | PP-OCRv6 + 可选 PP-StructureV3 | 复杂或字段不完整时升级管线，仍无法确认时失败关闭 |
| 紧急症状 | 本地固定规则 | 不依赖模型响应或远程工具 |
| 过敏与健康风险 | 本地确定性规则 | LLM 无权修改风险等级或跳过最终安全门 |

模型名称均由环境变量配置，但封测期间应冻结模型、推理强度、语料和规则版本。任何替换都必须重新运行相同评测集。

## 安全边界

- 只有用户明确确认的标签字段可以成为可信事实。
- OCR 原文、确认事实、规则结果和模型解释分层存放。
- 严重过敏与紧急症状优先于营养解释和替代品。
- 模型不能修改 `avoid`、`needs_confirmation` 或 `unknown` 等确定性边界。
- 法规回答必须包含中国大陆法域、适用日期、标准版本和检索证据。
- 工具失败、证据不足或用户描述矛盾时，回答“不确定”或要求重新确认。
- 包装中的提示词和指令始终视为食品文字，而不是系统指令。
- 不开放通用网页搜索、代码执行、任意文件访问、购物或自动购买。
- 不提供诊断、治疗方案、个体化营养处方或“绝对安全”保证。
- 未单独取得同意时，不建立长期个人记忆。

## 快速开始

### 1. 安装

需要 Python 3.11–3.14。开发环境建议使用 Python 3.13。

```bash
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -e '.[dev,cloud-ocr]'
```

如果只使用本地 OCR，可安装 `.[dev,ocr]`；Paddle 相关依赖较大，请按 [PP-OCRv6 配置教程](docs/ocr/PP-OCRv6_CONFIGURATION_GUIDE.md)准备运行环境。

### 2. 保存本地配置

不要把真实 API Key 写入仓库。项目启动脚本会自动读取：

```text
~/.config/food-label-agent/.env
```

首次创建：

```bash
mkdir -p "$HOME/.config/food-label-agent"
chmod 700 "$HOME/.config/food-label-agent"
touch "$HOME/.config/food-label-agent/.env"
chmod 600 "$HOME/.config/food-label-agent/.env"
```

推荐的对话与 RAG 配置：

```dotenv
OPENAI_API_KEY='由部署环境注入，不要提交到 Git'

FOOD_LABEL_CHAT_PROVIDER='openai'
FOOD_LABEL_CHAT_MODEL='gpt-5.6-terra'
FOOD_LABEL_CHAT_REASONING_EFFORT='low'
FOOD_LABEL_CHAT_RETENTION_HOURS='24'
FOOD_LABEL_CHAT_MAX_COST_USD='0.25'

FOOD_LABEL_RAG_PROFILE='hybrid_dense_rerank'
FOOD_LABEL_RAG_EMBEDDING_MODEL='text-embedding-3-large'
FOOD_LABEL_RAG_EMBEDDING_DIMENSIONS='1024'
FOOD_LABEL_RAG_RERANKER_MODEL='gpt-5.6-terra'

FOOD_LABEL_OCR_PROVIDER='tencent'
FOOD_LABEL_TENCENT_REGION='ap-guangzhou'
```

腾讯云凭证继续使用腾讯云 SDK 官方凭证链或 `~/.tencentcloud/credentials`，不要放进上述文件或仓库。

### 3. 启动 8000

```bash
./scripts/run_local_platform.sh
```

然后访问 [http://127.0.0.1:8000/](http://127.0.0.1:8000/)，并检查：

```bash
curl http://127.0.0.1:8000/api/health
curl http://127.0.0.1:8000/api/ready
```

本地开发环境允许 `/api/ready` 报告尚未配置的生产项；真正邀请外部测试者前，生产环境的 `/api/ready` 必须返回 HTTP 200。

## 运行评测

### 自动化与静态检查

```bash
.venv/bin/python -m ruff check src tests
.venv/bin/python -m mypy
.venv/bin/python -m pytest -q --cov=food_label_agent --cov-branch --cov-fail-under=70
```

`mypy` 当前 CI 门禁覆盖四个安全关键模块；全项目严格类型检查仍有历史技术债，不能把局部通过表述为全仓零类型问题。

### 对话与封测门禁

```bash
food-label-conversation-eval \
  --json artifacts/conversation-evaluation.json \
  --markdown artifacts/conversation-evaluation.md

food-label-conversation-eval --live \
  --json artifacts/conversation-evaluation-live.json \
  --markdown artifacts/conversation-evaluation-live.md

food-label-pilot-eval \
  --conversation-report artifacts/conversation-evaluation.json \
  --human-results evaluation/pilot/m9_human_results.template.json
```

离线评测验证程序安全契约；`--live` 才会调用当前配置的 OpenAI 模型。真人封测结果不得由合成用户、模型评分或历史测试代替。

### 统一评测

```bash
food-label-eval \
  --profile development \
  --json artifacts/evaluation.json \
  --markdown artifacts/evaluation.md
```

正式发布还必须提供仓库外的独立 OCR 标注集：

```bash
food-label-eval \
  --profile release \
  --ocr-images /secure/private-label-benchmark \
  --json artifacts/release-evaluation.json \
  --markdown artifacts/release-evaluation.md
```

## 封闭测试边界

当前版本适合小规模、受监督地测试：

- OCR、人工校对和刷新恢复；
- 确定性个人约束检查；
- 配料、营养、包装声称和法规解释；
- 多轮追问、纠错、重试与数据删除；
- 两个已经确认标签的同口径比较。

替代品功能目前只适合诊断性测试：

- 用户必须先确认替代用途并主动点击查找；
- “官方商店链接”不等于已经证明当前在售；
- 没有同口径营养字段时不宣称更健康；
- 没有双人实物背标时只显示“证据有限”或“待核验”；
- 严重过敏场景只允许返回“当前没有可信候选”。

真正解除替代品发布阻断，需要每个发布 SKU 绑定规格、内容哈希、两名不同审核者的实物背标复核，以及处于有效期内的中国大陆在售证据。操作流程见 [替代品目录扩充报告](docs/evaluation/ALTERNATIVE_CATALOG_EXPANSION_2026-09-12.md)。

## 真人封测通过条件

只有满足以下全部条件，`pilot_outcome_validated` 才能为 `true`：

- 至少 10 名真实参与者；
- 至少 100 个完成任务；
- 任务完成率不低于 85%；
- 回答有帮助率不低于 80%；
- 严重安全事故为 0；
- 首 Token P95 不超过 1500 ms；
- 完整回答 P95 不超过 7000 ms。

真人结果模板位于 [`evaluation/pilot/m9_human_results.template.json`](evaluation/pilot/m9_human_results.template.json)，12 项任务定义位于 [`m9_pilot_tasks.json`](src/food_label_agent/evaluation/data/m9_pilot_tasks.json)。

## 数据与隐私

- 上传图片会发送给配置的 OCR Provider，但应用不持久化原图。
- OCR 校对文字草稿只保留在当前标签页，最长 2 小时；刷新后需重新上传同一原图才能继续确认。
- 自由对话原文保存在独立短期表中，默认 24 小时后清理，不进入长期健康记忆。
- OpenAI 对话请求使用 `store: false`。
- 回答反馈只保存匿名哈希、评价、预定义原因和是否重试，不复制对话或标签原文。
- 长期偏好必须显式授权，并支持查看、修改、导出、删除和撤销授权。
- 本地启动指标只记录模型、延迟、Token、成本、工具状态和错误分类，不记录原始对话。

工程门禁不能替代正式隐私政策、服务条款、处理方协议或法律审查。完整清单见 [PRIVACY_COMPLIANCE_READINESS.md](docs/PRIVACY_COMPLIANCE_READINESS.md)。

## 生产部署

第一阶段采用 Starlette 单服务、SQLite 持久卷和 HTTPS 反向代理。部署前需要配置：

- `FOOD_LABEL_SITE_ACCESS_TOKEN`
- `FOOD_LABEL_DISCOVERY_ADMIN_TOKEN`
- `FOOD_LABEL_DEV_TOKEN`
- `FOOD_LABEL_ALLOWED_HOSTS`
- `FOOD_LABEL_PUBLIC_BASE_URL`
- 隐私政策、服务条款、隐私联系人和法律审核记录
- 持久化 `FOOD_LABEL_DATA_DIR`

生产模板见 [`.env.production.example`](.env.production.example)，完整步骤见 [国内部署说明](docs/DEPLOYMENT_CN.md)。共享站点口令只适合受控邀请测试；公开多用户版本仍需正式账户、会话撤销、租户隔离、数据库静态加密和集中密钥管理。

SQLite 应使用在线备份，而不是直接复制正在写入的主库：

```bash
food-label-data backup \
  --source /app/data/agent-data.sqlite3 \
  --output /app/backups/agent-data.sqlite3

food-label-data verify --path /app/backups/agent-data.sqlite3
```

## 项目结构

```text
src/food_label_agent/
├── web/              # 消费者网页与 HTTP API
├── graph/            # AgentState、路由、ReAct、Planner 与工作流
├── mcp/              # 白名单业务工具及 MCP 契约
├── ocr/              # OCR Provider、图片质量与字段解析
├── ingredients/      # 配料规范化、过敏原和添加剂解释
├── nutrition/        # 营养规范化与确定性规则
├── claims/           # 包装声称与一致性检查
├── regulations/      # 官方法规索引、检索和版本过滤
├── alternatives/     # 替代类别、商品证据与独立复核
├── conversation/     # 受控自由对话与短期会话
├── persistence/      # SQLite、授权记忆和备份
├── observability/    # 内容最小化运行指标
└── evaluation/       # 离线、真实模型与发布评测
```

## 设计与架构文档

- [产品上下文](PRODUCT.md)
- [界面设计系统](DESIGN.md)
- [最终 Agent North Star](docs/product/FINAL_AGENT_NORTH_STAR.md)
- [ADR-001：Agent 状态与安全路由](docs/architecture/ADR-001-agent-state-and-safety-routing.md)
- [ADR-002：受约束 ReAct 与工具轨迹](docs/architecture/ADR-002-constrained-react-tool-loop.md)
- [ADR-003：版本化法规混合检索](docs/architecture/ADR-003-versioned-hybrid-regulation-retrieval.md)
- [ADR-004：检查点与授权记忆](docs/architecture/ADR-004-context-checkpoints-and-consented-memory.md)
- [ADR-005：证据优先替代品复核](docs/architecture/ADR-005-evidence-first-alternative-revalidation.md)
- [ADR-006：策略保护的模型 Planner](docs/architecture/ADR-006-policy-guarded-model-planner.md)
- [ADR-007：Dense Retrieval 与独立 Reranker](docs/architecture/ADR-007-rag2-dense-independent-reranker.md)
- [腾讯云 OCR 配置](docs/ocr/TENCENT_CLOUD_CONFIGURATION_GUIDE.md)
- [PP-OCRv6 配置](docs/ocr/PP-OCRv6_CONFIGURATION_GUIDE.md)
- [国内部署说明](docs/DEPLOYMENT_CN.md)

## License

Proprietary。除非项目所有者另行授权，不授予复制、分发或商业使用许可。
