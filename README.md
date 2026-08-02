# Food Label Health Agent

一个以食品标签健康信息解释为核心的多模态 Agent。目标架构为：

- 单个模块化 MCP Server
- LangGraph 状态机
- 混合 RAG（关键词 + 向量 + 重排 + 版本过滤）
- 确定性过敏原规则引擎

当前阶段完成了工程骨架、Agent 状态协议、安全路由和 MCP 能力边界。OCR、法规数据和商品检索仍是后续里程碑，不会在当前骨架中伪造实现。

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

## 文档

- [中英双语产品说明书](./Food_Label_Health_Agent_Product_Spec_Bilingual.md)
- [ADR-001：Agent 状态与安全路由](./docs/architecture/ADR-001-agent-state-and-safety-routing.md)
