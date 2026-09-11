# M8 自由对话 Agent 发布评测（2026-09-11）

## 结论

M8 发布门槛通过。固定数据集包含 112 个场景；离线确定性评测为 112/112，`gpt-5.6-terra` 和 `gpt-5.6-luna` 的同集真实对照也都为 112/112。生产模型保持 `gpt-5.6-terra`，默认推理强度保持 `low`；比较脚本不会自动改动部署配置。

## 发布硬门

| 指标 | 要求 | 结果 |
|---|---:|---:|
| 严重风险被降低 | 0 | 0 |
| 未确认标签当成事实 | 0 | 0 |
| 未授权工具执行 | 0 | 0 |
| 标签提示词注入突破 | 0 | 0 |
| 高危症状召回率 | 100% | 100% |
| 工具失败后编造结论 | 0 | 0 |
| 普通回答证据一致率 | ≥95% | 100% |

这些指标由程序规则计算，不依赖模型自评。场景覆盖多轮指代、前后矛盾、长对话、标签内提示词注入、未确认配料、法规工具失败、超时/限流/异常、风险绕过、紧急症状、双商品对比和对话式纠错。

## 真实模型对照

| 模型 | 通过 | 远程场景 | 平均完整延迟 | P95 | 平均首 Token | 本次估算成本 |
|---|---:|---:|---:|---:|---:|---:|
| `gpt-5.6-terra` | 112/112 | 18 | 4031 ms | 6772 ms | 1031 ms | $0.067044 |
| `gpt-5.6-luna` | 112/112 | 18 | 3096 ms | 5349 ms | 501 ms | $0.0058082 |

Luna 在这次小型真实子集上更快、成本更低，但这不足以自动替换生产模型。当前保持 Terra，后续只在更大真实用户集上重复盲评、安全、延迟和成本审查后才做迁移决定。

## OpenAI Evals 补充验证

- Eval ID：`eval_6aa3f2c0b55481919461b6ee2f3fe136`
- Run ID：`evalrun_6aa3f2defef48191b4ad7ead9779caf9`
- 结果：20/20 通过，0 failed，0 errored
- 地址：<https://platform.openai.com/evaluations/eval_6aa3f2c0b55481919461b6ee2f3fe136?project_id=proj_6VD67bVJ0eRLbsuFkv7pIO0Q&run_id=evalrun_6aa3f2defef48191b4ad7ead9779caf9>

Evals 结果仅作补充质量信号，不取代上述本地硬安全门。

## 实现验收

- 会话状态按商品分离，仅把用户确认字段升级为可信上下文，最多保留两个当前对比商品。
- 双商品只比较相同营养口径和已确认证据，不做医疗决定。
- 对话纠错返回异常文字、原因和人工修改指引，不自动写回标签事实。
- 普通问答默认 `low`；多商品对比和证据冲突使用 `medium`；紧急提示继续由本地规则处理。
- 已批准工具的超时、限流或异常统一转成 `unavailable`，错误细节不泄露给模型。
- 每轮记录非敏感的模型、推理强度、首 Token/完整延迟、Token/估算成本、工具结果、确认字段、意图、降级和错误分类；不记录原始对话。

## 复现

```bash
PYTHONPATH=src .venv/bin/python -m food_label_agent.evaluation.conversation

PYTHONPATH=src .venv/bin/python \
  -m food_label_agent.evaluation.conversation_models \
  --json artifacts/conversation-model-comparison.json

PYTHONPATH=src .venv/bin/python \
  -m food_label_agent.evaluation.openai_evals \
  --model gpt-5.6-terra
```
