from __future__ import annotations

from html import unescape
from io import BytesIO
from pathlib import Path
import zipfile
from xml.etree import ElementTree


class DocumentExtractionError(ValueError):
    pass


MAX_DOCUMENT_XML_BYTES = 8 * 1024 * 1024


class BoundedTreeBuilder(ElementTree.TreeBuilder):
    def __init__(self):
        super().__init__()
        self.depth = 0
        self.nodes = 0

    def doctype(self, name, pubid, system):
        raise DocumentExtractionError("Document types and entities are not supported.")

    def start(self, tag, attrs):
        self.depth += 1
        self.nodes += 1
        if self.depth > 64 or self.nodes > 100_000:
            raise DocumentExtractionError("The uploaded document is too complex.")
        return super().start(tag, attrs)

    def end(self, tag):
        value = super().end(tag)
        self.depth -= 1
        return value


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
            info = archive.getinfo("word/document.xml")
            if info.file_size > MAX_DOCUMENT_XML_BYTES:
                raise DocumentExtractionError("Expanded document exceeds the extraction limit.")
            with archive.open(info) as document:
                document_xml = document.read(MAX_DOCUMENT_XML_BYTES + 1)
            if len(document_xml) > MAX_DOCUMENT_XML_BYTES:
                raise DocumentExtractionError("Expanded document exceeds the extraction limit.")
    except (KeyError, zipfile.BadZipFile, RuntimeError, NotImplementedError) as exc:
        raise DocumentExtractionError("The uploaded DOCX file could not be read.") from exc

    try:
        root = ElementTree.fromstring(document_xml, parser=ElementTree.XMLParser(target=BoundedTreeBuilder()))
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
    decoded = content.decode("latin-1")
    lines = []
    index = 0
    while (opening := decoded.find("(", index)) >= 0:
        depth = 1
        index = opening + 1
        while index < len(decoded) and depth:
            ch = decoded[index]
            index += 1
            if ch == "\\":
                index += 1
            elif ch == "(":
                depth += 1
            elif ch == ")":
                depth -= 1
        if depth:
            break
        closing = index - 1
        while index < len(decoded) and decoded[index] in " \t\r\n\x00\x0c":
            index += 1
        if decoded.startswith("Tj", index):
            lines.append(_unescape_pdf_text(decoded[opening + 1:closing]))
            index += 2
    if not lines:
        raise DocumentExtractionError("The uploaded PDF does not contain extractable text.")
    return "\n".join(line for line in lines if line.strip())


def _unescape_pdf_text(value: str) -> str:
    value = value.replace(r"\(", "(").replace(r"\)", ")").replace(r"\\", "\\")
    return unescape(value)
