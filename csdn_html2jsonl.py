"""
CSDN HTML 博文转 JSONL 工具
============================
功能：将 CSDN 下载的 .html 博文文件转换为 .jsonl 格式。
- 接受单个 .html 文件路径作为参数
- 仅保留 class="blog-content-box" 的内容
- 移除 class="article-bar-top"
- 将 HTML 转换为 Markdown（保留标题、列表、表格、代码块、图片链接等）
- 输出为 .jsonl 文件，保存到输入文件同目录

用法：
    python csdn_html2jsonl.py <html_file_path>
"""

import argparse
import hashlib
import json
import os
import re
import sys
from bs4 import BeautifulSoup, Tag, NavigableString
from urllib.parse import urlparse


def get_md5(text: str) -> str:
    """计算文本的 MD5 值"""
    if text:
        md5 = hashlib.md5()
        md5.update(text.encode('utf-8'))
        return md5.hexdigest().lower()
    return ''


def html_to_markdown(element, list_depth=0, ordered_counters=None) -> str:
    """
    递归将 HTML 元素（BeautifulSoup Tag/NavigableString）转换为 Markdown 文本。

    Args:
        element: BeautifulSoup 的 Tag 或 NavigableString
        list_depth: 当前所在的列表嵌套深度（用于 <li> 内嵌套列表）
        ordered_counters: 有序列表计数器 dict，key 为深度，value 为当前序号

    Returns:
        Markdown 格式字符串
    """
    if ordered_counters is None:
        ordered_counters = {}

    # --- 文本节点 ---
    if isinstance(element, NavigableString):
        text = str(element)
        # 压缩连续空白（但保留单个空格）
        text = re.sub(r'[\t ]+', ' ', text)
        # 转义 Markdown 特殊字符 #，防止被误解析为标题
        text = text.replace('#', '\\#')
        # 去掉首尾空白，但保留有意义的内容
        return text

    if not isinstance(element, Tag):
        return ''

    tag_name = element.name.lower() if element.name else ''

    # --- 需要跳过的元素 ---
    if tag_name in ('svg', 'script', 'style', 'noscript', 'link'):
        return ''

    # --- 排版/结构元素（透传子节点） ---
    if tag_name in ('div', 'span', 'section', 'article', 'header', 'footer',
                     'main', 'nav', 'aside', 'figure', 'figcaption', 'dl', 'dt', 'dd',
                     'details', 'summary', 'abbr', 'cite', 'dfn', 'mark', 'samp',
                     'small', 'sub', 'sup', 'time', 'var', 'wbr', 'bdi', 'bdo',
                     'data', 'ins', 's', 'u', 'q', 'ruby', 'rt', 'rp'):
        return process_children(element, list_depth, ordered_counters)

    # --- 标题 h1-h6 ---
    if re.match(r'^h([1-6])$', tag_name):
        level = int(tag_name[1])
        content = process_children(element, list_depth, ordered_counters).strip()
        return '#' * level + ' ' + content + '\n\n'

    # --- 段落 ---
    if tag_name == 'p':
        content = process_children(element, list_depth, ordered_counters).strip()
        if content:
            return content + '\n\n'
        return ''

    # --- 换行 ---
    if tag_name == 'br':
        return '\n'

    # --- 加粗 ---
    if tag_name in ('strong', 'b'):
        content = process_children(element, list_depth, ordered_counters).strip()
        if content:
            return '**' + content + '**'
        return ''

    # --- 斜体 ---
    if tag_name in ('em', 'i'):
        content = process_children(element, list_depth, ordered_counters).strip()
        if content:
            return '*' + content + '*'
        return ''

    # --- 删除线 ---
    if tag_name in ('del', 'strike'):
        content = process_children(element, list_depth, ordered_counters).strip()
        if content:
            return '~~' + content + '~~'
        return ''

    # --- 行内代码 ---
    if tag_name == 'code':
        # 如果父元素是 pre，则跳过（由 pre 处理）
        parent = element.parent
        if parent and hasattr(parent, 'name') and parent.name == 'pre':
            return element.get_text()  # 返回原始文本，由 pre 处理
        content = element.get_text().strip()
        if content:
            # 用反引号包裹，处理内部的反引号
            if '`' in content:
                # 用双反引号包裹
                return '`` ' + content + ' ``'
            return '`' + content + '`'
        return ''

    # --- 代码块 ---
    if tag_name == 'pre':
        code_tag = element.find('code')
        if code_tag:
            code_text = code_tag.get_text()
            # 尝试获取语言
            lang = ''
            code_classes = code_tag.get('class', [])
            if code_classes:
                for cls in code_classes:
                    if cls.startswith('language-'):
                        lang = cls.replace('language-', '')
                        break
                    elif cls.startswith('lang-'):
                        lang = cls.replace('lang-', '')
                        break

            # 去掉末尾多余的空白行
            code_text = code_text.rstrip()
            return '```' + lang + '\n' + code_text + '\n```\n\n'
        else:
            # <pre> 内没有 <code>
            code_text = element.get_text().rstrip()
            return '```\n' + code_text + '\n```\n\n'

    # --- 链接 ---
    if tag_name == 'a':
        href = element.get('href', '')
        content = process_children(element, list_depth, ordered_counters).strip()
        if not content:
            content = href
        if href:
            return '[' + content + '](' + href + ')'
        return content

    # --- 图片 ---
    if tag_name == 'img':
        src = element.get('src', '')
        alt = element.get('alt', '')
        if src:
            return '![' + alt + '](' + src + ')'
        return ''

    # --- 水平线 ---
    if tag_name == 'hr':
        return '---\n\n'

    # --- 引用块 ---
    if tag_name == 'blockquote':
        content = process_children(element, list_depth, ordered_counters).strip()
        lines = content.split('\n')
        quoted = '\n'.join('> ' + line if line.strip() else '>' for line in lines)
        return quoted + '\n\n'

    # --- 无序列表 ---
    if tag_name == 'ul':
        return process_children(element, list_depth, ordered_counters)

    # --- 有序列表 ---
    if tag_name == 'ol':
        ordered_counters[list_depth] = 0
        result = process_children(element, list_depth + 1, ordered_counters)
        return result

    # --- 列表项 ---
    if tag_name == 'li':
        # 分离直接子节点的文本和内嵌列表
        inline_parts = []
        nested_lists = []

        for child in element.children:
            if isinstance(child, Tag) and child.name in ('ul', 'ol'):
                nested_lists.append(child)
            else:
                inline_parts.append(child)

        # 处理内联内容
        inline_content = ''
        for part in inline_parts:
            inline_content += html_to_markdown(part, list_depth, ordered_counters)
        inline_content = inline_content.strip()

        # 构建标记符号
        parent_name = element.parent.name if element.parent and hasattr(element.parent, 'name') else 'ul'
        if parent_name == 'ol':
            if list_depth - 1 not in ordered_counters:
                ordered_counters[list_depth - 1] = 1
            else:
                ordered_counters[list_depth - 1] += 1
            marker = str(ordered_counters[list_depth - 1]) + '. '
        else:
            marker = '- '

        indent = '  ' * (list_depth - 1)
        result = indent + marker + inline_content + '\n'

        # 处理嵌套列表
        for nl in nested_lists:
            nested_md = process_children(nl, list_depth + 1, ordered_counters)
            if nested_md.strip():
                result += nested_md

        return result

    # --- 表格 ---
    if tag_name == 'table':
        return convert_table(element)

    # --- 表格行（由 table 处理时跳过） ---
    if tag_name in ('thead', 'tbody', 'tfoot', 'tr', 'th', 'td', 'col', 'colgroup', 'caption'):
        return process_children(element, list_depth, ordered_counters)

    # --- 预格式化文本 ---
    if tag_name in ('kbd', 'tt'):
        content = element.get_text().strip()
        return '`' + content + '`'

    # --- 视频/嵌入媒体（保留链接） ---
    if tag_name in ('video', 'audio', 'embed', 'object'):
        src = element.get('src', '') or element.get('data', '')
        if src:
            return '\n[' + tag_name + '](' + src + ')\n'
        # 尝试从子元素 source 获取
        source = element.find('source')
        if source and source.get('src'):
            return '\n[' + tag_name + '](' + source.get('src') + ')\n'
        return ''

    # --- iframe（保留链接） ---
    if tag_name == 'iframe':
        src = element.get('src', '')
        if src:
            return '\n[' + tag_name + '](' + src + ')\n'
        return ''

    # --- 其他未知元素：透传子节点 ---
    return process_children(element, list_depth, ordered_counters)


