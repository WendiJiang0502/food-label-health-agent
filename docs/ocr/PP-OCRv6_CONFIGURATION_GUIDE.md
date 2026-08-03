# PP-OCRv6 配置教程：中文食品标签优先，兼容英文版

本文说明如何在 Food Label Health Agent 的服务器端配置本地 PP-OCRv6。普通平台用户不需要配置 OCR，也不会接触模型路径、服务端环境变量或任何供应商凭证。代码已提供可切换的 `DemoOCRProvider` 与 `PaddleOCRProvider`；未配置时默认使用演示 Provider。

## 1. 这一步要建立什么

OCR 在本项目中不是一个直接输出“健康结论”的 Agent，而是标签事实提取层：

```text
食品标签图片
  -> 图像方向和形变处理
  -> PP-OCRv6 检测文字区域并识别文字
  -> 字段解析器提取配料表、过敏原提示等字段
  -> PP-StructureV3 解析营养成分表
  -> 用户确认低置信度或高风险字段
  -> LangGraph 才允许进入规则引擎和 RAG
```

推荐配置：

- 开发机主 OCR：`PP-OCRv6_medium`，macOS CPU 推理；
- 性能对照：`PP-OCRv6_small`；
- 营养成分表：按需单独启用 `PP-StructureV3`，默认关闭；
- 默认语言：保留 PP-OCRv6 的中英文统一能力，不指定仅英文模型；
- 生产环境：Linux + NVIDIA GPU，不直接复制 macOS 的推理依赖。

## 2. 当前机器情况

本项目当前开发机为：

```text
CPU 架构：Apple Silicon arm64
操作系统：macOS
当前 Python：3.13.7（Homebrew）
```

macOS 只能安装 PaddlePaddle CPU 版本。当前 Python 3.13 可以先尝试官方 wheel，但为了降低计算机视觉依赖的兼容风险，本项目推荐用 Python 3.12 创建独立环境。

这样做不会修改系统 Python，也不会影响其他项目。

## 3. 安装 Python 3.12

先检查是否已经安装：

```bash
python3.12 --version
```

如果提示找不到命令，并且已经安装 Homebrew：

```bash
brew install python@3.12
```

再次检查：

```bash
python3.12 --version
python3.12 -c "import platform; print(platform.machine())"
```

预期第二条命令输出：

```text
arm64
```

如果输出 `x86_64`，说明终端或 Python 可能运行在 Rosetta 模式下。不要继续混装不同架构的 wheel，应先换成 arm64 Python。

## 4. 创建项目虚拟环境

进入仓库：

```bash
cd "/Users/jiangwendi/Documents/食品标签解释与替代品agent"
```

如果项目根目录还没有 `.venv`：

```bash
python3.12 -m venv .venv
source .venv/bin/activate
```

如果已经有 `.venv`，先检查它使用的 Python：

```bash
source .venv/bin/activate
python --version
python -c "import platform; print(platform.machine())"
```

不要在不确认内容的情况下删除旧虚拟环境。如果旧环境不是 Python 3.12，后续可以建立一个独立的 `.venv-ocr`：

```bash
python3.12 -m venv .venv-ocr
source .venv-ocr/bin/activate
```

升级基础安装工具：

```bash
python -m pip install --upgrade pip setuptools wheel
```

## 5. 安装当前项目

确保终端提示符中已经出现虚拟环境名称，然后执行：

```bash
python -m pip install -e '.[dev]'
```

验证现有项目没有被 OCR 依赖破坏：

```bash
python -m pytest
```

所有测试应该通过。如果此时测试失败，应先处理基础环境问题，不要继续安装 OCR。

## 6. 安装 PaddlePaddle 和 PaddleOCR

### 6.1 macOS 本地 CPU 环境

按 PaddlePaddle 当前官方 macOS 安装方式执行：

```bash
python -m pip install paddlepaddle==3.2.0 \
  -i https://www.paddlepaddle.org.cn/packages/stable/cpu/
```

先验证推理框架：

```bash
python -c "import paddle; paddle.utils.run_check(); print(paddle.__version__)"
```

成功后安装基础 OCR 包：

```bash
python -m pip install paddleocr
```

第一阶段不使用：

```bash
python -m pip install 'paddleocr[all]'
```

`[all]` 会引入文档理解、翻译、公式等当前不需要的依赖。先安装基础包能减少冲突、下载体积和排错范围。等开始营养表结构识别时，再根据 PP-StructureV3 的依赖组进行扩展。

### 6.2 如果 Python 3.13 找不到兼容 wheel

典型错误是：

```text
No matching distribution found for paddlepaddle
```

