# 西门子 Software Engineer–AI 面试准备

准备日期：2026-10-02。依据：用户提供的简历、两张 JD 图片、三页面经，以及当前食品标签项目源码和历史评测报告。面经是备考线索，不是本轮面试流程承诺。本文未重新运行评测、调用业务模型或验证生产部署；历史数字均保留其样本和日期边界。其他项目仅依据简历，未核对源码。

## 1. 你的定位与准备顺序

核心定位：有真实业务交付经验，并能把 LLM 接入可测试、可约束、可追踪的软件系统的工程师。

| 准备优先级 | 面试官要判断什么 | 你的最佳素材 |
|---|---|---|
| 第一：Agent 项目 | 是否真正理解架构、权限、失败和取舍 | 食品标签的事实确认、规则、受约束规划、最终安全门 |
| 第一：Harness 与评测 | 能否证明系统行为，而不只展示成功回答 | 非法动作注入、预算耗尽、风险保持、检索消融、发布阻断 |
| 第一：软件设计 | 是否会写可维护、可替换、可测试的代码 | Provider Protocol、依赖注入、纯路由函数、框架适配层 |
| 第二：RAG | 是否懂召回、排序、适用性和证据支持的区别 | 版本过滤、BM25 + Dense + RRF、独立重排 |
| 第二：英语 | 是否能用英语解释同一个工程决策 | 项目介绍、harness、困难、daily work |
| 第二：生产工程 | 对并发、缓存、认证、故障是否有经验 | eSIM 支付和交付；Artist Search 的认证 |
| 第二：手写代码 | 能否先澄清题意，再给正确实现和复杂度 | 两数之和、返回原始下标的三数之和 |
| 第三：医疗与基础 AI | 对使用边界和开发流程是否有判断 | 风险管理、验证与确认、模型局限；不声称医疗器械研发经验 |

建议按备考时间分配约 50% 项目、20% 软件工程、15% 英语、15% 算法与其余基础。这是准备建议，不是面试概率预测。

## 2. 中文自我介绍：约 60–90 秒

我叫江文迪，本科在 UC San Diego 学习数学与计算机科学，硕士毕业于 USC 计算机科学专业。

我的经验主要有两部分。第一部分是业务软件开发，在 Simlessly 参与 eSIM 产品，负责过订单、支付、优惠券和第三方服务集成，也做过 Flutter 白标客户端和运营后台。第二部分是 AI 应用工程，最近重点做了食品标签解释 Agent 和只读股票研究 Agent。

其中食品标签项目最核心的问题，是不能让模型把不完整的图片识别结果直接解释成安全结论。我把系统拆成 OCR 与人工确认、确定性风险规则、版本感知法规检索，以及受策略约束的工具调用。模型负责选择允许的证据动作和组织解释，关键风险判断由程序维护。

我希望把已有的软件交付经验和 Agent 工程经验结合起来，参与更重视可靠性、测试和可追溯性的 AI 软件开发，这也是这份岗位最吸引我的地方。

注意：个人贡献、团队人数、开发时间、AI 编程工具的参与程度，只按真实情况补充；不要从仓库存在某个功能推导出自己独立完成了全部代码。

## 3. 食品 Agent：两分钟介绍

这个项目面向预包装食品标签解释。用户上传包装图片，系统识别配料、过敏原和营养信息，再结合用户约束解释需要关注的内容，并在证据允许时查找同用途备选。

我重点解决的是事实可信度和模型权限问题。例如 OCR 把营养表数字识别错了，或者漏掉复合配料里的某个成分，后面即使模型推理流畅，结论也可能不可靠。所以图片识别结果先作为草稿，关键事实经确认后才进入分析。

架构上，LangGraph 负责显式工作流。规范化和风险规则是必经步骤，中间的受约束工具循环补充法规、配料和包装声称证据，最后再经过安全门。Planner 默认是确定性策略，也支持模型从系统生成的合法 action_id 中选择；工具参数由系统持有，模型不能自由改写。

法规检索先过滤法域和适用版本，再通过 BM25 与 Dense 检索、RRF 融合和独立重排找证据。替代品也必须重新检查相同约束，不能因为语义相似就推荐。

