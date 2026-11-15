from __future__ import annotations

from dataclasses import dataclass
from html import escape
from io import BytesIO
import os
from pathlib import Path
import re
import textwrap
import zipfile


SUPPORTED_FORMATS = ("docx", "pdf")
APP_ROOT = Path(__file__).resolve().parents[1]
MONOREPO_ROOT = Path(__file__).resolve().parents[3]
PACKAGED_TEMPLATE_ROOT = APP_ROOT / "resources" / "context_templates"
MONOREPO_TEMPLATE_ROOT = MONOREPO_ROOT / "flowkron_context_templates_md" / "flowkron_context_templates"
CONTEXT_TEMPLATE_ROOT_ENV = "CONTEXT_TEMPLATE_ROOT"


@dataclass(frozen=True)
class ContextTemplate:
    id: int
    code: str
    name: str
    description: str
    format: str
    fields: list[dict[str, str]]
    path: Path


@dataclass(frozen=True)
class TemplateDownloadOption:
    format: str
    template_id: int
    filename: str
    media_type: str


@dataclass(frozen=True)
class ContextTemplateGroup:
    id: int
    code: str
    name: str
    description: str
    fields: list[dict[str, str]]
    download_options: list[TemplateDownloadOption]


def list_context_templates() -> list[ContextTemplate]:
    templates: list[ContextTemplate] = []
    template_root = resolve_template_root()
    for document_index, path in enumerate(sorted(template_root.glob("*.md")), start=1):
        markdown = path.read_text(encoding="utf-8")
        title = _extract_title(markdown) or _title_from_filename(path)
        code = _code_from_filename(path)
        for format_index, output_format in enumerate(SUPPORTED_FORMATS, start=1):
            templates.append(
                ContextTemplate(
                    id=(document_index * 10) + format_index,
                    code=code,
                    name=title,
                    description=f"Plantilla base de contexto: {title}",
                    format=output_format,
                    fields=_extract_placeholders(markdown),
                    path=path,
                )
            )
    return templates


def resolve_template_root() -> Path:
    for candidate in _candidate_template_roots():
        if candidate.exists() and any(candidate.glob("*.md")):
            return candidate
    return PACKAGED_TEMPLATE_ROOT


def _candidate_template_roots() -> list[Path]:
    candidates: list[Path] = []
    configured_root = os.getenv(CONTEXT_TEMPLATE_ROOT_ENV)
    if configured_root:
        candidates.append(Path(configured_root).expanduser())
    candidates.extend([MONOREPO_TEMPLATE_ROOT, PACKAGED_TEMPLATE_ROOT])
    return candidates


def list_context_template_groups() -> list[ContextTemplateGroup]:
    groups: list[ContextTemplateGroup] = []
    by_code: dict[str, list[ContextTemplate]] = {}
    for template in list_context_templates():
        by_code.setdefault(template.code, []).append(template)

    for group_index, templates in enumerate(by_code.values(), start=1):
        first = templates[0]
        groups.append(
            ContextTemplateGroup(
                id=group_index,
                code=first.code,
                name=first.name,
                description=first.description,
                fields=first.fields,
                download_options=[
                    TemplateDownloadOption(
                        format=template.format,
                        template_id=template.id,
                        filename=f"{template.code}.{template.format}",
                        media_type=_media_type_for_format(template.format),
                    )
                    for template in sorted(templates, key=lambda item: item.format)
                ],
            )
        )
    return groups


def get_context_template(template_id: int) -> ContextTemplate | None:
    return next((template for template in list_context_templates() if template.id == template_id), None)


def render_template_file(template: ContextTemplate) -> tuple[bytes, str, str]:
    markdown = template.path.read_text(encoding="utf-8")
    filename = f"{template.code}.{template.format}"
    if template.format == "docx":
        return _render_docx(markdown), filename, "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
    if template.format == "pdf":
        return _render_pdf(markdown), filename, "application/pdf"
    raise ValueError(f"Unsupported template format: {template.format}")


def _media_type_for_format(output_format: str) -> str:
    if output_format == "docx":
        return "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
    if output_format == "pdf":
        return "application/pdf"
    return "application/octet-stream"


def _code_from_filename(path: Path) -> str:
    return re.sub(r"^\d+-", "", path.stem)


def _title_from_filename(path: Path) -> str:
    return _code_from_filename(path).replace("-", " ").title()


def _extract_title(markdown: str) -> str | None:
    for line in markdown.splitlines():
        if line.startswith("# "):
            return line[2:].strip()
    return None


def _extract_placeholders(markdown: str) -> list[dict[str, str]]:
    fields: list[dict[str, str]] = []
    seen: set[str] = set()
    for match in re.finditer(r"\*\*(?P<label>[^:*]+):\*\*\s*(?:\n|\s{2,})?\[Completar(?P<hint>[^\]]*)\]", markdown):
        label = match.group("label").strip()
        name = re.sub(r"[^a-z0-9]+", "_", label.lower()).strip("_")
        if not name or name in seen:
            continue
        seen.add(name)
        hint = match.group("hint").strip(" :")
        fields.append({"name": name, "label": label, "hint": hint})
    return fields


