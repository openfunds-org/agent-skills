#!/usr/bin/env python3
"""Stage a PDF or DOCX into searchable text with honest location markers."""

from __future__ import annotations

import argparse
import json
import shutil
import subprocess
import sys
import zipfile
from pathlib import Path

from defusedxml_fallback import parse_xml_bytes
from oftc_common import sha256_file, write_json

W_NS = "http://schemas.openxmlformats.org/wordprocessingml/2006/main"


def qname(tag: str) -> str:
    return f"{{{W_NS}}}{tag}"


def stage_pdf(path: Path) -> tuple[list[tuple[str, int, str]], list[int], str]:
    """Extract PDF pages using Poppler pdftotext in layout mode."""
    exe = shutil.which("pdftotext")
    if not exe:
        raise RuntimeError("PDF staging requires the 'pdftotext' executable (Poppler).")
    proc = subprocess.run([exe, "-layout", str(path), "-"], capture_output=True, text=True, check=False)
    if proc.returncode != 0:
        raise RuntimeError(f"pdftotext failed: {proc.stderr.strip() or 'unknown error'}")
    pages = proc.stdout.split("\f")
    if pages and not pages[-1].strip():
        pages.pop()
    if not pages:
        raise RuntimeError("No pages were extracted from the PDF.")
    empty = [idx for idx, text in enumerate(pages, 1) if not text.strip()]
    blocks = [
        ("Page", idx, text if text.strip() else "[NO TEXT LAYER]")
        for idx, text in enumerate(pages, 1)
    ]
    return blocks, empty, "pdftotext-layout"


def text_of_paragraph(paragraph) -> str:
    """Return accepted paragraph text, skipping Word tracked deletions (<w:del>)."""
    parts: list[str] = []

    def walk(el, deleted: bool = False) -> None:
        is_deleted = deleted or el.tag == qname("del")
        if not is_deleted:
            if el.tag == qname("t"):
                parts.append(el.text or "")
            elif el.tag == qname("tab"):
                parts.append("\t")
            elif el.tag == qname("br"):
                parts.append("\n")
        for child in el:
            walk(child, is_deleted)

    walk(paragraph)
    return "".join(parts).strip()


def stage_docx(path: Path) -> tuple[list[tuple[str, int, str]], list[int], str]:
    """Extract structural sections from a DOCX document in reading order."""
    try:
        with zipfile.ZipFile(path) as archive:
            root = parse_xml_bytes(archive.read("word/document.xml"))
    except (zipfile.BadZipFile, KeyError, ValueError) as exc:
        raise RuntimeError(f"Invalid DOCX file: {exc}") from exc

    body = next(root.iter(qname("body")), None)
    if body is None:
        raise RuntimeError("Invalid DOCX file: missing word/document.xml body element.")

    blocks: list[tuple[str, int, str]] = []
    section = 0
    for child in body:
        content: list[str] = []
        if child.tag == qname("p"):
            text = text_of_paragraph(child)
            if text:
                content.append(text)
        elif child.tag == qname("tbl"):
            for row in child.findall(qname("tr")):
                cells: list[str] = []
                for cell in row.findall(qname("tc")):
                    cell_text = " ".join(
                        filter(None, (text_of_paragraph(p) for p in cell.iter(qname("p"))))
                    )
                    cells.append(cell_text)
                if any(cells):
                    content.append(" | ".join(cells))
        if content:
            section += 1
            blocks.append(("Section", section, "\n".join(content)))

    if not blocks:
        raise RuntimeError("No readable paragraphs or tables were extracted from the DOCX.")
    return blocks, [], "docx-xml-accepted-text"


def main() -> None:
    ap = argparse.ArgumentParser(description="Stage a PDF or DOCX into searchable Markdown.")
    ap.add_argument("input", help="Source PDF or DOCX file.")
    ap.add_argument("--output", required=True, help="Output staged Markdown path.")
    ap.add_argument("--manifest", required=True, help="Output JSON manifest path.")
    args = ap.parse_args()

    source = Path(args.input)
    if not source.is_file():
        sys.exit(f"Input file not found: {source}")

    ext = source.suffix.lower()
    try:
        if ext == ".pdf":
            blocks, unreadable, method = stage_pdf(source)
            location_type = "page"
        elif ext == ".docx":
            blocks, unreadable, method = stage_docx(source)
            location_type = "section"
        else:
            raise RuntimeError("Unsupported input. Provide a PDF or DOCX; legacy .doc is not supported.")
    except RuntimeError as exc:
        sys.exit(str(exc))

    output = Path(args.output)
    output.parent.mkdir(parents=True, exist_ok=True)
    with output.open("w", encoding="utf-8") as handle:
        handle.write(f"# Staged document: {source.name}\n\n")
        for label, number, text in blocks:
            handle.write(f"## {label} {number}\n\n{text}\n\n")

    warnings: list[str] = []
    if unreadable:
        warnings.append("Visually inspect every unreadable PDF page before proceeding.")
    if ext == ".docx":
        warnings.append("DOCX locations are structural sections, not rendered page numbers.")

    manifest = {
        "source_path": str(source.resolve()),
        "source_file": source.name,
        "source_sha256": sha256_file(source),
        "source_type": ext[1:],
        "location_type": location_type,
        "locations": len(blocks),
        "unreadable_locations": unreadable,
        "extraction_method": method,
        "warnings": warnings,
    }
    write_json(args.manifest, manifest)
    print(json.dumps(manifest))


if __name__ == "__main__":
    main()