评测分成程序回归、真实模型评测和真实用户验证。当前已经有回归和小规模模型评测证据，但仍是封测候选版，独立 OCR 发布集、替代品完整商品证据和真人试用仍未完成。这个项目最有价值的实践，是把不确定性变成显式状态，并让系统在证据不足时停止或降级。

讲完后停住，让面试官选追问方向。不要一口气把所有技术名词念完。

## 4. 必须能画出的架构

```text
图片 + 用户约束
      ↓
OCR 草稿（文字、位置、置信度）
      ↓
质量检查 / 用户确认 ← 缺失、模糊、纠错后重新确认
      ↓
规范化事实：配料、营养数值、单位、计量口径
      ↓
确定性风险规则：风险 / 未知 / 待确认
      ↓
受约束工具循环
  策略生成候选 → Planner 选 action_id → 本地验证
      → 系统参数调用工具 → 写入证据与轨迹 → 继续或停止
      ↓
可选：同用途候选检索 → 同一套硬约束复核
      ↓
最终安全门 → 结构化结果

自由对话：读取已确认事实与风险，调用受控工具，生成解释并做输出边界检查
```

不要把上图说成“每次必然执行全部工具”。图描述必经边界和可选分支，工具调用按需要发生。也不要把自由对话模型和工作流 Planner 当成同一个组件。

## 5. 十四组高频项目追问

### 5.1 这是真 Agent，还是固定 workflow？

**短答：**这是固定安全工作流中嵌入有界工具规划的混合架构。事实确认、风险检查和最终安全门不交给模型；在允许的证据任务之间，Planner 可以根据状态选择下一步。

**继续追问：既然默认确定性策略，模型有什么价值？**

默认配置确实不是全自主模型 Agent。模型规划的价值需要通过多种合法动作存在时的优先级选择来验证，不能把框架名称当能力证明。项目有确定性基线、原始模型提议和受保护模型三组比较；如果模型没有净收益，保留确定性配置更合理。

**继续追问：为什么不用普通函数？**

业务规则本来就可以是普通函数。LangGraph 提供显式状态和分支编排；领域规则、路由和工具合同保持独立，便于脱离框架测试。代价是状态迁移和节点合同更复杂，简单线性任务未必值得使用图框架。

### 5.2 你怎么理解 harness engineering？

**短答：**我把 harness 理解为模型周围负责执行、约束和验证的系统，包括上下文、工具合同、状态、预算、错误恢复、轨迹和评测。Prompt 是其中一部分。

**对应本项目：**

| 组成 | 实际落点 | 要防止的错误 |
|---|---|---|
| 上下文 | 节点字段白名单、确认事实、约束和证据 | 把未确认 OCR 或无关历史当事实 |
| 权限 | 候选 action_id、本地成员校验、系统工具参数 | 越权工具和篡改参数 |
| 执行预算 | 步数、工具调用数、有限重试 | 循环、成本和尾延迟失控 |
| 状态 | 风险与证据分层、检查点 | 隐式状态丢失或风险被覆盖 |
| 输出 | 最终安全门、对话边界检查 | 把未知包装成肯定答案 |
| 可观测性 | 工具结果、错误码、延迟、Token | 失败无法定位 |
| 评测 | 不变量测试、故障注入、消融、发布门禁 | 只看几个成功 demo |

**英文：**“The model proposes an action, but the runtime owns permission checks, tool arguments, execution budgets, and validation.”

### 5.3 如何防止模型绕过护栏？

先生成合法动作，再要求模型返回 action_id；返回后仍本地验证，不信任模型声称合法。真正的参数来自系统。工具选择还要满足前置条件和预算。循环不写 risk_findings，最终安全门在循环外。

举例：模型返回 DELETE_ALL_EVIDENCE，它不在候选集合里，系统记录非法提议并回退确定性策略，而不是尝试执行。对应测试在 tests/test_model_assisted_planner.py。

**关键边界：**结构化风险不被 Planner 改写，不代表自然语言永不矛盾。目前对话输出有短语替换和风险补充提示，尚不是完整的逐陈述语义验证。下一步可把关键结论模板化，再对自由解释进行事实支持与矛盾检查，并补充绕过测试。

