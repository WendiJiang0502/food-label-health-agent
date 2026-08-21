# 真实标签数据目录

将经过允许内部评测的标签图片放在本地数据目录，并在 `manifest.json` 中登记。图片和可能包含原始标签文字的文件默认不提交 Git。

推荐结构：

```text
evaluation/real_labels/
├── manifest.json
├── images/          # 本地图片，已被 .gitignore 排除
└── annotations/     # 人工确认事实，按 label_id 命名
```

先复制 `manifest.template.json` 为 `manifest.json`，再按规范填写。
