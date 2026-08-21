# 内部试用集 v1

文件：`docs/evaluation/internal_pilot_dataset_v1.json`

本试用集用于验证完整任务，而不是单独验证 OCR。所有 `label_facts` 都视为已经过 OCR 质量检查并由用户确认的标签事实。

目前分为两个入口：

- 个人约束安全判断：`scripts/run_internal_pilot.py`；
- 通用配料/声称解释：`scripts/run_general_explanations.py`。

运行两个入口并生成统一回归报告：

```bash
PYTHONPATH=src ./.venv/bin/python scripts/run_pilot_suite.py --json /tmp/internal-pilot-suite.json
```

## 状态定义

- `compatible`：在当前已知事实和用户约束下，没有发现阻断项。
- `blocked`：确定性规则发现不满足用户约束或声称存在明确冲突。
- `unknown`：证据、字段或适用条件不足，不能安全判断。
- `needs_confirmation`：需要用户确认关键标签事实或风险提示。

## 通过标准

每个 case 至少检查：

1. 最终状态是否等于 `expected_status`；
2. `expected_findings` 是否全部出现；
3. `must_not_claim` 是否全部未出现；
4. `required_evidence` 是否已被最终结果或审计轨迹引用；
5. 替代品是否经过独立的相同硬约束复核。

高风险错误包括：把 `blocked` 输出为 `compatible`、把 `unknown` 猜成安全、把未确认事实用于肯定判断、或推荐未完成复核的替代品。

## 使用方式

先使用这 20 个固定案例跑现有工作流，保存每个 case 的：最终状态、完整轨迹、证据 ID、耗时、工具调用次数和人工备注。任何失败都应新增为回归案例，或修订现有案例的预期并记录原因。
