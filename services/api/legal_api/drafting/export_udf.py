"""A petition as a UDF file, the document format of UYAP's editor.

A UDF file is a ZIP archive with `content.xml`: the whole text in one CDATA block, then
paragraph elements whose `content` children point into that text by offset and length, with
the run's font, size and weight. The layout below (format 1.8, A4, Times New Roman 12) follows
the structure documented by the open UDF-Toolkit project; there is no published specification.
"""

from __future__ import annotations

import io
import zipfile
from xml.sax.saxutils import quoteattr

from legal_api.drafting.export import FONT, FONT_SIZE, MARGIN_CM, Block, Run

POINTS_PER_CM = 28.3464567
_ALIGN_LEFT, _ALIGN_CENTRE, _ALIGN_RIGHT, _ALIGN_JUSTIFY = 0, 1, 2, 3


def _run(start: int, r: Run) -> str:
    style = "".join(f' {name}="true"' for name, on in
                    (("bold", r.bold), ("italic", r.italic), ("underline", r.underline)) if on)
    return (f'<content family={quoteattr(FONT)} size="{r.size or FONT_SIZE}"{style} '
            f'startOffset="{start}" length="{len(r.text)}" />')


def content_xml(blocks: list[Block]) -> str:
    text, paragraphs, offset = [], [], 0
    for block in blocks:
        runs = []
        for r in block.runs:
            if r.marker or not r.text:
                continue
            runs.append(_run(offset, r))
            text.append(r.text)
            offset += len(r.text)
        text.append("\n")           # each paragraph ends with a newline, counted in the text
        runs.append(_run(offset, Run("\n")))
        offset += 1
        align = {"centre": _ALIGN_CENTRE, "right": _ALIGN_RIGHT,
                 "left": _ALIGN_LEFT}.get(block.align, _ALIGN_JUSTIFY)
        paragraphs.append(f'<paragraph Alignment="{align}" LeftIndent="0.0" RightIndent="0.0">'
                          f'{"".join(runs)}</paragraph>')
    body = "".join(text).replace("]]>", "]]]]><![CDATA[>")
    margin = round(MARGIN_CM * POINTS_PER_CM, 2)
    return ('<?xml version="1.0" encoding="UTF-8" ?>\n<template format_id="1.8">\n'
            f"<content><![CDATA[{body}]]></content>\n"
            f'<properties><pageFormat mediaSizeName="1" leftMargin="{margin}" '
            f'rightMargin="{margin}" topMargin="{margin}" bottomMargin="{margin}" '
            'paperOrientation="1" headerFOffset="20.0" footerFOffset="20.0" /></properties>\n'
            f'<elements resolver="hvl-default">{"".join(paragraphs)}</elements>\n'
            '<styles><style name="hvl-default" family="Times New Roman" size="12" '
            'description="Gövde" /></styles>\n</template>')


def to_udf(blocks: list[Block]) -> bytes:
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as z:
        z.writestr("content.xml", content_xml(blocks))
    return buf.getvalue()
