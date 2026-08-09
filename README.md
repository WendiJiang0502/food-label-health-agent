# Food Label Health Agent

一个以食品标签健康信息解释为核心的多模态 Agent。目标架构为：

- 单个模块化 MCP Server
- LangGraph 状态机
- 混合 RAG（关键词 + 向量 + 重排 + 版本过滤）
- 确定性过敏原规则引擎

当前阶段已完成工程骨架、Agent 状态协议、安全路由、配料树状规范化、中国八类常见致敏物质的确定性规则，以及从图片上传、人工确认到个人约束评估的网页闭环。平台默认使用腾讯云高精度 OCR，也可由部署者切换到本地 PP-OCRv6；任何模型识别结果仍必须经过证据检查和必要的人工确认。法规层已经具备官方标准注册、结构化 PDF 分片、版本/适用日期过滤和 BM25 基线检索；配料解释会绑定具体官方条款，并由最终安全门阻断失效引用和风险降级。包装声称层已支持“无糖、低糖、无蔗糖、不添加糖、不添加蔗糖”的非等价解释，并用确定性规则交叉核对已确认的配料与糖含量；数值或计量口径缺失时只返回 `unknown`。商品替代品检索仍是后续里程碑，不会在当前界面中伪造实现。

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

然后访问 `http://127.0.0.1:8000`。项目 CLI 默认使用腾讯云 OCR；这个默认值只包含 Provider 选择，不包含任何密钥。凭证继续由腾讯云 SDK 的环境变量或 `~/.tencentcloud/credentials` 提供。上传图片会发送到腾云 OCR，本平台不持久化原图。如需本地识别，可显式设置 `FOOD_LABEL_OCR_PROVIDER=paddle`。

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
- [PP-OCRv6 配置教程](./docs/ocr/PP-OCRv6_CONFIGURATION_GUIDE.md)
- [腾讯云 OCR 配置教程](./docs/ocr/TENCENT_CLOUD_CONFIGURATION_GUIDE.md)
- [腾讯云 OCR 匿名评测记录](./docs/ocr/TENCENT_OCR_EVALUATION_2026-08-05.md)
- [法规官方来源与索引清单](./docs/regulations/OFFICIAL_SOURCE_MANIFEST.md)
- [产品上下文](./PRODUCT.md)
- [界面设计系统](./DESIGN.md)
