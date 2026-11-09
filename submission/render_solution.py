"""Render the editable Markdown solution as a two-page A4 PDF with ReportLab."""

import argparse
from html import escape
import os
from pathlib import Path
import re

from reportlab.lib.colors import HexColor
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.platypus import PageBreak, Paragraph, SimpleDocTemplate


HERE = Path(__file__).resolve().parent
INK = HexColor("#172D32")
TEXT = HexColor("#27393E")
TEAL = HexColor("#176359")
MUTED = HexColor("#485D62")
RULE = HexColor("#CADBD7")
INLINE = re.compile(r"\*\*([^*]+)\*\*|`([^`]+)`|\[([^\]]+)\]\((https://[^\s)]+)\)")


def register_fonts(font_dir: Path | None) -> None:
    windows = Path(os.environ.get("WINDIR", "C:/Windows")) / "Fonts"
    candidates = [
        (font_dir or windows, "segoeui.ttf", "segoeuib.ttf"),
        (font_dir or Path("/usr/share/fonts/truetype/dejavu"), "DejaVuSans.ttf", "DejaVuSans-Bold.ttf"),
    ]
    for directory, regular, bold in candidates:
        if (directory / regular).is_file() and (directory / bold).is_file():
            pdfmetrics.registerFont(TTFont("Solution", directory / regular))
            pdfmetrics.registerFont(TTFont("Solution-Bold", directory / bold))
            pdfmetrics.registerFontFamily("Solution", normal="Solution", bold="Solution-Bold")
            return
    raise SystemExit("Set --font-dir to a directory containing Segoe UI or DejaVu Sans fonts.")


def inline(text: str) -> str:
    parts = []
    cursor = 0
    for match in INLINE.finditer(text):
        parts.append(escape(text[cursor:match.start()]))
        bold, code, label, target = match.groups()
        if bold:
            parts.append(f"<b>{escape(bold)}</b>")
        elif code:
            parts.append(f'<font color="#176359">{escape(code)}</font>')
        else:
            parts.append(f'<link href="{escape(target, quote=True)}" color="#176359"><u>{escape(label)}</u></link>')
        cursor = match.end()
    parts.append(escape(text[cursor:]))
    return "".join(parts)


def footer(canvas, document) -> None:
    width, _ = A4
    canvas.saveState()
    canvas.setStrokeColor(RULE)
    canvas.setLineWidth(0.7)
    canvas.line(50, 43, width - 50, 43)
    canvas.setFont("Solution", 8.5)
    canvas.setFillColor(MUTED)
    canvas.drawString(50, 29, "NyaySaathi AI  /  Kuku AI Generalist Assignment")
    canvas.drawRightString(width - 50, 29, f"{document.page} / 2")
    canvas.restoreState()


def render(source: Path, output: Path, font_dir: Path | None) -> None:
    register_fonts(font_dir)
    body = ParagraphStyle("Body", fontName="Solution", fontSize=10.8, leading=14.6, textColor=TEXT, spaceAfter=7)
    kicker = ParagraphStyle("Kicker", parent=body, fontName="Solution-Bold", fontSize=9.2,
                            leading=13, textColor=TEAL, spaceAfter=9, keepWithNext=True)
    title = ParagraphStyle("Title", parent=body, fontName="Solution-Bold", fontSize=31, leading=36,
                           textColor=INK, spaceAfter=6, keepWithNext=True)
    second_title = ParagraphStyle("SecondTitle", parent=title, fontSize=25, leading=30, spaceAfter=8)
    deck = ParagraphStyle("Deck", parent=body, fontSize=13, leading=18, textColor=MUTED,
                          spaceAfter=12, keepWithNext=True)
    section = ParagraphStyle("Section", parent=body, fontName="Solution-Bold", fontSize=13.2, leading=17,
                             textColor=INK, spaceBefore=7, spaceAfter=5, keepWithNext=True)
    step = ParagraphStyle("Step", parent=body, leftIndent=19, bulletIndent=1, bulletFontName="Solution-Bold",
                          bulletFontSize=10.5, bulletColor=TEAL, spaceAfter=5)

    pages = source.read_text(encoding="utf-8").split("<!-- pagebreak -->")
    if len(pages) != 2:
        raise SystemExit("The source needs exactly one page-break marker.")
    story = []
    for index, page in enumerate(pages):
        if index:
            story.append(PageBreak())
        label = "PROBLEM 2  /  KUKU AI GENERALIST ASSIGNMENT" if index == 0 else "EVALUATION  /  LIMITS AND SCALE"
        story.append(Paragraph(label, kicker))
        for block_number, block in enumerate(re.split(r"\n\s*\n", page.strip())):
            if block.startswith("# "):
                story.append(Paragraph(inline(block[2:]), title if index == 0 else second_title))
            elif block.startswith("## "):
                story.append(Paragraph(inline(block[3:]), section))
            elif re.match(r"^\d+\. ", block):
                for line in block.splitlines():
                    number, description = line.split(". ", 1)
                    story.append(Paragraph(inline(description), step, bulletText=number + "."))
            else:
                story.append(Paragraph(inline(" ".join(block.splitlines())),
                                       deck if index == 0 and block_number == 1 else body))

    document = SimpleDocTemplate(str(output), pagesize=A4, leftMargin=44, rightMargin=44, topMargin=47,
                                 bottomMargin=55, title="NyaySaathi AI | Kuku Problem 2", author="NyaySaathi AI project")
    document.build(story, onFirstPage=footer, onLaterPages=footer)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--font-dir", type=Path)
    args = parser.parse_args()
    render(HERE / "Kuku_NyaySaathi_Solution.md", HERE / "Kuku_NyaySaathi_Solution.pdf", args.font_dir)
