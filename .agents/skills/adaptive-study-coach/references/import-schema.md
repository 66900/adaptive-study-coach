# 导入规范

## 统一字段

每条学习内容使用以下结构：

```json
{
  "subject": "英语",
  "topic": "今日单词",
  "type": "term",
  "prompt": "meticulous",
  "answer": "一丝不苟的；非常仔细的",
  "aliases": ["细致的", "谨慎的"],
  "tags": ["vocabulary"],
  "source": "chat",
  "content_confidence": 0.95,
  "ocr_confidence": null,
  "content_verified": false
}
```

- `subject`：学科，缺省为“英语”。
- `topic`：章节或知识点分组，缺省为“未分类”。
- `type`：`term`、`concept`、`qa`、`cloze`、`problem`、`procedure` 之一。
- `prompt`：题面或术语，不得为空。
- `answer`：标准答案；缺失时进入待确认区。
- `aliases`：可接受的等价答案数组。
- `tags`：标签数组。
- `source`：`chat`、原文件名、`vision` 或 `model-assisted`。
- `content_confidence`：0 到 1，表示题面与答案本身可靠程度；低于 0.75 时进入待确认区。
- `ocr_confidence`：0 到 1，仅表示 OCR 字符识别清晰度，不代表知识内容正确。
- `content_verified`：OCR 来源必须由人确认后设为 `true`，否则始终进入待确认区。
- `confidence`：旧版兼容字段。非 OCR 内容会映射为 `content_confidence`；新文件不要继续使用。

JSON 文件可为对象数组，也可用顶层 `items` 数组。CSV/Excel 可使用英文字段名，也可使用
“学科、主题、类型、问题、答案、同义答案、标签、来源、置信度”。两列且没有表头时按
“问题、答案”读取。

## 图片和扫描件

先逐项抄录可见内容，再归一化为 JSON。将 OCR 引擎分数写入 `ocr_confidence`，不要据此
提高 `content_confidence`。未经人工确认时保持 `content_verified: false` 并进入待确认区。
模糊字符不能猜测。扫描 PDF 没有可提取文字时，按图片处理。

## 学科题型

- 英语：先 `英文 → 中文含义`，之后可用反向拼写或语境填空作为变式。
- 数学/物理：概念、公式适用条件、代入计算和步骤说明分开建条目。
- 生物/化学：名词定义、机制、因果关系、实验现象和步骤分别建条目。
- 其他学科：一个条目只测试一个清晰、可判定的知识点。
