"""
Converts QA_GUIDE.md to a formatted Word document and saves it to the Desktop.
Run once: python qa/export_guide.py
"""

import re
from pathlib import Path
from docx import Document
from docx.shared import Pt, RGBColor, Inches
from docx.enum.text import WD_ALIGN_PARAGRAPH
from docx.oxml.ns import qn
from docx.oxml import OxmlElement

QA_DIR   = Path(__file__).parent
MD_FILE  = QA_DIR / "QA_GUIDE.md"
OUT_FILE = Path.home() / "Desktop" / "YourAI_QA_Guide.docx"

doc = Document()

# ── Page margins ──────────────────────────────────────────────────────────────
for section in doc.sections:
    section.top_margin    = Inches(1)
    section.bottom_margin = Inches(1)
    section.left_margin   = Inches(1.2)
    section.right_margin  = Inches(1.2)

# ── Colour palette ────────────────────────────────────────────────────────────
DARK_BLUE  = RGBColor(0x1a, 0x1a, 0x2e)
MID_BLUE   = RGBColor(0x0d, 0x6e, 0xfd)
GREY       = RGBColor(0x6c, 0x75, 0x7d)
GREEN      = RGBColor(0x19, 0x87, 0x54)
RED        = RGBColor(0xdc, 0x35, 0x45)
BLACK      = RGBColor(0x21, 0x25, 0x29)
CODE_BG    = RGBColor(0xf8, 0xf9, 0xfa)
CODE_FG    = RGBColor(0xe8, 0x3e, 0x8c)

def set_cell_bg(cell, hex_color: str):
    """Set Word table cell background colour."""
    tc   = cell._tc
    tcPr = tc.get_or_add_tcPr()
    shd  = OxmlElement("w:shd")
    shd.set(qn("w:val"),   "clear")
    shd.set(qn("w:color"), "auto")
    shd.set(qn("w:fill"),  hex_color)
    tcPr.append(shd)

def add_heading(text: str, level: int):
    if level == 1:
        p = doc.add_paragraph()
        p.alignment = WD_ALIGN_PARAGRAPH.LEFT
        run = p.add_run(text)
        run.bold      = True
        run.font.size = Pt(22)
        run.font.color.rgb = DARK_BLUE
        p.paragraph_format.space_before = Pt(18)
        p.paragraph_format.space_after  = Pt(6)
    elif level == 2:
        p = doc.add_paragraph()
        run = p.add_run(text)
        run.bold      = True
        run.font.size = Pt(15)
        run.font.color.rgb = MID_BLUE
        p.paragraph_format.space_before = Pt(14)
        p.paragraph_format.space_after  = Pt(4)
    elif level == 3:
        p = doc.add_paragraph()
        run = p.add_run(text)
        run.bold      = True
        run.font.size = Pt(12)
        run.font.color.rgb = DARK_BLUE
        p.paragraph_format.space_before = Pt(10)
        p.paragraph_format.space_after  = Pt(2)

def add_body(text: str):
    """Add a body paragraph, handling inline bold and inline code."""
    p = doc.add_paragraph()
    p.paragraph_format.space_after = Pt(4)

    # Split on **bold** and `code` patterns
    parts = re.split(r'(\*\*[^*]+\*\*|`[^`]+`)', text)
    for part in parts:
        if part.startswith("**") and part.endswith("**"):
            run = p.add_run(part[2:-2])
            run.bold = True
            run.font.color.rgb = BLACK
        elif part.startswith("`") and part.endswith("`"):
            run = p.add_run(part[1:-1])
            run.font.name = "Courier New"
            run.font.size = Pt(9)
            run.font.color.rgb = CODE_FG
        else:
            run = p.add_run(part)
            run.font.color.rgb = BLACK
    run.font.size = Pt(10.5)

def add_bullet(text: str, level: int = 0):
    p = doc.add_paragraph(style="List Bullet")
    p.paragraph_format.left_indent   = Inches(0.3 + level * 0.25)
    p.paragraph_format.space_after   = Pt(3)

    parts = re.split(r'(\*\*[^*]+\*\*|`[^`]+`)', text)
    for part in parts:
        if part.startswith("**") and part.endswith("**"):
            run = p.add_run(part[2:-2])
            run.bold = True
        elif part.startswith("`") and part.endswith("`"):
            run = p.add_run(part[1:-1])
            run.font.name = "Courier New"
            run.font.size = Pt(9)
            run.font.color.rgb = CODE_FG
        else:
            run = p.add_run(part)
    for run in p.runs:
        run.font.size = Pt(10.5)

