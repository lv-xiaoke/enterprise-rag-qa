from __future__ import annotations

import re
from pathlib import Path

from reportlab.lib import colors
from reportlab.lib.enums import TA_CENTER
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import cm
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.platypus import (
    ListFlowable,
    ListItem,
    PageBreak,
    Paragraph,
    Preformatted,
    SimpleDocTemplate,
    Spacer,
)


ROOT = Path(__file__).resolve().parent
MD_PATH = ROOT / "HELP.md"
PDF_PATH = ROOT / "LangChain_ReAct_Agent_项目完整帮助文档.pdf"
FONT_PATH = Path(r"C:\Windows\Fonts\msyh.ttc")
MONO_FONT_PATH = Path(r"C:\Windows\Fonts\simhei.ttf")


def register_fonts() -> tuple[str, str]:
    body_font = "MicrosoftYaHei"
    mono_font = "SimHei"
    pdfmetrics.registerFont(TTFont(body_font, str(FONT_PATH)))
    pdfmetrics.registerFont(TTFont(mono_font, str(MONO_FONT_PATH)))
    return body_font, mono_font


def xml_escape(text: str) -> str:
    return (
        text.replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
    )


def inline(text: str) -> str:
    text = xml_escape(text)
    text = re.sub(r"`([^`]+)`", r"<font color='#8a3ffc'>\1</font>", text)
    return text


def make_styles(body_font: str, mono_font: str):
    styles = getSampleStyleSheet()
    styles.add(
        ParagraphStyle(
            name="DocTitle",
            fontName=body_font,
            fontSize=24,
            leading=34,
            alignment=TA_CENTER,
            textColor=colors.HexColor("#1f2937"),
            spaceAfter=18,
        )
    )
    styles.add(
        ParagraphStyle(
            name="BodyCN",
            fontName=body_font,
            fontSize=10.5,
            leading=17,
            textColor=colors.HexColor("#111827"),
            spaceAfter=7,
        )
    )
    styles.add(
        ParagraphStyle(
            name="H1CN",
            fontName=body_font,
            fontSize=18,
            leading=24,
            textColor=colors.HexColor("#111827"),
            spaceBefore=14,
            spaceAfter=10,
        )
    )
    styles.add(
        ParagraphStyle(
            name="H2CN",
            fontName=body_font,
            fontSize=15,
            leading=21,
            textColor=colors.HexColor("#1f2937"),
            spaceBefore=12,
            spaceAfter=8,
        )
    )
    styles.add(
        ParagraphStyle(
            name="H3CN",
            fontName=body_font,
            fontSize=12.5,
            leading=18,
            textColor=colors.HexColor("#374151"),
            spaceBefore=9,
            spaceAfter=6,
        )
    )
    styles.add(
        ParagraphStyle(
            name="ListCN",
            fontName=body_font,
            fontSize=10.2,
            leading=16,
            leftIndent=10,
            spaceAfter=4,
        )
    )
    styles.add(
        ParagraphStyle(
            name="CodeCN",
            fontName=mono_font,
            fontSize=8.6,
            leading=12,
            textColor=colors.HexColor("#111827"),
            backColor=colors.HexColor("#f3f4f6"),
            borderColor=colors.HexColor("#e5e7eb"),
            borderWidth=0.5,
            borderPadding=6,
            leftIndent=0,
            rightIndent=0,
            spaceBefore=4,
            spaceAfter=8,
        )
    )
    return styles


def flush_list(story, items, ordered, styles):
    if not items:
        return
    flow_items = [
        ListItem(Paragraph(inline(item), styles["ListCN"]), leftIndent=12)
        for item in items
    ]
    story.append(
        ListFlowable(
            flow_items,
            bulletType="1" if ordered else "bullet",
            start="1",
            leftIndent=18,
            bulletFontName=styles["BodyCN"].fontName,
            bulletFontSize=9,
        )
    )
    items.clear()


def build_story(md: str, styles):
    story = []
    lines = md.splitlines()
    in_code = False
    code_lines: list[str] = []
    list_items: list[str] = []
    list_ordered = False
    title_done = False

    def flush_code():
        if code_lines:
            story.append(Preformatted("\n".join(code_lines), styles["CodeCN"], maxLineLength=92))
            code_lines.clear()

    for raw in lines:
        line = raw.rstrip()
        stripped = line.strip()

        if stripped.startswith("```"):
            flush_list(story, list_items, list_ordered, styles)
            if in_code:
                flush_code()
                in_code = False
            else:
                in_code = True
            continue

        if in_code:
            code_lines.append(line)
            continue

        if not stripped:
            flush_list(story, list_items, list_ordered, styles)
            story.append(Spacer(1, 2))
            continue

        if stripped.startswith("# "):
            flush_list(story, list_items, list_ordered, styles)
            text = stripped[2:].strip()
            if not title_done:
                story.append(Paragraph(inline(text), styles["DocTitle"]))
                story.append(Paragraph("生成日期：2026-05-06", styles["BodyCN"]))
                story.append(PageBreak())
                title_done = True
            else:
                story.append(Paragraph(inline(text), styles["H1CN"]))
            continue

        if stripped.startswith("## "):
            flush_list(story, list_items, list_ordered, styles)
            story.append(Paragraph(inline(stripped[3:].strip()), styles["H1CN"]))
            continue

        if stripped.startswith("### "):
            flush_list(story, list_items, list_ordered, styles)
            story.append(Paragraph(inline(stripped[4:].strip()), styles["H2CN"]))
            continue

        if stripped.startswith("#### "):
            flush_list(story, list_items, list_ordered, styles)
            story.append(Paragraph(inline(stripped[5:].strip()), styles["H3CN"]))
            continue

        match = re.match(r"^\d+\.\s+(.*)", stripped)
        if match:
            if list_items and not list_ordered:
                flush_list(story, list_items, list_ordered, styles)
            list_ordered = True
            list_items.append(match.group(1))
            continue

        if stripped.startswith("- "):
            if list_items and list_ordered:
                flush_list(story, list_items, list_ordered, styles)
            list_ordered = False
            list_items.append(stripped[2:].strip())
            continue

        flush_list(story, list_items, list_ordered, styles)
        if stripped.startswith("> "):
            story.append(Paragraph("<i>" + inline(stripped[2:].strip()) + "</i>", styles["BodyCN"]))
        else:
            story.append(Paragraph(inline(stripped), styles["BodyCN"]))

    flush_list(story, list_items, list_ordered, styles)
    flush_code()
    return story


def footer(canvas, doc):
    canvas.saveState()
    canvas.setFont("MicrosoftYaHei", 8)
    canvas.setFillColor(colors.HexColor("#6b7280"))
    canvas.drawRightString(A4[0] - 2 * cm, 1.2 * cm, f"第 {doc.page} 页")
    canvas.restoreState()


def main() -> None:
    body_font, mono_font = register_fonts()
    styles = make_styles(body_font, mono_font)
    doc = SimpleDocTemplate(
        str(PDF_PATH),
        pagesize=A4,
        rightMargin=2 * cm,
        leftMargin=2 * cm,
        topMargin=1.9 * cm,
        bottomMargin=1.8 * cm,
        title="LangChain ReAct Agent 项目完整帮助文档",
        author="Codex",
    )
    story = build_story(MD_PATH.read_text(encoding="utf-8"), styles)
    doc.build(story, onFirstPage=footer, onLaterPages=footer)
    print(PDF_PATH)


if __name__ == "__main__":
    main()
