# ADR-002：受约束 ReAct 与工具轨迹

状态：Accepted  
日期：2026-08-09

## 背景

固定顺序调用所有解释工具会产生不必要的法规检索，也无法体现最终 Agent 按标签事实选择下一步工具的能力。完全自由的 ReAct 又可能跳过 OCR 确认、确定性过敏原规则或最终安全门。

## 决策

在 `evaluate_safety` 与 `final_safety_gate` 之间加入 `react_orchestrator`。它使用可测试的策略逐步选择下一项 MCP 调用，并且只允许以下工具：

- `search_food_regulations`
- `explain_ingredient`
- `interpret_label_claim`
- `verify_label_consistency`

`normalize_food_label` 和 `evaluate_user_constraints` 仍由 LangGraph 固定主路径调用，不交给 ReAct 决定。`final_safety_gate` 也保持在循环之外，因此编排器不能跳过事实层、安全评估或最终结论校验。

## 状态与边界

编排节点读取已确认的 `label_fields`、`normalized_label`、`user_constraints`、`risk_findings`、`regulatory_evidence` 以及法域和日期。它更新解释、法规证据、未知项和以下两个专用字段：

- `tool_trace`：记录步骤、动作、工具、原因码、调用前后状态和压缩观察；
- `react_budget`：记录最大步骤、最大工具调用和已使用调用数。

轨迹不保存工具参数中的原始标签全文，也不保存自由文本推理或模型思维链。

## 安全不变量

1. 配料等关键字段未确认时停止，并返回人工确认状态；
2. 标签未规范化或约束尚未逐项评估时阻断循环；
3. 工具必须同时满足允许列表和动作名称匹配；
4. 工具错误、步骤耗尽或调用预算耗尽均产生结构化阻断轨迹；
5. 编排器不修改 `risk_findings`，尤其不能把 `avoid` 降为 `compatible`；
6. 正常停止后仍必须经过 `final_safety_gate`；
7. 法规未检索到时保留 `unknown`，不重复调用同一目的的检索，也不生成肯定合规结论。

## 评测

Agent 轨迹评测计算工具序列精确匹配、选择精确率、召回率、不必要调用率和允许工具率。以下情况作为发布阻断项：

- 调用未批准工具；
- 工具失败或预算耗尽；
- 缺少正常停止事件；
- 绕过最终安全门；
- 硬风险结论被改变。

集成测试覆盖复合场景的完整工具序列、无需工具的短路、前置条件阻断、预算阻断以及 `avoid` 结果保持不变。

## 后果

系统第一次具备真实但有边界的工具选择能力，同时保持安全流程可复现、可审计和不依赖隐式思维链。初始版本只使用确定性选择；模型辅助提议器已经按 ADR-006 接入，但仍必须通过相同的允许列表、前置条件、预算和最终安全门验证。
