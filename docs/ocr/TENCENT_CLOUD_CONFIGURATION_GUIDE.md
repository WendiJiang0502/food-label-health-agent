# 腾讯云 OCR 配置与 Agent 接入教程

## 1. 这层在系统中的职责

腾讯云 OCR 只负责从食品包装图片中取得可追溯的文字与版面证据，不负责解释健康性，也不直接判断过敏风险。

```text
图片
  -> GeneralAccurateOCR：文字、置信度、原图坐标
  -> 确定性字段定位：配料、过敏原提示、营养口径、包装声称
  -> RecognizeTableAccurateOCR：营养表单元格（仅在检测到营养内容时调用）
  -> OCR 完整性与污染检查
  -> 用户确认
  -> Agent 配料规范化、过敏原规则、官方标准 RAG
```

OCR 结果是证据，不是健康结论。LLM 不允许补写未识别文字，也不能绕过人工确认和过敏原安全门。

## 2. 凭证安全

使用仅开启“编程访问”的 CAM 子用户，并关联最小权限策略 `QcloudOCRReadSelfUinUsage`。不要使用主账号密钥，不要将密钥放入前端、聊天、截图、GitHub 或项目内的真实 `.env` 文件。

腾讯云官方 SDK 默认凭证文件：

```text
~/.tencentcloud/credentials
```

格式：

```ini
[default]
secret_id = 真实 SecretId
secret_key = 真实 SecretKey
```

文件权限应为 `600`：

```bash
chmod 600 ~/.tencentcloud/credentials
```

SDK 会优先读取 `TENCENTCLOUD_SECRET_ID` 和 `TENCENTCLOUD_SECRET_KEY` 环境变量，其次读取上述凭证文件。生产环境应使用部署平台的 Secret Manager；最终用户不配置 OCR 密钥。

## 3. 安装与启动

```bash
python3 -m pip install -e '.[cloud-ocr,dev]'
export FOOD_LABEL_OCR_PROVIDER=tencent
export FOOD_LABEL_TENCENT_REGION=ap-guangzhou
export FOOD_LABEL_TENCENT_TABLE_ENABLED=true
export FOOD_LABEL_TENCENT_TABLE_NEW_MODEL=false
food-label-platform
```

配置项：

| 变量 | 默认值 | 作用 |
|---|---:|---|
| `FOOD_LABEL_OCR_PROVIDER` | `demo` | 设为 `tencent` 才启用腾讯云 |
| `FOOD_LABEL_TENCENT_REGION` | `ap-guangzhou` | SDK 请求地域 |
| `FOOD_LABEL_TENCENT_TABLE_ENABLED` | `true` | 是否在检测到营养内容后调用表格 V3 |
| `FOOD_LABEL_TENCENT_TABLE_NEW_MODEL` | `false` | 新模型复杂表格效果更好，但耗时更长；默认模型支持坐标返回 |

## 4. Provider 内部设计

`TencentCloudOCRProvider` 实现与本地 Paddle 相同的 `OCRProvider` 协议。上层 `OCRService`、LangGraph 状态和 MCP 合同不会依赖腾讯云 SDK 类型。

主要转换规则：

1. 图片只在内存中做 Base64 编码并发送给 API；代码不会打印或缓存 Base64。
2. `GeneralAccurateOCR.TextDetections` 转成统一 `OCRLine`。
3. 腾讯云 0–100 置信度归一化到系统的 0–1。
4. 原图四点坐标归一化到 0–1，供网页在任意显示尺寸下定位证据。
5. 配料必须找到锚定标题，如“配料”“配料表”“原料”；标题文字本身会被移除。
6. 只有检测到“营养成分”或至少两个核心营养素时才调用表格 API。
7. 表格单元格按 `RowTl/ColTl` 恢复行列，再运行营养数值、单位、重复行和核心字段完整性校验。
8. 配料和营养表始终需要用户核对；云服务置信度不能替代安全确认。

## 5. 隐私边界

启用腾讯云 Provider 后，图片会离开当前服务器并发送到腾讯云 OCR。网页必须明确显示“图片发送至腾讯云处理，本平台不保存原图”，不能继续声称为纯本地处理。

当前应用级缓存只保存短期结构化 OCR 结果，以图片内容哈希作为键；不保存原图，也不写入 Git。正式上线前仍需根据腾讯云服务条款、隐私政策和产品法域完成隐私告知、用户同意、数据保留和跨境评估。

## 6. 验证清单

- [ ] 凭证文件存在且权限为 `-rw-------`；
- [ ] `/api/health` 返回 `remote_processing: true`；
- [ ] 页面状态显示“腾讯云 OCR”；
- [ ] 页面披露图片会发送至腾讯云；
- [ ] 配料字段不包含“配料”标题；
- [ ] 营养表恢复营养素、数值、单位和口径；
- [ ] 低置信度或字段不完整时进入人工确认；
- [ ] 私有样本、响应原文和密钥没有进入 Git；
- [ ] 使用量、延迟、错误码和降级策略纳入生产监控。
