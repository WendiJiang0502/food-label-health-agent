# Food Label Health Agent

一个以食品标签健康信息解释为核心的多模态 Agent。目标架构为：

- 单个模块化 MCP Server
- LangGraph 状态机
- 混合 RAG（关键词 + 向量 + 重排 + 版本过滤）
- 确定性过敏原规则引擎

当前阶段完成了工程骨架、Agent 状态协议、安全路由、MCP 能力边界，以及可操作的图片上传与人工确认平台。平台默认使用明确标注的演示 OCR Provider；部署者可在服务器端选择腾讯云高精度 OCR 或本地 PP-OCRv6，任何模型识别结果仍必须经过证据检查和必要的人工确认。法规数据和商品检索仍是后续里程碑，不会在当前界面中伪造实现。

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

启动本地平台：

```bash
food-label-platform
```

然后访问 `http://127.0.0.1:8000`。上传图片不会持久化；PP-OCRv6 适配器如需临时文件，会在单次识别结束后立即删除。

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
- [PP-OCRv6 配置教程](./docs/ocr/PP-OCRv6_CONFIGURATION_GUIDE.md)
- [腾讯云 OCR 配置教程](./docs/ocr/TENCENT_CLOUD_CONFIGURATION_GUIDE.md)
- [产品上下文](./PRODUCT.md)
- [界面设计系统](./DESIGN.md)
