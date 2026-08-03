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
  "allergens": ["小麦"]
}
```

`fields` 用于逐字段字符错误率（CER），`allergens` 用于过敏原词项召回率；标注字段中的数字还会用于数字 token 准确率。没有 sidecar 时，仍会统计图片阻断率、字段发现率和人工确认率。

## 运行

服务端配置 PaddleOCR 后运行：

```bash
food-label-ocr-eval /path/to/private-labels --output /tmp/ocr-report.json
```

输出只含图片内容哈希的前 12 位，不含原文件名和 OCR 全文。报告也应保存在仓库外。

