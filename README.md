# Food Label Health Agent

面向中国大陆预包装食品的标签解释与替代品筛选系统。用户上传包装、确认识别文字并设置个人约束后，系统结合确定性规则、法规 RAG 和商品证据 RAG 给出有来源的解释与筛选结果。

**当前阶段：v0.3 封闭测试候选版。** 标签检查、受控对话和商品证据闭环已实现；商品标签完整性、独立真实数据评测与生产部署仍需完善。检索命中或官网初筛符合，不等于商品已审核，更不等于适合所有用户。

## 系统如何工作

```text
包装图片 → 腾讯 OCR 草稿 → 用户确认 → 配料与营养结构化
                                      ↓
                            确定性规则 + 法规 RAG
                                      ↓
                         受控 Agent 解释 / 多轮对话
                                      ↓
用户约束 → 商品 RAG 检索 → 候选独立复核 → 本次筛选结果
                  ↑                         ↓
           证据索引更新 ← 来源刷新/人工审核 ← 缺口任务
```

项目采用 **Python 模块化单体 + 独立知识更新进程**。Starlette 提供网页和 API，LangGraph 编排标签工作流，白名单 MCP 工具执行限定业务操作。模型参与解释、召回和重排；风险等级、数值比较和推荐资格由程序判断。

| 模块 | 职责与边界 |
| --- | --- |
| 标签识别 | 默认腾讯 OCR，支持本地 Paddle；保留原文、坐标和置信度，识别结果须经确认 |
| 确定性判断 | 配料结构、过敏原、营养口径、包装声称检查；缺失数据保留未知 |
| 法规 RAG | 按法域、日期和版本过滤，再做关键词/向量召回与独立重排 |
| 商品 RAG | 检索目录标签、官网资料、外部 API 资料及 OCR 草稿，保留来源和审核层级 |
| 统一替代品流程 | 网页与对话共享官网初筛、缺口记录和图工作流，逐次应用用户约束 |
| 证据补齐 | 外部来源按月复查；后台本地对账更新索引、关闭或重新打开缺口 |
| 人工复核 | `/knowledge-review` 展示字段依据、冲突和审核任务；资料录入不自动获得推荐资格 |

商品身份、来源版本、字段值、单位、计量口径与审核状态一起保存。不同规格不按同名自动合并；“未查到成分”不等于“不含”，碳水化合物也不能替代总糖数值。

## 当前验证与已知缺口

截至 **2026-10-05**：

| 验证范围 | 结果 | 解释 |
| --- | --- | --- |
| 自动化回归 | 707 项通过 | 包括 HTTP/对话一致性、缺口回流、版本变化和错误降级 |
| 正式官网资料隔离验证 | 77 条候选中 66 条属于受支持来源并建立商品索引 | 其余 11 条保留在发现队列；候选数不是可推荐商品数 |
| 酸奶规则回归 | 50 组合成用例符合预期 | 由助手编制规则期望，不是独立人工标注的真实商品准确率 |
| 现有酸奶资料覆盖 | 39 条记录、48 组普通查询中 18 组出现官网初步匹配 | 包含规格变体；不代表真实用户成功率或 RAG 提升幅度 |

仍需补齐同一 SKU 的完整标签、糖数值和过敏相关证据；来源没有提供的数据不会由模型推算。需要独立真实查询集与 RAG 开关对照，才能判断搜索成功率是否提高。

本轮重构已在代码及隔离环境验证，**尚未重启正式后台**。历史评测按日期保留，不能当成当前版本的重新验证结果。详见 [文档导航](docs/README.md) 与 [统一证据流程](docs/architecture/ADR-012-unified-product-evidence-flow.md)。

## 快速开始

需要 Python 3.11–3.14，开发建议使用 Python 3.13。

### 1. 安装

```bash
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -e '.[dev,cloud-ocr]'
```

本地 OCR 的可选依赖较大，单独参考 [Paddle 配置](docs/ocr/PP-OCRv6_CONFIGURATION_GUIDE.md)。

### 2. 配置凭证

密钥放在仓库外的 `~/.config/food-label-agent/.env`。这是文件，使用编辑器打开，不是用 `cd` 进入。

```bash
mkdir -p "$HOME/.config/food-label-agent"
chmod 700 "$HOME/.config/food-label-agent"
touch "$HOME/.config/food-label-agent/.env"
chmod 600 "$HOME/.config/food-label-agent/.env"
```

按实际服务填写，以下不包含真实密钥：