这通常不是代码错误，而是 Python 版本、CPU 架构或软件源中没有对应 wheel。依次确认：

```bash
python --version
python -c "import platform; print(platform.machine())"
python -m pip --version
```

然后切换到前述 Python 3.12 环境，不要使用 `sudo pip`，也不要把 x86_64 和 arm64 包混在同一个环境中。

## 7. 第一次运行 PP-OCRv6

准备一张清晰的食品标签测试图，例如：

```text
samples/labels/chinese-label-001.jpg
```

出于隐私和版权考虑，真实用户图片不应提交到 Git。测试图片目录后续应配合 `.gitignore` 和明确的数据授权策略。

执行基础识别：

```bash
paddleocr ocr \
  -i samples/labels/chinese-label-001.jpg \
  --use_doc_orientation_classify True \
  --use_doc_unwarping True \
  --use_textline_orientation True
```

第一次执行会下载模型，所以耗时明显长于后续请求。模型下载完成后，重复处理同类图片会直接使用本地缓存。

也可以用一个最小 Python 脚本验证：

```python
from paddleocr import PaddleOCR

ocr = PaddleOCR(
    use_doc_orientation_classify=True,
    use_doc_unwarping=True,
    use_textline_orientation=True,
)

results = ocr.predict("samples/labels/chinese-label-001.jpg")
for result in results:
    result.print()
    result.save_to_json("output/ocr")
    result.save_to_img("output/ocr")
```

默认配置当前使用 PP-OCRv6 medium。食品包装容易出现旋转、弯曲和倾斜，因此教程先打开三个预处理模块；后续会通过真实数据评估它们的精度收益和耗时，而不是永久写死。

## 8. 如何确认运行的是本地模型

本地推理具有以下特征：

- 代码实例化的是 `PaddleOCR`，不是 `PaddleOCRClient`；
- 不需要 `PADDLEOCR_ACCESS_TOKEN`；
- 首次下载模型后，推理计算发生在本机；
- 关闭网络后，已缓存模型仍应能处理本地图片。

`PaddleOCRClient` 调用的是托管 API，不应和本地推理混淆。当前项目默认采用本地推理，云 API 只保留为将来的可选回退 Provider。

## 9. 项目中的配置方式

正式接入时，不会在 Web 路由里直接实例化模型，而是通过环境变量选择 Provider：

```env
FOOD_LABEL_OCR_PROVIDER=paddle
FOOD_LABEL_OCR_VERSION=PP-OCRv6
FOOD_LABEL_OCR_DEVICE=cpu
FOOD_LABEL_OCR_CACHE_DIR=.paddlex
FOOD_LABEL_OCR_USE_ORIENTATION=true
FOOD_LABEL_OCR_USE_UNWARPING=true
FOOD_LABEL_OCR_USE_TEXTLINE_ORIENTATION=true
FOOD_LABEL_OCR_ALLERGEN_THRESHOLD=0.95
FOOD_LABEL_OCR_GENERAL_THRESHOLD=0.80
```

中国大陆的服务器可另外设置 `PADDLE_PDX_MODEL_SOURCE=bos`，让首次模型下载优先使用 Paddle 官方 BOS。该变量只影响部署时的模型来源，不会发送用户图片到云端；完成下载后，识别仍在本地运行。

这些变量由当前代码在应用启动时读取。它们只应设置在本地 shell、容器编排平台或云端配置管理中，不应保存为 GitHub 中的 `.env` 文件。仓库的 `.gitignore` 会排除 `.env`、`.env.*`、私有标签样本、OCR 输出和本地模型缓存。

Provider 的目标关系为：

```text
Web API
  -> OCRService
    -> OCRProvider 协议
      -> DemoOCRProvider（默认）
      -> PaddleOCRProvider（设置 FOOD_LABEL_OCR_PROVIDER=paddle 后启用）
      -> CloudOCRFallbackProvider（以后可选）
```

模型对象应在应用启动时创建一次并复用，不能每次 HTTP 请求都重新加载，否则会产生严重延迟和内存抖动。

## 10. 可选启用 PP-StructureV3

项目已经提供延迟启用的 `PPStructureNutritionParser`，默认值为 `disabled`，不会加载表格模型。普通 PP-OCRv6 检出营养标示口径后，只有在服务器明确启用时才运行表格结构恢复：

```bash
export FOOD_LABEL_OCR_TABLE_PARSER=ppstructure
export FOOD_LABEL_OCR_TABLE_OCR_VERSION=PP-OCRv5
```

主文字管线与表格管线的 OCR 版本必须分开配置：主管线继续使用 PP-OCRv6；当前 PP-StructureV3 接受 PP-OCRv3、PP-OCRv4 或 PP-OCRv5，项目默认使用 PP-OCRv5。

