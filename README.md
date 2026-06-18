# MNBVC 数据清洗 - CSDN HTML 转 JSONL 工具

将 CSDN 下载的 `.html` 博文文件转换为 [MNBVC 代码语料](https://github.com/LinnaWang76/githubcode_extractor_mnbvc) `.jsonl` 格式，保留标题、列表、表格、代码块、图片/视频外链等 Markdown 格式。

## 依赖

- Python 3.7+
- beautifulsoup4

```bash
pip install beautifulsoup4
```

## 参数说明

```bash
python csdn_html2jsonl.py <html_file_path>
```

| 参数 | 说明 |
|------|------|
| `html_file_path` | 单个 CSDN `.html` 博文文件的**绝对路径** |

**示例：**

```bash
python csdn_html2jsonl.py "D:/mnbvc/download/.../123456789.html"
```

输出文件与输入文件**同目录、同名**，仅扩展名由 `.html` 替换为 `.jsonl`，统一编码为 **UTF-8**。

## JSONL 输出格式

每行一个 JSON 对象，各字段说明如下：

```json
{
    "来源": "csdn",
    "仓库名": "博文作者的 CSDN 账号",
    "path": "原文链接地址",
    "文件名": "博文 ID.md",
    "ext": "md",
    "size": 1234,
    "原始编码": "utf-8",
    "md5": "abc123def456...",
    "text": "# 标题\n\n正文 Markdown 内容..."
}
```