```dotenv
OPENAI_API_KEY='替换为自己的密钥'
FOOD_LABEL_OCR_PROVIDER='tencent'
FOOD_LABEL_TENCENT_REGION='ap-guangzhou'
FOOD_LABEL_CHAT_PROVIDER='openai'
FOOD_LABEL_CHAT_MODEL='gpt-5.6-terra'
FOOD_LABEL_CHAT_REASONING_EFFORT='low'
FOOD_LABEL_RAG_PROFILE='hybrid_dense_rerank'
FOOD_LABEL_RAG_EMBEDDING_MODEL='text-embedding-3-large'
FOOD_LABEL_RAG_EMBEDDING_DIMENSIONS='1024'
FOOD_LABEL_RAG_RERANKER_MODEL='gpt-5.6-terra'
FOOD_LABEL_PRODUCT_RAG_PROFILE='hybrid_dense_rerank'
FOOD_LABEL_PRODUCT_CATALOG='official_cn_expanded'
```

腾讯云凭证的具体配置见 [腾讯 OCR 指南](docs/ocr/TENCENT_CLOUD_CONFIGURATION_GUIDE.md)。模型名称是本项目配置，变更模型后应重新评测。没有远程 RAG 服务时，可显式使用 `hybrid_tfidf` 做本地开发。

### 3. 启动网页

在项目根目录加载上述配置，再启动：

```bash
set -a
source "$HOME/.config/food-label-agent/.env"
set +a
.venv/bin/python -m uvicorn food_label_agent.web.app:app --host 127.0.0.1 --port 8000
```

访问 [本地网页](http://127.0.0.1:8000/)，用 `/api/health` 查看配置与持久化状态，用 `/api/ready` 检查生产就绪条件。

**开发入口 `web.app:app` 默认使用内存工作流和对话存储，重启会丢失这些会话。** 商品知识库文件可持久化，不代表会话也持久化。生产部署应使用生产工厂与持久卷，并确认健康检查中的 `durable` 为 `true`。现有 `run_local_platform.sh` 含本机绝对路径，其他机器优先使用上述命令。

### 4. 启动知识更新

网页与后台需要使用相同的 `FOOD_LABEL_DATA_DIR`；默认目录为 `~/.local/share/food-label-health-agent`。如设置 `FOOD_LABEL_PRODUCT_RAG_DB`，两端也必须一致。

```bash
./scripts/run_local_knowledge_refresh.sh --once  # 运行到期任务
./scripts/run_local_knowledge_refresh.sh         # 持续调度
```

外部 API 与官方来源默认按自然月复查；本地补齐对账每次后台运行都会执行，不增加网络抓取频率。包装 OCR 默认启用并沿用配置的 Provider，`--no-ocr` 仅暂停后台图片识别。

手动录入来源如果没有下载适配器，仍需人工提供新版资料。服务未运行时不会自动更新；完整说明见 [月度刷新](docs/architecture/ADR-008-product-knowledge-refresh.md)。

## 开发与验证

```bash
.venv/bin/python -m pytest -q
.venv/bin/python -m ruff check src tests
.venv/bin/python -m mypy
```

`mypy` 的项目门禁仅覆盖配置中的四个安全关键文件。自动化测试验证程序行为，不替代真人试用、独立标签标注或生产发布验收。

商品筛选模拟评测（不调用付费接口）：

```bash
.venv/bin/python -m food_label_agent.evaluation.yogurt_validation \
  --input artifacts/public-expansion-2026-10-04/combined-candidates.json \
  --output /tmp/yogurt-validation.json
```

更多离线、真实模型和发布评测入口见 [评测说明](docs/evaluation/README.md)。

## 部署与数据边界

- 生产入口、HTTPS、访问令牌、备份和持久卷配置见 [部署说明](docs/DEPLOYMENT_CN.md)。
- 用户确认事实、OCR 草稿、官网字段和已审核包装证据分层使用。
- 对话与长期记忆有不同生命周期；长期记忆需要用户显式授权。
- 模型不能降低严重过敏风险、跳过最终安全门或把未知当作符合。
- 系统不提供医疗诊断、个体化营养处方或绝对安全保证。
- API Key、私人标签照片、正式用户数据库不应提交到 Git。

## 代码与文档导航

```text
src/food_label_agent/
├── web/                         网页、HTTP API
├── graph/                       状态、受控 Agent、共享工作流
├── mcp/                         白名单业务工具
├── ocr/                         OCR Provider 与质量门
├── ingredients/ nutrition/      配料、过敏与营养规则
├── claims/                      包装声称核对
├── regulations/                 法规 RAG
├── alternatives/                商品 RAG、证据、复核、补齐与刷新
├── conversation/ persistence/   对话、检查点与授权记忆
└── evaluation/ observability/   评测与运行记录
```

- [文档导航](docs/README.md)：按产品、架构、运行、评测查找。
- [产品上下文](PRODUCT.md) / [设计系统](DESIGN.md)：产品与界面约束。
- [架构决策目录](docs/architecture/README.md)：ADR-001 至 ADR-012。
- [历史记录](docs/archive/README.md)：保留实质进展；重复日报已清理，旧版本可从 Git 历史恢复。

## License

Proprietary。除非项目所有者另行授权，不授予复制、分发或商业使用许可。