推荐按以下顺序上线：

1. PP-OCRv6 能稳定返回文字、坐标和置信度；
2. 完成配料表与过敏原字段解析；
3. 建立至少一批人工校对的营养成分表图片；
4. 启用 PP-StructureV3，允许首次运行下载额外的布局与表格模型，并评估结构准确率；
5. 把营养数字、单位、每份口径和 NRV% 分开校验。

PP-StructureV3 的输出仍然只是候选事实。任何低置信度营养数字都不能由 LLM 猜测补全。

当前结构化字段会保留 HTML 恢复出的行列关系，并运行确定性校验：口径缺失、营养素数值缺失、数字字形歧义、负值、单位缺失、NRV% 异常值和重复营养素行。阻断级问题会把该营养表标记为必须人工确认。表格模型的本地缓存和真实评测图片仍不得提交 GitHub。

## 11. Linux GPU 生产环境

未来部署到带 NVIDIA GPU 的 Linux 服务器时，应创建独立容器镜像，并根据服务器 CUDA 版本安装对应的 `paddlepaddle-gpu`。例如官方文档给出的 CUDA 11.8 示例与 macOS CPU 包不同。

不要把以下内容直接从开发机复制到生产环境：

- macOS 的 PaddlePaddle wheel；
- 本机绝对模型缓存路径；
- 开发环境完整 `pip freeze`；
- 用户上传的真实食品图片。

生产镜像应该固定以下版本：

- Python；
- PaddlePaddle GPU 与 CUDA 对应版本；
- PaddleOCR；
- 模型名称或模型文件校验值；
- 项目代码版本。

## 12. 验收清单

完成配置后逐项确认：

- [ ] `python` 来自项目虚拟环境；
- [ ] Python 和系统架构都是 arm64；
- [ ] `paddle.utils.run_check()` 成功；
- [ ] `import paddleocr` 成功；
- [ ] PP-OCRv6 首次模型下载成功；
- [ ] 一张中文配料表能输出文本、坐标和置信度；
- [ ] 英文字母、数字和单位没有被预先丢弃；
- [ ] 现有项目测试仍全部通过；
- [ ] 当前 Web 平台仍明确显示 Demo OCR，直到 Provider 真正接入；
- [ ] 用户图片和 OCR 输出没有被意外提交到 Git。

## 13. 常见问题

### 安装很慢

PaddlePaddle wheel 和模型文件体积较大。先确认下载仍有进度，不要反复中断产生多个残缺环境。国内环境可优先使用官方提供的软件源地址。

### 第一次识别很慢

第一次运行包含模型下载、解压和初始化。应分别记录冷启动时间和模型加载后的单次推理时间。

### Mac 没有调用 GPU

这是预期行为。官方 PaddlePaddle 在 macOS 上提供 CPU 版本；真正的 GPU 性能测试应在 Linux NVIDIA 环境进行。

### OCR 文本看起来正确，为什么还不能直接判断过敏风险

OCR 的平均置信度不能代表高风险词一定正确。`花生`、`乳`、`蛋`、`坚果`以及“含有/可能含有”等字段必须经过单独阈值、词典匹配、原图证据定位和必要的用户确认。

### 英文版是否需要重新换 OCR

不需要。PP-OCRv6 medium 本身支持中文、英文和数字。英文版主要替换法规知识库、术语规范化、过敏原规则和产品检索数据，OCR Provider 合同保持不变。

## 14. 下一阶段

下一次代码里程碑应包括：

1. 增加可选的 OCR 依赖组；
2. 实现延迟加载的 `PaddleOCRProvider`；
3. 从环境变量选择 Demo 或真实 Provider；
4. 把 PaddleOCR 原始行结果映射为项目的统一数据结构；
5. 为模型未安装、首次下载失败和推理异常增加可观察错误；
6. 保持高风险字段进入人工确认路由；
7. 用测试替身验证，不在普通单元测试中下载模型。

## 官方资料

- [PaddleOCR 快速开始](https://www.paddleocr.ai/latest/en/quick_start.html)
- [PP-OCRv6 模型说明](https://www.paddleocr.ai/latest/en/version3.x/algorithm/PP-OCRv6/PP-OCRv6.html)
- [PaddleOCR 安装说明](https://www.paddleocr.ai/main/en/version3.x/installation.html)
- [PaddlePaddle macOS 安装说明](https://www.paddlepaddle.org.cn/documentation/docs/en/install/pip/macos-pip_en.html)
- [PP-StructureV3 使用说明](https://www.paddleocr.ai/main/en/version3.x/pipeline_usage/PP-StructureV3.html)
