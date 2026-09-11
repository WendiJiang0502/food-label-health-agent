# OCR 私有评测集

真实食品标签图片、逐字标注和评测报告均属于本地私有数据，不提交到 GitHub。
仓库只保存评测程序与标注契约。

## 本地目录

把图片放在仓库外的任意目录。若要计算有监督指标，可在图片旁添加同名 sidecar：

```text
private-labels/
├── sample-01.jpg
└── sample-01.jpg.json
```

标注文件示例：

```json
{
  "fields": {
    "ingredients": "小麦粉、白砂糖、食用盐",
    "allergen_statement": "本产品含有小麦"
  },
  "ingredient_tokens": ["小麦粉", "白砂糖", "食用盐"],
  "allergens": ["小麦"]
}
```

`fields` 用于逐字段字符错误率（CER），`allergens` 用于过敏原词项召回率。标注字段中的数字用于计算数字 token 精确率、召回率和 F1；`nutrition_table` 还会计算营养素—数值—单位的对应准确率。没有 sidecar 时，仍会统计图片阻断率、字段发现率和人工确认率。

`ingredient_tokens`、`allergens` 与 `nutrition_table` 中的营养素—数值—单位关系共同构成关键事实。报告中的 `critical_fact_recall` 采用微平均：正确关键事实数除以全部已标注关键事实数。它不能替代逐字 CER，也不能绕过人工确认或过敏安全门。

## 数据集角色

用于调参或修复回归的图片必须登记为 `frozen_development`，不得计入发布门禁。
发布评测只统计同时满足以下条件的标注：

- `annotation_status` 为 `double_reviewed_gold`；
- `dataset_role` 为 `blind_test`；
- 未参与当前实现的调参或规则设计。

首批 9 张用户单人审核图片登记在 `devset_tencent_2026-09-11.json`，只用于开发回归。

## 运行

服务端配置 PaddleOCR 后运行：

```bash
food-label-ocr-eval /path/to/private-labels --output /tmp/ocr-report.json
```

输出只含图片内容哈希的前 12 位，不含原文件名和 OCR 全文。报告也应保存在仓库外。

云端 Provider 遇到账号未开通、凭证无效、权限不足或资源包耗尽等不可重试错误时，评测器会在第一张失败图片后立即停止，避免重复请求。网络限流或临时内部错误会标记为可重试错误，不会被误计为识别准确率。
