# ADR-006：策略保护的模型辅助 Planner

状态：Accepted  
日期：2026-08-12

## 背景

确定性 ReAct 策略安全、可复现，但无法评估模型面对多个合法证据动作时的动态规划价值。直接让模型生成工具名和参数，会扩大提示注入、错误参数、风险降级和不可审计决策的攻击面。

## 决策

在 `react_orchestrator` 内增加可选的动作提议器，形成以下边界：

```text
Policy builds legal candidates
→ Model proposes one action_id
→ Policy validates membership
→ System-owned arguments execute MCP tool
→ Observation updates AgentState
→ final_safety_gate validates the result
```

默认 Provider 为 `deterministic`。只有部署者同时设置 `FOOD_LABEL_PLANNER_PROVIDER=openai` 与服务端 `OPENAI_API_KEY` 时才调用 OpenAI Responses API。默认模型为 `gpt-5.6-terra`，输出通过严格 JSON Schema 限定为当前候选动作 ID。

## 所属架构

- 层：Agent 编排与规划层，不改变标签事实层、规则层或 RAG 索引；
- LangGraph 节点：仅 `react_orchestrator`；
- MCP 工具：`search_food_regulations`、`explain_ingredient`、`interpret_label_claim`、`verify_label_consistency`；
- 状态：读取节点裁剪后的确认事实与证据；写入 `tool_trace`、`audit_events` 和既有工具结果字段；
- 安全门：`normalize_label`、`evaluate_safety` 和 `final_safety_gate` 仍在模型控制之外。

模型只收到候选动作的 `action_id`、工具名和用途摘要，不能返回工具参数。真正的法域、日期、主题、证据 ID 和配料内容仍由确定性动作对象提供。模型提议不合法、输出无效、缺少凭证、被拒答、超时或 Provider 失败时，系统记录错误码并选择确定性候选，不阻断原本可完成的工作流。

## 隐私与审计

Planner 会处理确认后的标签事实、用户约束、当前风险与证据摘要，但不接收原始图片。远程请求设置 `store: false`，并使用请求 ID 的不可逆哈希作为 `safety_identifier`。网页健康状态向用户披露远程 Planner 是否启用。

系统只记录 Provider、模型、响应 ID、输入/输出 token 数、候选数量、接受或回退结果和错误码，不保存自由文本推理。风险结果仍由确定性规则产生，Planner 不写 `risk_findings`。

## 消融评测

`food-label-planner-eval` 比较三种配置：

1. 确定性 Planner：固定基线动作；
2. 原始模型提议：度量动作准确率和非法动作率；
3. 策略保护模型：度量校验后准确率、策略违规率和回退率。

`planner_benchmark_v2` 使用数据驱动的 16 个案例，按安全优先级、标签冲突、证据缺口和多重约束四类分别报告指标。部分案例故意将期望动作放在第二候选位，避免“永远选择第一项”的伪 Planner 获得满分。模型保护后准确率不得低于 85%，也不得低于确定性基线。

统一离线评测只运行确定性基线，因此不会意外发送数据。`--live` 才执行真实模型消融。发布不允许保护后出现非法动作，也不允许相对于基线发生动作回归。原始模型的非法提议会作为可观测的模型质量指标，但只要被策略完全阻断，就不会成为系统安全违规。测试还注入未批准动作和 Provider 持续失败，确认它们会被记录并回退，而不会穿透策略边界。

## 后果

系统具备真实、可替换、可评测的模型规划能力，同时保留确定性 fallback。模型的价值可以用消融实验验证，而不是仅凭演示判断；模型升级不需要改变 MCP 参数合同或安全门。