### 5.4 OCR 为什么不直接交给多模态大模型？

我需要保留字段、坐标、置信度以及用户纠错入口，并让事实层独立于生成模型。Provider 抽象允许比较云端与本地 OCR。多模态模型也可以成为候选，但需要在独立标签集上比较字段召回、营养素与数值对齐、过敏原漏识别、延迟与成本。

置信度高不等于事实正确，人工确认也不是绝对正确。要同时做字段完整性、单位和口径校验，并允许纠错后重新分析。

**现状：**简历写 PaddleOCR；仓库当前说明默认腾讯云高精度 OCR，同时保留 Paddle 本地方案。面试解释为 Provider 演进，不要说线上始终只有 Paddle。

### 5.5 RAG 完整链路与 chunking 怎么讲？

离线：获取官方来源 → 按条款组织文本 → 保留标准号、法域、生效窗口、来源定位、内容哈希 → 建立可检索索引。在线：解析查询与适用条件 → 先过滤 → BM25/Dense 召回 → RRF → 独立重排 → 返回条款级证据 → 解释时引用。

法规适合保留条款结构，不能盲目固定字符切分而把条件和例外拆开。扩大语料时需要评估标题继承、上下文窗口、表格和跨条款引用。不要声称已经完成无限规模法规自动解析。

**为什么先过滤？**相似并不等于适用。错误法域、尚未生效或指定标准不匹配的条款不应进入候选，重排模型不能重新引入被排除内容。

**如何选日期？**应用显式接收适用日期。实际法规的过渡安排可能还需要生产日期和产品类别；仅有一个日期字段不能说明已完整建模所有法律适用规则。

### 5.6 BM25、Dense、RRF 和 Reranker 各自做什么？

BM25 擅长标准号、专有名词等精确词匹配；Dense 改善口语改写与语义相近表达。两者分数不可直接视为同一尺度。

项目 RRF 使用名次融合：score(d) = Σ 1 / (60 + rank_i(d))。60 是当前实现常数，不是普遍最优值。RRF 不需要直接校准两路原始分数，但也会丢失部分分数间距信息。

独立重排再比较 query 与候选条款。当前用模型返回已过滤的 evidence_id 排序，最多处理 20 个候选；不是已经部署了专用 cross-encoder。它不能新增条款，也不能弥补召回阶段完全漏掉的证据。

**对抗追问：引用存在就证明正确吗？**不能。还要验证条款是否支持这条陈述、版本是否适用、数值和条件是否一致。来源合法性、检索相关性和回答正确性是不同指标。

### 5.7 你用的是什么向量数据库？

当前法规规模下，项目使用本地 RegulationStore、Provider 生成向量、归一化后的余弦相似度计算和进程内缓存，没有使用 Milvus、Chroma 或 FAISS。SQLite 主要负责状态等持久化，不能因此称它为当前向量检索引擎。

我会按数据量、维度、更新频率、过滤需求、并发、P95、备份恢复、多租户和运维成本选型。当前小语料线性比较简单可复现；数据扩大后再用真实工作负载验证 ANN 索引的收益。