def add_code_block(lines: list[str]):
    """Add a styled code block."""
    for line in lines:
        p = doc.add_paragraph()
        p.paragraph_format.left_indent  = Inches(0.4)
        p.paragraph_format.space_before = Pt(1)
        p.paragraph_format.space_after  = Pt(1)
        run = p.add_run(line if line else " ")
        run.font.name  = "Courier New"
        run.font.size  = Pt(9)
        run.font.color.rgb = RGBColor(0x21, 0x25, 0x29)

def add_table(rows: list[list[str]]):
    """Add a styled table. First row = header."""
    if not rows:
        return
    col_count = max(len(r) for r in rows)
    t = doc.add_table(rows=len(rows), cols=col_count)
    t.style = "Table Grid"

    for i, row in enumerate(rows):
        for j, cell_text in enumerate(row):
            cell = t.cell(i, j)
            # strip markdown bold from header
            clean = re.sub(r'\*\*([^*]+)\*\*', r'\1', cell_text.strip())
            cell.text = clean
            run = cell.paragraphs[0].runs[0] if cell.paragraphs[0].runs else cell.paragraphs[0].add_run(clean)
            run.font.size = Pt(9.5)
            if i == 0:
                run.bold = True
                run.font.color.rgb = RGBColor(0xff, 0xff, 0xff)
                set_cell_bg(cell, "1a1a2e")
            else:
                run.font.color.rgb = BLACK
                set_cell_bg(cell, "f8f9fa" if i % 2 == 0 else "ffffff")
    doc.add_paragraph()   # spacing after table

# ── Parse and render the markdown ─────────────────────────────────────────────

lines = MD_FILE.read_text().splitlines()

i = 0
table_rows: list[list[str]] = []
code_lines: list[str] = []
in_code = False
in_table = False

def flush_table():
    global table_rows, in_table
    if table_rows:
        # Remove separator rows (---|--- lines)
        data = [r for r in table_rows if not all(re.match(r'^[-:]+$', c.strip()) for c in r)]
        if data:
            add_table(data)
    table_rows = []
    in_table   = False

def flush_code():
    global code_lines, in_code
    if code_lines:
        add_code_block(code_lines)
    code_lines = []
    in_code    = False

while i < len(lines):
    line = lines[i]

    # Code block toggle
    if line.strip().startswith("```"):
        if in_code:
            flush_code()
        else:
            if in_table:
                flush_table()
            in_code = True
        i += 1
        continue

    if in_code:
        code_lines.append(line)
        i += 1
        continue

    # Table row
    if line.strip().startswith("|"):
        in_table = True
        cells = [c.strip() for c in line.strip().strip("|").split("|")]
        table_rows.append(cells)
        i += 1
        continue
    else:
        if in_table:
            flush_table()

    # Blank line
    if not line.strip():
        i += 1
        continue

    # Headings
    if line.startswith("# "):
        add_heading(line[2:].strip(), 1)
    elif line.startswith("## "):
        add_heading(line[3:].strip(), 2)
    elif line.startswith("### "):
        add_heading(line[4:].strip(), 3)

    # Horizontal rule
    elif line.strip().startswith("---"):
        doc.add_paragraph().add_run("─" * 60).font.color.rgb = GREY

    # Bullet points
    elif line.strip().startswith("- "):
        add_bullet(line.strip()[2:], level=0)
    elif re.match(r'^\s{2,}- ', line):
        add_bullet(line.strip()[2:], level=1)

    # Numbered list
    elif re.match(r'^\d+\.', line.strip()):
        add_bullet(re.sub(r'^\d+\.\s*', '', line.strip()), level=0)

    # Normal paragraph
    else:
        add_body(line.strip())

    i += 1

# Flush any remaining
if in_table:
    flush_table()
if in_code:
    flush_code()

# ── Save ──────────────────────────────────────────────────────────────────────

doc.save(str(OUT_FILE))
print(f"✓ Saved to {OUT_FILE}")