def process_children(element, list_depth=0, ordered_counters=None) -> str:
    """遍历子节点并拼接转换结果"""
    result = []
    for child in element.children:
        result.append(html_to_markdown(child, list_depth, ordered_counters))
    return ''.join(result)


def convert_table(table_tag) -> str:
    """
    将 HTML <table> 转换为 Markdown 表格。

    处理 thead/tbody/tfoot 结构，支持跨行跨列的基本情况。
    """
    rows = []

    # 收集所有行
    thead = table_tag.find('thead')
    if thead:
        for tr in thead.find_all('tr', recursive=False):
            rows.append(tr)

    tbody = table_tag.find('tbody')
    if tbody:
        for tr in tbody.find_all('tr', recursive=False):
            rows.append(tr)
    else:
        # 没有 tbody，直接找 tr
        for tr in table_tag.find_all('tr', recursive=False):
            rows.append(tr)

    tfoot = table_tag.find('tfoot')
    if tfoot:
        for tr in tfoot.find_all('tr', recursive=False):
            rows.append(tr)

    if not rows:
        return ''

    # 将每一行转为单元格列表
    table_data = []
    max_cols = 0

    for tr in rows:
        cells = []
        for cell in tr.find_all(['th', 'td'], recursive=False):
            # 获取单元格文本（去除多余空白）
            cell_text = process_children(cell).strip()
            # 将内部换行替换为空格，保持单元格内容在一行
            cell_text = cell_text.replace('\n', ' ').replace('|', '\\|')
            cells.append(cell_text)
        table_data.append(cells)
        max_cols = max(max_cols, len(cells))

    if max_cols == 0:
        return ''

    # 补齐列数
    for row in table_data:
        while len(row) < max_cols:
            row.append('')

    # 构建 Markdown 表格
    lines = []

    # 表头行
    header = '| ' + ' | '.join(table_data[0]) + ' |'
    lines.append(header)

    # 分隔行
    separator = '| ' + ' | '.join(['---'] * max_cols) + ' |'
    lines.append(separator)

    # 数据行
    for row in table_data[1:]:
        line = '| ' + ' | '.join(row) + ' |'
        lines.append(line)

    return '\n'.join(lines) + '\n\n'