def _markdown_blocks(markdown: str) -> list[tuple[str, str]]:
    blocks: list[tuple[str, str]] = []
    for raw_line in markdown.splitlines():
        line = raw_line.rstrip()
        if not line:
            blocks.append(("blank", ""))
        elif line.startswith("### "):
            blocks.append(("heading3", _strip_inline_markdown(line[4:])))
        elif line.startswith("## "):
            blocks.append(("heading2", _strip_inline_markdown(line[3:])))
        elif line.startswith("# "):
            blocks.append(("heading1", _strip_inline_markdown(line[2:])))
        elif line.strip("-") == "":
            blocks.append(("separator", ""))
        elif line.startswith("- "):
            blocks.append(("bullet", _strip_inline_markdown(line[2:])))
        else:
            blocks.append(("paragraph", _strip_inline_markdown(line)))
    return blocks


def _strip_inline_markdown(text: str) -> str:
    text = re.sub(r"\*\*(.*?)\*\*", r"\1", text)
    text = re.sub(r"\[(.*?)\]\((.*?)\)", r"\1", text)
    return text.replace("  ", " ").strip()


def _render_docx(markdown: str) -> bytes:
    paragraphs = [_docx_paragraph(kind, text) for kind, text in _markdown_blocks(markdown)]
    document_xml = (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
        '<w:document xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main">'
        "<w:body>"
        + "".join(paragraphs)
        + '<w:sectPr><w:pgSz w:w="12240" w:h="15840"/><w:pgMar w:top="1440" w:right="1440" w:bottom="1440" w:left="1440"/></w:sectPr>'
        "</w:body></w:document>"
    )
    output = BytesIO()
    with zipfile.ZipFile(output, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        archive.writestr("[Content_Types].xml", _docx_content_types())
        archive.writestr("_rels/.rels", _docx_relationships())
        archive.writestr("word/document.xml", document_xml)
    return output.getvalue()


def _docx_paragraph(kind: str, text: str) -> str:
    if kind == "blank":
        return "<w:p/>"
    if kind == "separator":
        return '<w:p><w:r><w:t>----------------------------------------</w:t></w:r></w:p>'
    style = {
        "heading1": "Title",
        "heading2": "Heading2",
        "heading3": "Heading3",
        "bullet": "ListParagraph",
    }.get(kind)
    prefix = "- " if kind == "bullet" else ""
    props = f'<w:pPr><w:pStyle w:val="{style}"/></w:pPr>' if style else ""
    return f"<w:p>{props}<w:r><w:t>{escape(prefix + text)}</w:t></w:r></w:p>"


def _docx_content_types() -> str:
    return (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
        '<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">'
        '<Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/>'
        '<Default Extension="xml" ContentType="application/xml"/>'
        '<Override PartName="/word/document.xml" ContentType="application/vnd.openxmlformats-officedocument.wordprocessingml.document.main+xml"/>'
        "</Types>"
    )


def _docx_relationships() -> str:
    return (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
        '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
        '<Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument" Target="word/document.xml"/>'
        "</Relationships>"
    )


def _render_pdf(markdown: str) -> bytes:
    text_lines: list[str] = []
    for kind, text in _markdown_blocks(markdown):
        if kind == "blank":
            text_lines.append("")
            continue
        prefix = "- " if kind == "bullet" else ""
        width = 78 if kind.startswith("heading") else 92
        text_lines.extend(textwrap.wrap(prefix + text, width=width) or [""])

    pages = [text_lines[index : index + 48] for index in range(0, len(text_lines), 48)] or [[]]
    objects: list[bytes] = [
        b"<< /Type /Catalog /Pages 2 0 R >>",
        b"",
        b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>",
    ]
    page_refs: list[str] = []
    for page_number, page_lines in enumerate(pages):
        page_object_id = 4 + (page_number * 2)
        content_object_id = page_object_id + 1
        page_refs.append(f"{page_object_id} 0 R")
        objects.append(f"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] /Resources << /Font << /F1 3 0 R >> >> /Contents {content_object_id} 0 R >>".encode("ascii"))
        stream = _pdf_text_stream(page_lines)
        objects.append(f"<< /Length {len(stream)} >>\nstream\n".encode("ascii") + stream + b"\nendstream")

    objects[1] = f"<< /Type /Pages /Kids [{' '.join(page_refs)}] /Count {len(page_refs)} >>".encode("ascii")
    return _pdf_document(objects)


def _pdf_text_stream(lines: list[str]) -> bytes:
    commands = ["BT", "/F1 10 Tf", "50 752 Td", "14 TL"]
    for line in lines:
        commands.append(f"({_pdf_escape(line)}) Tj")
        commands.append("T*")
    commands.append("ET")
    return "\n".join(commands).encode("cp1252", errors="replace")


def _pdf_escape(text: str) -> str:
    return text.replace("\\", "\\\\").replace("(", "\\(").replace(")", "\\)")


def _pdf_document(objects: list[bytes]) -> bytes:
    output = BytesIO()
    output.write(b"%PDF-1.4\n")
    offsets = [0]
    for object_id, payload in enumerate(objects, start=1):
        offsets.append(output.tell())
        output.write(f"{object_id} 0 obj\n".encode("ascii"))
        output.write(payload)
        output.write(b"\nendobj\n")
    xref_offset = output.tell()
    output.write(f"xref\n0 {len(objects) + 1}\n".encode("ascii"))
    output.write(b"0000000000 65535 f \n")
    for offset in offsets[1:]:
        output.write(f"{offset:010d} 00000 n \n".encode("ascii"))
    output.write(f"trailer\n<< /Size {len(objects) + 1} /Root 1 0 R >>\nstartxref\n{xref_offset}\n%%EOF\n".encode("ascii"))
    return output.getvalue()
