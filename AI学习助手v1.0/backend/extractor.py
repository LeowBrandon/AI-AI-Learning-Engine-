"""把各种格式的文件读成纯文本，并切成片段。

纯函数，不依赖 Flask 与数据库，方便单独测试。

**只用标准库 + pypdf**：
.docx / .pptx 本质就是 ZIP 里装 XML，用 zipfile + ElementTree 直接读，
不引 python-docx / python-pptx。那两个库依赖 lxml，而 lxml 带编译好的 DLL，
在路径较长的项目里会报「DLL load failed ... filename or extension is too long」
（Windows 260 字符上限，lxml 内部还要再加载 libxml2 等，一起就越界了）。
纯 Python 的实现没有这个限制。
"""

import re
import zipfile
from pathlib import Path
from xml.etree import ElementTree

from pypdf import PdfReader


class ExtractError(RuntimeError):
    """无法从文件里读出文字。消息会直接展示给用户。"""


# 直接按文本读的后缀
PLAIN_SUFFIXES = {'.md', '.markdown', '.txt'}

# 中文文本文件常见的编码，按命中率排序
TEXT_ENCODINGS = ('utf-8-sig', 'utf-8', 'gb18030', 'utf-16')

# OOXML 命名空间
W_NS = '{http://schemas.openxmlformats.org/wordprocessingml/2006/main}'
A_NS = '{http://schemas.openxmlformats.org/drawingml/2006/main}'

SLIDE_NAME = re.compile(r'^ppt/slides/slide(\d+)\.xml$')


def extract_text(file_path, file_type):
    """按后缀分派到对应的解析器，返回纯文本。"""
    ext = '.' + (file_type or '').lower()

    if ext in PLAIN_SUFFIXES:
        return _read_plain(file_path)
    if ext == '.pdf':
        return _read_pdf(file_path)
    if ext == '.pptx':
        return _read_pptx(file_path)
    if ext == '.docx':
        return _read_docx(file_path)

    # 旧版二进制格式，Python 生态里没有可靠的开源解析器
    if ext == '.doc':
        raise ExtractError('旧版 .doc 无法解析，请用 Word 另存为 .docx 后重新上传')
    if ext == '.ppt':
        raise ExtractError('旧版 .ppt 无法解析，请用 PowerPoint 另存为 .pptx 后重新上传')

    raise ExtractError('不支持的文件类型：%s' % (file_type or '未知'))


def split_chunks(text, size=1200):
    """按空行分段，再把段落攒到约 size 个字符一片。

    不用向量检索，切片只是为了分块存储、以及拼接提示词时按上限截断。
    """
    paragraphs = [p.strip() for p in re.split(r'\n\s*\n', text) if p.strip()]

    chunks = []
    buffer = ''

    for para in paragraphs:
        if len(para) > size:
            # 单段就超长（比如没有空行的整篇 PDF），先冲掉手上的，再硬切
            if buffer:
                chunks.append(buffer)
                buffer = ''
            for start in range(0, len(para), size):
                chunks.append(para[start:start + size])
        elif buffer and len(buffer) + len(para) + 2 > size:
            chunks.append(buffer)
            buffer = para
        else:
            buffer = (buffer + '\n\n' + para) if buffer else para

    if buffer:
        chunks.append(buffer)

    return chunks


# ---------- 各格式解析 ----------

def _read_plain(path):
    """TXT / Markdown。中文文件可能是 GBK，逐个编码试。"""
    data = Path(path).read_bytes()

    for encoding in TEXT_ENCODINGS:
        try:
            return data.decode(encoding)
        except (UnicodeDecodeError, LookupError):
            continue

    # 全部失败也要给出内容，而不是整个上传失败
    return data.decode('utf-8', errors='replace')


def _read_pdf(path):
    try:
        reader = PdfReader(str(path))
    except Exception as exc:
        raise ExtractError('PDF 打不开，文件可能已损坏：%s' % exc) from exc

    if reader.is_encrypted:
        try:
            reader.decrypt('')
        except Exception as exc:
            raise ExtractError('PDF 有密码保护，无法读取文字') from exc

    pages = []
    for page in reader.pages:
        try:
            pages.append(page.extract_text() or '')
        except Exception:
            # 单页解析失败不影响其它页
            pages.append('')

    return '\n\n'.join(pages)


def _read_pptx(path):
    """PPTX：ZIP 里的 ppt/slides/slideN.xml，文字在 <a:t> 里。

    按文件名里的数字排序，对绝大多数文件来说与实际放映顺序一致
    （严格来说顺序记录在 presentation.xml 的 sldIdLst 里，这里不做解析）。
    """
    try:
        with zipfile.ZipFile(str(path)) as archive:
            slides = sorted(
                (int(matched.group(1)), name)
                for name in archive.namelist()
                for matched in [SLIDE_NAME.match(name)]
                if matched
            )

            blocks = []
            for index, (_number, name) in enumerate(slides, start=1):
                try:
                    root = ElementTree.fromstring(archive.read(name))
                except ElementTree.ParseError:
                    continue

                lines = []
                for paragraph in root.iter(A_NS + 'p'):
                    text = ''.join(
                        node.text or '' for node in paragraph.iter(A_NS + 't')).strip()
                    if text:
                        lines.append(text)

                if lines:
                    blocks.append('【第 %d 页】\n%s' % (index, '\n'.join(lines)))
    except (zipfile.BadZipFile, OSError) as exc:
        raise ExtractError('PPT 打不开，文件可能已损坏：%s' % exc) from exc

    return '\n\n'.join(blocks)


def _read_docx(path):
    """DOCX：ZIP 里的 word/document.xml，正文是 <w:p>，表格是 <w:tbl>。"""
    try:
        with zipfile.ZipFile(str(path)) as archive:
            xml = archive.read('word/document.xml')
    except (zipfile.BadZipFile, KeyError, OSError) as exc:
        raise ExtractError('Word 打不开，文件可能已损坏：%s' % exc) from exc

    try:
        root = ElementTree.fromstring(xml)
    except ElementTree.ParseError as exc:
        raise ExtractError('Word 内容解析失败：%s' % exc) from exc

    body = root.find(W_NS + 'body')
    if body is None:
        return ''

    blocks = []
    for element in body:
        if element.tag == W_NS + 'p':
            text = _docx_paragraph_text(element)
            if text:
                blocks.append(text)

        elif element.tag == W_NS + 'tbl':
            for row in element.findall(W_NS + 'tr'):
                cells = [
                    ' '.join(_docx_paragraph_text(p) for p in cell.findall(W_NS + 'p')).strip()
                    for cell in row.findall(W_NS + 'tc')
                ]
                if any(cells):
                    blocks.append(' | '.join(cells))

    return '\n\n'.join(blocks)


def _docx_paragraph_text(paragraph):
    """把一个 <w:p> 里的文字按顺序拼起来。制表符与换行补成空格。"""
    parts = []
    for node in paragraph.iter():
        if node.tag == W_NS + 't':
            parts.append(node.text or '')
        elif node.tag in (W_NS + 'tab', W_NS + 'br'):
            parts.append(' ')
    return ''.join(parts).strip()
