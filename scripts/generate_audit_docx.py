"""Generate lightweight DOCX audit deliverables from Markdown reports."""
from pathlib import Path
from xml.sax.saxutils import escape
import zipfile

ROOT = Path(__file__).resolve().parents[1]


def _paragraphs(markdown: str) -> str:
    result = []
    for raw in markdown.splitlines():
        text = raw.strip().lstrip("#").strip()
        if not text or text == "---":
            continue
        style = "Title" if raw.startswith("# ") else "Heading1" if raw.startswith("## ") else None
        props = f'<w:pPr><w:pStyle w:val="{style}"/></w:pPr>' if style else ""
        result.append(f'<w:p>{props}<w:r><w:t xml:space="preserve">{escape(text)}</w:t></w:r></w:p>')
    return "".join(result)


def build(source: Path, target: Path) -> None:
    cover = (
        '<w:p><w:pPr><w:pStyle w:val="Title"/></w:pPr><w:r><w:t>FinderOS Security Audit Report</w:t></w:r></w:p>'
        '<w:p><w:r><w:t>Project: DataFinderAgentOS</w:t></w:r></w:p>'
        '<w:p><w:r><w:t>Group: FinderOS Project Team</w:t></w:r></w:p>'
        '<w:p><w:r><w:t>Members: Project contributors</w:t></w:r></w:p>'
        '<w:p><w:r><w:t>Date: 2026-07-16</w:t></w:r></w:p>'
        '<w:p><w:r><w:br w:type="page"/></w:r></w:p>'
        '<w:p><w:r><w:t>Contents</w:t></w:r></w:p>'
        '<w:p><w:fldSimple w:instr="TOC \\o &quot;1-3&quot; \\h \\z \\u"/></w:p>'
        '<w:p><w:r><w:br w:type="page"/></w:r></w:p>'
    )
    document = ('<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
        '<w:document xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main" '
        'xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships">'
        f'<w:body>{cover}{_paragraphs(source.read_text(encoding="utf-8"))}'
        '<w:sectPr><w:headerReference w:type="default" r:id="rId1"/>'
        '<w:footerReference w:type="default" r:id="rId2"/></w:sectPr></w:body></w:document>')
    types = ('<?xml version="1.0" encoding="UTF-8"?>'
        '<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">'
        '<Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/>'
        '<Default Extension="xml" ContentType="application/xml"/>'
        '<Override PartName="/word/document.xml" ContentType="application/vnd.openxmlformats-officedocument.wordprocessingml.document.main+xml"/>'
        '<Override PartName="/word/header1.xml" ContentType="application/vnd.openxmlformats-officedocument.wordprocessingml.header+xml"/>'
        '<Override PartName="/word/footer1.xml" ContentType="application/vnd.openxmlformats-officedocument.wordprocessingml.footer+xml"/>'
        '</Types>')
    rels = ('<?xml version="1.0" encoding="UTF-8"?>'
        '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
        '<Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument" Target="word/document.xml"/>'
        '</Relationships>')
    document_rels = ('<?xml version="1.0" encoding="UTF-8"?>'
        '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
        '<Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/header" Target="header1.xml"/>'
        '<Relationship Id="rId2" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/footer" Target="footer1.xml"/>'
        '</Relationships>')
    header = ('<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
        '<w:hdr xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main">'
        '<w:p><w:r><w:t>FinderOS Security Audit</w:t></w:r></w:p></w:hdr>')
    footer = ('<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
        '<w:ftr xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main">'
        '<w:p><w:r><w:t>Page </w:t></w:r><w:fldSimple w:instr="PAGE"/></w:p></w:ftr>')
    with zipfile.ZipFile(target, "w", zipfile.ZIP_DEFLATED) as archive:
        archive.writestr("[Content_Types].xml", types)
        archive.writestr("_rels/.rels", rels)
        archive.writestr("word/document.xml", document)
        archive.writestr("word/_rels/document.xml.rels", document_rels)
        archive.writestr("word/header1.xml", header)
        archive.writestr("word/footer1.xml", footer)


if __name__ == "__main__":
    for name in ("audit_report_v1", "audit_report_v2"):
        build(ROOT / "docs" / f"{name}.md", ROOT / "docs" / f"{name}.docx")
