"""A petition as a PDF (A4, Times New Roman 12, justified), with a font that has the Turkish
letters: Times New Roman where the system has it, else DejaVu Serif or Liberation Serif."""

from __future__ import annotations

import io
from functools import cache
from pathlib import Path
from xml.sax.saxutils import escape

from reportlab.lib.enums import TA_CENTER, TA_JUSTIFY, TA_LEFT, TA_RIGHT
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib.units import cm
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.platypus import Paragraph, SimpleDocTemplate

from legal_api.drafting.export import FONT_SIZE, MARGIN_CM, Block, Run

# (regular, bold) font files, in order of preference, on macOS, Windows and Linux.
FONT_FILES = [
    ("/System/Library/Fonts/Supplemental/Times New Roman.ttf",
     "/System/Library/Fonts/Supplemental/Times New Roman Bold.ttf"),
    ("C:/Windows/Fonts/times.ttf", "C:/Windows/Fonts/timesbd.ttf"),
    ("/usr/share/fonts/truetype/dejavu/DejaVuSerif.ttf",
     "/usr/share/fonts/truetype/dejavu/DejaVuSerif-Bold.ttf"),
    ("/usr/share/fonts/truetype/liberation/LiberationSerif-Regular.ttf",
     "/usr/share/fonts/truetype/liberation/LiberationSerif-Bold.ttf"),
]


class NoFont(RuntimeError):
    pass


@cache
def _fonts() -> tuple[str, str]:
    for regular, bold in FONT_FILES:
        if Path(regular).exists() and Path(bold).exists():
            pdfmetrics.registerFont(TTFont("PetitionSerif", regular))
            pdfmetrics.registerFont(TTFont("PetitionSerif-Bold", bold))
            pdfmetrics.registerFontFamily("PetitionSerif", normal="PetitionSerif",
                                          bold="PetitionSerif-Bold")
            return "PetitionSerif", "PetitionSerif-Bold"
    raise NoFont("no serif font with Turkish letters found")


def _markup(r: Run, bold_font: str) -> str:
    """A run as reportlab markup. Italics are slanted with <i> (the serif family has no italic
    face registered, so reportlab synthesises none and keeps the upright face)."""
    out = escape(r.text)
    if r.underline:
        out = f"<u>{out}</u>"
    if r.italic:
        out = f"<i>{out}</i>"
    if r.bold:
        out = f"<font name='{bold_font}'>{out}</font>"
    if r.size:
        out = f"<font size='{r.size}'>{out}</font>"
    return out


def to_pdf(blocks: list[Block], title: str = "") -> bytes:
    regular, bold = _fonts()
    body = ParagraphStyle("body", fontName=regular, fontSize=FONT_SIZE,
                          leading=FONT_SIZE * 1.4, alignment=TA_JUSTIFY, spaceAfter=6)
    centred = ParagraphStyle("centred", parent=body, alignment=TA_CENTER, spaceAfter=14)
    right = ParagraphStyle("right", parent=body, alignment=TA_RIGHT, spaceAfter=14)
    left = ParagraphStyle("left", parent=body, alignment=TA_LEFT)
    styles = {"centre": centred, "right": right, "left": left}
    story = []
    for block in blocks:
        markup = "".join(_markup(r, bold) for r in block.runs if not r.marker)
        story.append(Paragraph(markup, styles.get(block.align, body)))
    buf = io.BytesIO()
    margin = MARGIN_CM * cm
    # The title is what PDF viewers show as the document's name (reportlab's default author
    # "anonymous" was shown instead).
    SimpleDocTemplate(buf, pagesize=A4, leftMargin=margin, rightMargin=margin,
                      topMargin=margin, bottomMargin=margin, title=title, author="",
                      subject="", creator="").build(story)
    return buf.getvalue()
