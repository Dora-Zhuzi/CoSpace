"""素材解析：从上传文件提取纯文本，并按段落切分为 chunk。"""
import io
import re


def extract_text(filename: str, data: bytes) -> str:
    name = (filename or "").lower()
    if name.endswith(".pdf"):
        from pypdf import PdfReader

        reader = PdfReader(io.BytesIO(data))
        return "\n".join(page.extract_text() or "" for page in reader.pages)
    if name.endswith(".docx"):
        from docx import Document

        doc = Document(io.BytesIO(data))
        return "\n\n".join(p.text for p in doc.paragraphs if p.text.strip())
    # txt / md / 其他文本
    for enc in ("utf-8", "gbk", "latin-1"):
        try:
            return data.decode(enc)
        except UnicodeDecodeError:
            continue
    return data.decode("utf-8", errors="ignore")


MIN_CHUNK_CHARS = 300  # chunk 下限：过短的相邻段落合并到此长度


def split_paragraphs(text: str) -> list[str]:
    """按空行分段；没有空行时退化为按单行分段。"""
    paragraphs = [p.strip() for p in re.split(r"\n\s*\n", text) if p.strip()]
    if len(paragraphs) <= 1:
        paragraphs = [p.strip() for p in text.splitlines() if p.strip()]
    return paragraphs


def chunk_labeled(paragraphs: list[str], labels: list[str]) -> list[dict]:
    """把带类型标签的段落合并成 chunk：

    - 相邻**同类型**段落合并，直到达到 MIN_CHUNK_CHARS；
    - **类型一变即断块**（即使未达下限），保证每个 chunk 类型纯净；
    - 不切断单个段落。
    返回 [{"content": str, "type": str}, ...]。
    """
    chunks: list[dict] = []
    buf = ""
    buf_type: str | None = None
    for para, typ in zip(paragraphs, labels):
        if buf and typ != buf_type:
            chunks.append({"content": buf, "type": buf_type})
            buf = ""
        buf = f"{buf}\n\n{para}" if buf else para
        buf_type = typ
        if len(buf) >= MIN_CHUNK_CHARS:
            chunks.append({"content": buf, "type": buf_type})
            buf = ""
            buf_type = None
    if buf:
        chunks.append({"content": buf, "type": buf_type or "其他"})
    return chunks


def chunk_text(text: str) -> list[str]:
    """按段落切分，并把过短的相邻段落合并到 MIN_CHUNK_CHARS 下限。

    - 以空行（一个或多个）分段；没有空行时退化为按单行分段。
    - 不切断单个段落：达到下限即成块（长段落自成一块）。
    - 目的：避免转写稿等"每句一段"产生大量碎块，既拖慢入库又不利于挂载。
    """
    paragraphs = [p.strip() for p in re.split(r"\n\s*\n", text) if p.strip()]
    # 没有空行时退化为按单行切
    if len(paragraphs) <= 1:
        paragraphs = [p.strip() for p in text.splitlines() if p.strip()]

    chunks: list[str] = []
    buf = ""
    for para in paragraphs:
        buf = f"{buf}\n\n{para}" if buf else para
        if len(buf) >= MIN_CHUNK_CHARS:
            chunks.append(buf)
            buf = ""
    if buf:
        chunks.append(buf)
    return chunks
