from __future__ import annotations

from html import unescape
from io import BytesIO
from pathlib import Path
import re
import zipfile
from xml.etree import ElementTree


class DocumentExtractionError(ValueError):
    pass


def extract_text_from_upload(filename: str, content: bytes) -> str:
    extension = Path(filename).suffix.lower()
    if extension in {".txt", ".md", ".csv"}:
        return _decode_text(content)
    if extension == ".docx":
        return _extract_docx_text(content)
    if extension == ".pdf":
        return _extract_pdf_text(content)
    raise DocumentExtractionError(f"Unsupported context document extension: {extension or 'none'}")


def _decode_text(content: bytes) -> str:
    for encoding in ("utf-8-sig", "utf-8", "cp1252", "latin-1"):
        try:
            return content.decode(encoding)
        except UnicodeDecodeError:
            continue
    return content.decode("utf-8", errors="replace")


def _extract_docx_text(content: bytes) -> str:
    try:
        with zipfile.ZipFile(BytesIO(content)) as archive:
            document_xml = archive.read("word/document.xml")
    except (KeyError, zipfile.BadZipFile) as exc:
        raise DocumentExtractionError("The uploaded DOCX file could not be read.") from exc

    try:
        root = ElementTree.fromstring(document_xml)
    except ElementTree.ParseError as exc:
        raise DocumentExtractionError("The uploaded DOCX file has invalid document XML.") from exc

    namespace = {"w": "http://schemas.openxmlformats.org/wordprocessingml/2006/main"}
    paragraphs: list[str] = []
    for paragraph in root.findall(".//w:p", namespace):
        parts = [node.text or "" for node in paragraph.findall(".//w:t", namespace)]
        text = "".join(parts).strip()
        if text:
            paragraphs.append(text)
    return "\n".join(paragraphs)


def _extract_pdf_text(content: bytes) -> str:
    decoded = content.decode("latin-1", errors="ignore")
    matches = re.findall(r"\((.*?)\)\s*Tj", decoded, flags=re.DOTALL)
    if not matches:
        raise DocumentExtractionError("The uploaded PDF does not contain extractable text.")
    lines = [_unescape_pdf_text(match) for match in matches]
    return "\n".join(line for line in lines if line.strip())


def _unescape_pdf_text(value: str) -> str:
    value = value.replace(r"\(", "(").replace(r"\)", ")").replace(r"\\", "\\")
    return unescape(value)
