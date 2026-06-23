"""素材解析：从上传文件提取纯文本，并按段落切分为 chunk。"""
import io
import re


def extract_text(filename: str, data: bytes) -> str:
    name = (filename or "").lower()
    if name.endswith(".pdf"):
        from pypdf import PdfReader

        reader = PdfReader(io.BytesIO(data))
        return "\n".join(page.extract_text() or "" for page in reader.pages)
    # txt / md / 其他文本
    for enc in ("utf-8", "gbk", "latin-1"):
        try:
            return data.decode(enc)
        except UnicodeDecodeError:
            continue
    return data.decode("utf-8", errors="ignore")


def chunk_text(text: str) -> list[str]:
    """按段落切分：每个段落作为一个 chunk，不跨段合并、不截断段落。

    以空行（一个或多个）分段；若全文没有空行，则退化为按单行分段。
    """
    paragraphs = [p.strip() for p in re.split(r"\n\s*\n", text) if p.strip()]
    # 没有空行时退化为按单行切
    if len(paragraphs) <= 1:
        paragraphs = [p.strip() for p in text.splitlines() if p.strip()]
    return [p for p in paragraphs if p]