def extract_content_from_html(html_path: str) -> tuple:
    """
    从 CSDN HTML 文件中提取内容和元数据。

    Args:
        html_path: HTML 文件路径

    Returns:
        (md_text, meta_dict) 或 (None, None) 如果提取失败
    """
    # 读取 HTML 文件（先尝试 utf-8，失败则用其他编码）
    for encoding in ['utf-8', 'gbk', 'gb2312', 'latin-1']:
        try:
            with open(html_path, 'r', encoding=encoding) as f:
                html_content = f.read()
            break
        except (UnicodeDecodeError, UnicodeError):
            continue
    else:
        print(f"[ERROR] 无法读取文件: {html_path}")
        return None, None

    soup = BeautifulSoup(html_content, 'html.parser')

    # --- 提取元数据 ---

    # 原始编码
    charset_meta = soup.find('meta', charset=True)
    orig_encoding = charset_meta.get('charset', 'utf-8') if charset_meta else 'utf-8'

    # 从 head 中的 meta 获取 charset
    meta_charset = soup.find('meta', attrs={'http-equiv': re.compile(r'content-type', re.I)})
    if meta_charset and not charset_meta:
        content = meta_charset.get('content', '')
        m = re.search(r'charset=([^\s;]+)', content)
        if m:
            orig_encoding = m.group(1)

    # 获取 canonical URL
    canonical_link = soup.find('link', rel='canonical')
    canonical_href = ''
    repo_name = ''
    file_name_md = ''

    if canonical_link:
        canonical_href = canonical_link.get('href', '')

    # 从 canonical URL 提取仓库名和文件名
    # URL 格式: https://blog.csdn.net/<repo_name>/article/details/<article_id>
    if canonical_href:
        # 仓库名：blog.csdn.net/ 之后到下一个 / 之间的部分
        m = re.search(r'blog\.csdn\.net/([^/]+)', canonical_href)
        if m:
            repo_name = m.group(1)

        # 文件名：URL 路径最后一段数字 + .md
        parsed = urlparse(canonical_href)
        path_parts = [p for p in parsed.path.strip('/').split('/') if p]
        if path_parts:
            last_part = path_parts[-1].split('?')[0]
            if last_part.isdigit():
                file_name_md = last_part + '.md'
            else:
                file_name_md = last_part + '.md'

    # --- 提取 blog-content-box ---
    blog_content_box = soup.find('div', class_='blog-content-box')
    if not blog_content_box:
        print(f"[ERROR] 未找到 class='blog-content-box' 的元素: {html_path}")
        return None, None

    # 复制一份用于处理
    content_div = BeautifulSoup(str(blog_content_box), 'html.parser')

    # --- 移除 article-bar-top ---
    for bar_top in content_div.find_all('div', class_='article-bar-top'):
        bar_top.decompose()

    # --- 移除不需要的元素（目录弹窗、VIP 弹窗等） ---
    for unwanted_class in [
        'directory-boxshadow-dialog',
        'vip-limited-time-offer-box-new',
        'more-toolbox-new',
        'runner-box',
    ]:
        for el in content_div.find_all('div', class_=unwanted_class):
            el.decompose()

    # --- 移除 <script> 标签 ---
    for script in content_div.find_all('script'):
        script.decompose()

    # --- 移除空的或仅含空白的 div ---
    # 这一步对 content_views 内 dataFrame 间的空 div 很关键
    empty_divs = []
    for div in content_div.find_all('div'):
        if div.get_text(strip=True) == '' and not div.find('img'):
            empty_divs.append(div)
    for div in empty_divs:
        div.decompose()

    # --- 转换为 Markdown ---
    md_text = html_to_markdown(content_div)

    # --- 后处理：清理多余的空白行 ---
    # 将 3 个以上连续换行压缩为 2 个
    md_text = re.sub(r'\n{4,}', '\n\n\n', md_text)
    # 去掉开头和结尾的多余空白
    md_text = md_text.strip() + '\n'

    meta = {
        'orig_encoding': orig_encoding,
        'canonical_href': canonical_href,
        'repo_name': repo_name,
        'file_name_md': file_name_md,
    }

    return md_text, meta