基础比较：FAISS 是向量相似性搜索库；Chroma 提供持久化和客户端/服务端使用方式；Milvus 有嵌入式、单机和分布式部署选项。不能简单说 FAISS 是完整数据库，或 Milvus 只能大规模分布式部署。[FAISS](https://faiss.ai/)、[Chroma](https://docs.trychroma.com/reference/python)、[Milvus](https://milvus.io/docs/install-overview.md)。

### 5.8 超时、重试、fallback 怎么做？

必须区分三类失败：Planner 提议失败可回退确定性动作；工具执行失败按有限次数重试并计入预算；证据依然不足时保留未知或阻断结果。重试不能无限制，存在副作用的写操作还需要幂等和状态核对。

**当前代码与文档差异：**旧 ADR-007 说 Dense/Reranker 失败后不自动回退，但 regulations/service.py 目前捕获 RAGProviderError 后自动调用 hybrid_tfidf，并记录 unknowns 降级标记。面试按代码解释，同时承认文档需要同步。不能说“任何远程失败都直接关闭”，也不能把 fallback 当原配置成功。

食品工作流默认预算是 32 步、32 次工具调用；Planner 单次默认超时 8 秒。简历里 4 轮、6 次工具、45 秒属于 SignalDesk，不可混用。单次超时不等于整个请求总时限，若设计总 deadline，应让各子调用消耗剩余预算。

### 5.9 如何降低延迟？

先拆解 OCR、确认等待、检索、重排、规划和生成，区分首 Token、完整回答、P50/P95、冷启动和缓存命中。用户确认等待也要和服务处理耗时分开。

当前可指认的实现：检索结果 LRU 缓存、向量进程内缓存、确定性模式下独立法规检索并行、按节点裁剪上下文、按对话意图选择推理强度。

进一步方案：减少无价值模型调用；离线预计算文档向量；只对必要请求重排；限制候选和输出长度；有依赖的步骤保持顺序；加总 deadline。流式输出改善感知等待，但不自动降低完成时间。

目前历史真实对话报告的完整响应 P95 约 7.31 秒，目标 7 秒未达到。不能承诺已达标，也不能用一轮消融总耗时当单请求 P95。

**缓存追问：**当前查询缓存键包含查询、法域、日期、主题和 limit，版本变化依赖清缓存。改进应显式纳入语料、规则、模型/profile 版本，并给降级结果设置恢复策略；否则远程服务恢复后，同一查询还可能继续命中降级缓存。多实例场景不能靠本机 LRU 解决一致性。

### 5.10 怎么评测 Agent，为什么不只用 LLM judge？

我分四层：事实层检查字段和数值；检索层检查条款级 Recall@K、MRR、版本适用性；轨迹层检查合法动作、预算和安全门；用户层检查任务完成、帮助程度和延迟。

明确风险能否降级、非法工具是否执行、引用 ID 是否存在，用程序判定更直接。解释是否清晰等主观维度可用人工或经过校准的模型评分，但不能由模型评分代替硬安全门。

要分别报告原始模型与最终系统表现。非法提议被拦截，说明系统防线有效；不代表模型没犯错。还要分清安全拒绝率与任务成功率，否则全部拒绝也可能获得虚假的高安全评分。

精确率 = TP/(TP+FP)，召回率 = TP/(TP+FN)。高风险漏报代价大时重视召回，但误报和过度拒绝也要单独监测。测试集零漏报不构成真实世界零漏报证明。

### 5.11 为什么替代品不能直接按 embedding 相似度排序？

相似度可以帮助找同用途候选，不能证明满足用户硬约束。必须核对具体 SKU、配方与规格、当前标签和过敏提示，并统一营养比较口径。每份和每 100 克不能未经换算直接比较；固体与液体之间也不能凭空假设密度。

当前目录有 93 件商品，但历史报告中精确 SKU/规格绑定、双人实物背标和当前可购买证据均为 0/93。核心门禁实现存在，发布数据未就绪，两者不能混为一谈。

### 5.12 如何处理记忆、恢复与用户纠错？

短期工作流检查点、短期对话和长期偏好分别管理。长期记忆须显式授权；原图不进入检查点和长期记忆。历史修正只能作为待核对信息，不能覆盖当前包装。

当前恢复是应用层 SQLite 显式状态持久化。虽然图构建接口可接收 checkpointer，生产 runtime 调用 build_graph 时未传入它，不要说“已直接用 LangGraph 原生持久化完成全部恢复”。

纠错后应让依赖旧事实的结果失效，重新进行规范化、规则与证据检查。若引入并发会话更新，进一步需要状态版本和冲突处理；不要把未来设计说成当前已支持多人并发编辑。

### 5.13 MCP 和普通函数调用有什么区别？

MCP 为外部工具接入提供标准化的工具描述和调用边界；函数调用是进程内的执行方式。项目把业务工具封装为可复用合同，并提供 MCP 暴露方式。

当前内部 invoke_mcp_tool 会查合同，然后调用 BUSINESS_TOOLS 中的本地 handler，并不是每次都通过远程 MCP 网络连接。使用 MCP 本身不会自动获得安全性，安全仍来自白名单、参数所有权、验证和隔离。

### 5.14 最大困难或最有价值的失败是什么？

可用的真实仓库案例：2026-09-12 的报告记录，最终发布门失败时，API 仍可能留下 eligible 候选，而前端没有独立检查该门。后来改为门失败就清空 eligible、禁止营养比较，并把原候选标为 FINAL_SAFETY_GATE_BLOCKED。

讲述顺序：用户可能看到不应显示的候选 → 定位到门禁结果与响应合同不一致 → 后端失败关闭并约束展示 → 用失败路径回归验证 → 将安全成功与业务成功拆开统计。

这是报告记载的工程故事。你必须能说明自己实际参与了哪些定位、决策和验证；不要虚构当时如何发现、花了多久或用户事故。

## 6. 数字口径：只背这些有边界的结果

| 数字 | 可以怎么说 | 不能怎么说 |
|---|---|---|
| 606/606；82.68% | README 记录的 9 月 13 日历史测试与覆盖率 | 我今天重跑也是这些数；全场景都安全 |
| 离线对话 112/112 | 固定程序契约评测通过 | 112 名真实用户全部满意 |
| 真实模型全集 111/112 | M9 报告有失败契约修正和单例复跑 | 修改后完整全集已重新 112/112 |
| RAG 12 案 | 11 个可回答问题加 1 个无证据场景 | 大规模外部集 RAG 准确率 100% |
| Recall@5 90.91% → 100% | 8 月 12 日小样本消融，提升 9.09 个百分点 | 提升 9.09% 就能证明所有问题都改善 |
| MRR 81.82% → 100% | 同轮消融提升 18.18 个百分点 | 检索质量等于回答质量 |
| 140 条 / 14 类；95% | 独立留出替代意图集的 Top-1 / Macro Recall | 95% 商品推荐成功率 |
| P95 7312.64 ms | 历史真实对话观测，尚高于 7000 ms 目标 | SLA 已达标 |
| OCR 9 张开发样本 | 参与调优的小规模开发证据 | 独立盲测或生产泛化水平 |
| 真人 0 人 / 0 任务 | 真人验证尚未开始 | 产品已有真实用户成功率 |

不同日期报告包含 590、596、606 等测试数量；不是任意挑最大的数字。回答时指明版本和日期，最好面试前重新冻结一份结果。

## 7. 软件设计与工程八股：用自己的项目回答

### OOP、SOLID 与设计模式

封装：Provider 隐藏供应商请求和错误转换。多态：同一 OCRProvider/ActionProposer 合同可接不同实现。继承：表达合理的 is-a 关系，不是为了复用而堆继承树；项目更常用 Protocol 和组合。

单一职责：OCR、规则、检索、规划分开。开闭原则：新增 Provider 尽量不改安全核心。里氏替换：替代 Provider 不能破坏字段与错误合同。接口隔离：OCR 接口不混入检索职责。依赖倒置：高层依赖协议，测试可注入替身。

最值得讲三个模式：Strategy 对应可替换 Planner/Provider；Adapter 对应 SDK/框架到领域对象的转换；Factory 对应按配置构造 Provider。有限状态工作流可以讨论状态机，但没有使用经典 State 对象层次时，不必硬说完整实现了 State 模式。

### 单元、集成与端到端测试

单元：纯路由、单位归一化、非法 action_id 拦截。集成：模型替身 + 工具 + 状态更新 + 最终门。端到端：上传、确认、分析、纠错与结果展示。真实远程评测单独执行，避免普通测试依赖网络和密钥。

医疗相关软件中，测试证据要对应需求与风险控制，但单元测试和高覆盖率仍不能替代系统级验证、实际使用确认和人工审查。

### CI/CD

当前 GitHub Actions 有静态检查、安全关键模块类型检查、pytest/覆盖率、确定性评测、安全扫描和浏览器可访问性检查。能说有 CI 门禁；不能说已经自动部署到生产，也不能说全项目严格类型检查全部通过。

### 并发、线程与进程

线程共享进程内存，通信较方便，也需要同步；进程通常有独立地址空间，隔离更强，通信开销更大。I/O 等待适合异步或线程；Python CPU 密集任务可考虑进程或释放 GIL 的原生库。不能绝对说所有 Python 版本和构建都不支持线程 CPU 并行。

项目例子：彼此独立的法规查询可并行；OCR 后才能做字段规范化，确认事实后才能算风险，这些有依赖的步骤不能盲目并行。

### 乐观锁、悲观锁与幂等

乐观锁通过版本号或条件更新检测冲突，适合冲突较少场景；悲观锁先持锁再修改，适合需要串行保护的高冲突更新，但要考虑阻塞和死锁。

支付 webhook 重复投递可讨论事件唯一标识、唯一约束、订单状态机和幂等交付；“收到两次只处理一次”须依赖原子操作，不能仅先查再写。只有你实际做过的方案才用过去时。

### B+ 树

内部节点用于导航，叶子存储索引记录，叶子有序连接便于范围扫描；较高扇出减少树高与磁盘访问。索引不是越多越好，会增加写入与维护成本。不要说所有数据库的所有存储结构都是 B+ 树。

### 缓存

进程内缓存简单但各实例独立；共享缓存便于集中管理但引入网络和故障依赖。讨论命中率、TTL、容量、版本失效、击穿和隐私隔离。项目里的 lru_cache 不等于分布式缓存或持久化索引。

## 8. 认证题：简历没写双令牌，别凭面经补造经历

简历只写 Artist Search 使用 JWT + Cookie，并没有证明有 refresh token。开场先说实际实现，再回答如果需要更长登录周期会怎样设计。

Access token 通常短期有效，用于访问资源；refresh token 用于获取新 access token，权限和暴露面应更受限。这样在登录体验和访问令牌泄漏窗口之间取舍，但也引入刷新、撤销和重放检测的状态。

Session 完全可以：服务端保存会话、客户端保存会话标识，撤销直接。JWT 可以让资源服务本地验签，但权限变更与立即撤销更复杂；不一定比 session 更好，也不等于整个系统无状态。

常见 JWT claims 有 sub、iss、aud、exp、iat，按需要加 jti 等；不要放密码或认为 payload 经过 Base64URL 就被加密。校验要固定允许算法、验证签名、到期时间、issuer 和 audience。

普通紧凑 JWS 的签名输入是编码后的 header、一个点、编码后的 payload；HS256 对其做 HMAC-SHA256，非“把密码和 payload 简单 hash”。非对称算法使用私钥签名、公钥验证。依据：[RFC 7515](https://www.rfc-editor.org/rfc/rfc7515.html)。

刷新机制可采用 token rotation、旧 token 失效与重放检测；RFC 9700 对公共客户端的 refresh token 要求发送者约束或轮换。不要把 refresh token rotation 说成你已经在项目做过。[RFC 9700](https://www.rfc-editor.org/info/rfc9700/)。

Cookie 讨论 HttpOnly、Secure、SameSite 与 CSRF 防护。HttpOnly 限制脚本读取 cookie，不等于 XSS 不再有危害。

## 9. 医疗背景与模型基础

### 为什么对这个岗位感兴趣？

这份 JD 同时强调软件架构、Agent harness、评测和风险护栏，和我希望深入的可靠 AI 应用方向一致。我的食品项目不是医疗器械，但它让我具体实践了事实追溯、风险边界和证据不足时降级。我希望在成熟团队中进一步学习更严格的软件生命周期和验证流程。

### IEC 62304 是什么？

这是医疗器械软件生命周期过程标准。面试可从开发、维护、风险相关活动、配置管理和问题解决的可追溯过程谈理解；不要说某一项单元测试通过就符合标准，也不要声称自己有认证交付经验。具体适用性需要团队专业判断。[IEC 官方条目](https://webstore.iec.ch/en/publication/22794)。

### 医疗软件是否不能敏捷？

可以迭代，但变更需要可追踪的需求、风险分析、审查和验证证据。关键不是慢，而是每次变更都能说明影响范围与风险控制是否仍有效。

### 如果做医生辅助 AI，重点风险是什么？

输入缺失或错误、患者或版本混淆、证据不适用、模型幻觉、自动化偏见、隐私与访问权限、服务不可用和责任边界。明确预期用途，保留人工复核、失败提示和可追溯证据。不要把食品过敏规则直接等同于临床诊断系统。

### 模型漂移与监控

区分输入分布改变、模型或提示版本改变、检索语料更新、用户行为变化。监测拒答、纠错、证据一致性、分层任务成功、风险事件、延迟和成本；定期人工抽样并回放冻结基准。不能仅看平均用户评分。

### AI 基础速答

预训练学习广泛的语言模式；后训练可通过监督微调、偏好优化等改善任务与行为。RAG 提供外部证据；微调改变模型行为或能力，两者解决的问题不同，也不能自动消除幻觉。

生成模型输出是条件概率预测，不天然保证事实真实。temperature 较低也不构成事实正确或完全可复现的保证。

卷积利用局部连接和参数共享提取特征；stride 影响采样步长，padding 影响边界和输出尺寸。准备自己写出二维卷积输出尺寸并解释其假设。

推理优化先分应用层和模型服务层。项目能重点谈减少调用、上下文裁剪、缓存和并行；量化、批处理、KV cache、推测解码属于模型服务层知识，没有实践就不要说自己部署优化过。

Kubernetes 至少解释 Pod、Deployment、Service、健康探针、资源限制和滚动更新。当前食品项目没有足够证据证明完成了 K8s 生产部署，回答可说了解概念、当前方案先采用单服务部署。

## 10. 英语切换练习

### Self-introduction

Hi, I'm Wendi Jiang. I have a master's degree in Computer Science from USC and a bachelor's degree in Mathematics and Computer Science from UC San Diego. My background combines product engineering with AI application development. At Simlessly, I worked on eSIM applications, including order and payment workflows, backend integrations, and operational tools. More recently, I have been working on agents with explicit tool boundaries and evaluation pipelines. One example is my food-label project, where I separate confirmed label facts, deterministic risk checks, and model-generated explanations. I'm interested in this role because it combines software engineering with reliable AI systems.

### Explain the agent architecture

The system starts with a food-label image, but OCR output is treated as a draft. After the relevant fields are confirmed, the workflow normalizes the data and runs deterministic checks. A bounded tool loop then gathers supporting evidence. The planner can select an action from a policy-generated candidate set, while the runtime owns the tool arguments and execution. A final safety gate remains outside that loop. The current version is a closed-pilot candidate, and real-user validation is still pending.

### What is your harness?

I use the term harness to describe the runtime around the model: context construction, tool contracts, permission checks, execution budgets, recovery, tracing, and evaluation. For example, my planner returns an action ID rather than arbitrary tool arguments. The runtime validates that choice and falls back to a deterministic policy if the proposal is invalid. This lets me evaluate model quality separately from system-level safety.

### Describe a limitation

One limitation is that our evaluation sets are still small. Passing those tests demonstrates specific contracts, but it does not establish production safety. Another limitation is that preserving a structured risk result does not guarantee that every generated sentence is consistent with it. I would strengthen that boundary with structured claims, evidence checks, and broader adversarial tests.

### Describe daily work

可用下面结构，改成自己真实做过的日常：I usually start by clarifying the user problem and identifying the affected services. Then I break the work into testable changes, implement the core logic, and verify both the normal path and failure cases. For integrations, I pay particular attention to retries, state consistency, and observability. When an issue is unclear, I collect a reproducible example and communicate the impact and next steps to the team.

### 常用澄清句

- “Would you like me to focus on the architecture or the implementation details?”
- “Let me separate what is implemented from what I would improve next.”
- “That result comes from a small offline benchmark, not a production study.”
- “I haven't implemented that part in production, but here is how I would approach it.”

## 11. 手写算法：返回下标

先澄清：返回任意一组还是所有组合？下标必须不同吗？无解返回什么？能否修改输入？以下实现返回任意一组不同的原始下标。

```python
def two_sum(nums, target):
    seen = {}
    for j, value in enumerate(nums):
        needed = target - value
        if needed in seen:
            return [seen[needed], j]
        seen[value] = j
    return []


def three_sum_indices(nums, target):
    for i in range(len(nums) - 2):
        seen = {}
        for j in range(i + 1, len(nums)):
            needed = target - nums[i] - nums[j]
            if needed in seen:
                return [i, seen[needed], j]
            seen[nums[j]] = j
    return []
```

两数之和期望时间 O(n)、空间 O(n)。三数之和期望时间 O(n²)、额外空间 O(n)。先查询再插入，保证不重复用当前下标；每轮重建 seen，保证三下标不同。

口头跑：[3,3], target=6；[0,0,0], target=0；负数、重复数、无解、长度不足。返回所有下标组合时，重复值可能产生大量结果，原实现只存一个下标不再够用，复杂度还要计算输出规模。

面试官要求双指针时，排序 (value, original_index)，固定第一项后移动左右指针；不要排序后丢掉原始下标。

## 12. 另外三个简历入口别失守

**SignalDesk：**准备只读权限、预算如何计数、事实验证到什么粒度、数值单位/日期如何核对、Tracked Thesis 如何触发复盘。简历的“大幅消除幻觉”需要具体指标，若没有，改口说“对引用和数值做后验证，删除部分无支持陈述”。该项目源码本次未核验。

**Simlessly：**准备一个支付成功但供应商交付失败的场景，讲订单状态机、重试、幂等、补偿和告警。准备一个多白标配置设计例子。月营收是业务规模背景，不可把全部营收归因为个人开发工作。

**Artist Search：**JWT 放哪、Cookie 属性、用户隔离如何校验、收藏接口能否越权、过期与退出怎么处理。没有实现双令牌就明确说没有，不要由题库推导个人经历。

## 13. 24 小时与三天准备方案

只有一天：2 小时讲熟架构与 harness；2 小时复习 RAG、评测和失败案例；1 小时英语切换；1 小时 OOP、测试、认证；1 小时手写两题；最后 1 小时模拟追问与复盘。休息与作息优先于继续堆新名词。

有三天：第一天项目和源码，做到每个关键词都能指认模块；第二天工程基础、RAG 设计题和算法；第三天英语及完整模拟，重点修正绕圈回答、数字口径和个人贡献。

回答统一用“结论 → 实现 → 为什么 → 如何验证 → 现有限制”。每题第一层控制在 30–60 秒，收到追问再展开。

自测评分：0 分不会；1 分仅定义；2 分能对应代码；3 分能解释取舍、失败、指标边界。Agent/harness/RAG/评测/设计模式五项都应到 3 分。

## 14. 反问面试官

- 这个岗位近期更主要的工作，是新 Agent 原型，还是已有 AI 应用的生产工程化？
- 团队目前如何分别评估模型质量、工具执行可靠性和最终业务效果？
- AI 输出如何进入实际使用流程，哪些节点需要人工复核？
- 新人前三个月最希望解决的一个具体问题是什么？

## 15. 本地证据索引

所有路径相对项目根目录；本节用于自己复习，不必在面试中背文件名。

| 主题 | 依据 |
|---|---|
| 当前能力与阻断项 | README.md |
| 真正的图编排 | src/food_label_agent/graph/langgraph_adapter.py；runtime.py |
| 预算与循环 | src/food_label_agent/graph/react.py:120；state.py:96 |
| 模型候选合同 | src/food_label_agent/graph/planner.py |
| 非法提议与风险保持测试 | tests/test_model_assisted_planner.py |
| RRF 与独立重排 | src/food_label_agent/regulations/store.py:230 |
| 当前自动降级实现 | src/food_label_agent/regulations/service.py:64 |
| 输出护栏边界 | src/food_label_agent/conversation/service.py:522 |
| 本地工具执行 | src/food_label_agent/mcp/business_tools.py:274 |
| 记忆设计 | docs/architecture/ADR-004-context-checkpoints-and-consented-memory.md |
| RAG 历史消融 | docs/evaluation/RAG2_EVALUATION_2026-08-12.md |
| 真实失败和替代品限制 | docs/evaluation/PREPILOT_FULL_EVALUATION_2026-09-12.md |
| 真实模型与真人验证边界 | docs/evaluation/M9_CLOSED_PILOT_READINESS_2026-09-12.md |
| CI 配置 | .github/workflows/evaluation.yml |

个人贡献、面试日期和准备时长尚未提供；本稿没有替你编造这些信息。实际练习时，优先补齐自己负责的决策、最熟的一段代码和一次真实排障经过。
