from io import BytesIO
from zipfile import ZipFile
from pypdf import PdfReader
from docx import Document

MAX_UPLOAD = 2 * 1024 * 1024


def parse_resume(filename: str, data: bytes):
    if not data or len(data) > MAX_UPLOAD:
        raise ValueError("Upload must be between 1 byte and 2 MB")
    suffix = filename.lower().rsplit(".", 1)[-1]
    if suffix in {"txt", "md"}:
        text = data.decode("utf-8-sig")
    elif suffix == "pdf":
        reader = PdfReader(BytesIO(data))
        if reader.is_encrypted or len(reader.pages) > 50:
            raise ValueError("Encrypted or over-50-page PDF is unsupported")
        text = "\n".join(p.extract_text() or "" for p in reader.pages)
    elif suffix == "docx":
        with ZipFile(BytesIO(data)) as z:
            if sum(i.file_size for i in z.infolist()) > 10 * 1024 * 1024:
                raise ValueError("Expanded document exceeds 10 MB")
        doc = Document(BytesIO(data))
        text = "\n".join(
            [p.text for p in doc.paragraphs]
            + [
                " | ".join(c.text for c in row.cells)
                for t in doc.tables
                for row in t.rows
            ]
        )
    else:
        raise ValueError("Supported formats: UTF-8 Markdown/text, text PDF, DOCX")
    if not text.strip() or len(text) > 100000 or "\x00" in text:
        raise ValueError("Resume must contain readable text; scanned PDFs need OCR")
    return text.strip()