def build_jsonl_record(md_text: str, meta: dict) -> dict:
    """
    根据 Markdown 文本和元数据构建 JSONL 记录。

    Args:
        md_text: Markdown 文本
        meta: 元数据字典

    Returns:
        JSONL 记录字典
    """
    md5 = get_md5(md_text)
    # size 为 md 文本的 UTF-8 字节数
    size = len(md_text.encode('utf-8'))

    record = {
        '来源': 'csdn',
        '仓库名': meta['repo_name'],
        'path': meta['canonical_href'],
        '文件名': meta['file_name_md'],
        'ext': 'md',
        'size': size,
        '原始编码': meta['orig_encoding'],
        'md5': md5,
        'text': md_text,
    }

    return record


def process_html_file(html_path: str) -> bool:
    """
    处理单个 HTML 文件：转换为 Markdown 并输出 JSONL。

    Args:
        html_path: HTML 文件路径

    Returns:
        成功返回 True，失败返回 False
    """
    if not os.path.isfile(html_path):
        print(f"[ERROR] 文件不存在: {html_path}")
        return False

    if not html_path.lower().endswith('.html'):
        print(f"[ERROR] 不是 .html 文件: {html_path}")
        return False

    print(f"[INFO] 处理文件: {html_path}")

    # 提取内容
    md_text, meta = extract_content_from_html(html_path)
    if md_text is None:
        return False

    # 构建记录
    record = build_jsonl_record(md_text, meta)

    # 输出路径：同目录，.html 替换为 .jsonl
    output_path = re.sub(r'\.html$', '.jsonl', html_path, flags=re.IGNORECASE)
    # 如果输出路径和输入一样（没替换成功），加 .jsonl
    if output_path == html_path:
        output_path = html_path + '.jsonl'

    with open(output_path, 'w', encoding='utf-8') as f:
        f.write(json.dumps(record, ensure_ascii=False) + '\n')

    print(f"[INFO] 输出文件: {output_path}")
    print(f"[INFO] MD5: {record['md5']}, Size: {record['size']} bytes")
    return True


def main():
    parser = argparse.ArgumentParser(
        description='CSDN HTML 博文转 JSONL 工具',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog='''
示例:
    python csdn_html2jsonl.py "D:/mnbvc/download/csdn_html_vip1/html_vip/e1/0d/tutu6169/129647815.html"
        '''
    )
    parser.add_argument('html_file', type=str, help='单个 HTML 文件路径')
    args = parser.parse_args()

    success = process_html_file(args.html_file)
    sys.exit(0 if success else 1)


if __name__ == '__main__':
    main()
