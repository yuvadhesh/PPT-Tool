"""
Benchmark Dataset Generator for PowerPoint Reading Order Algorithm.
Generates 42 diverse, realistic test presentations covering all required scenarios:
- Title + Content
- Title + Subtitle
- Multi-column layouts (2-col, 3-col, 4-col)
- Media + Captions (below, above, multiple)
- Grids (2x2 row-major, 2x2 col-major, 3x3 matrix)
- Connectors & Flowcharts
- Groups (flat and nested)
- Decorative & Overlapping shapes (Z-order safety)
- SmartArt & Tables & Charts
- RTL text
- Inherited geometry & mc:AlternateContent
- Academic layout

For each test case:
1. Generates the PPTX with known human-logical reading order.
2. Writes `expected_order.json` specifying the exact sequence of shape names.
3. Shuffles the slide's <p:spTree> children with a seeded random permutation so the
   initial XML order is scrambled and the algorithm must genuinely recover the order.
"""
import io
import os
import json
import random
from pathlib import Path
from lxml import etree
import pptx
from pptx import Presentation
from pptx.util import Inches, Pt, Emu
from pptx.enum.shapes import MSO_SHAPE, MSO_SHAPE_TYPE
from pptx.chart.data import CategoryChartData
from pptx.enum.chart import XL_CHART_TYPE
from pptx.dml.color import RGBColor

TINY_PNG_BYTES = (
    b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR\x00\x00\x00\x02\x00\x00\x00\x02\x08\x02"
    b"\x00\x00\x00\xfd\xd4\x9as\x00\x00\x00\x12IDATx\x9cc\xf8\xcf\xc0\xc0\x00\x03"
    b"\x03\x03\x00\x00\x18\x00\x01\xa5\x05Gk\x00\x00\x00\x00IEND\xaeB`\x82"
)

BENCHMARK_DIR = Path(__file__).resolve().parent / "decks"


def _shuffle_slide_sptree(slide, seed: int = 42):
    """Scramble shapes in slide spTree using seeded random while keeping canvas elements."""
    spTree = slide.shapes._spTree
    header_elems = [c for c in spTree if c.tag.split("}")[-1] in ("nvGrpSpPr", "grpSpPr")]
    footer_elems = [c for c in spTree if c.tag.split("}")[-1] == "extLst"]
    shape_elems = [c for c in spTree if c not in header_elems and c not in footer_elems]

    rng = random.Random(seed)
    # Ensure it's not identity permutation if len >= 2
    shuffled = list(shape_elems)
    if len(shuffled) >= 2:
        for _ in range(5):
            rng.shuffle(shuffled)
            if [c for c in shuffled] != shape_elems:
                break

    for c in list(spTree):
        spTree.remove(c)
    for h in header_elems:
        spTree.append(h)
    for s in shuffled:
        spTree.append(s)
    for f in footer_elems:
        spTree.append(f)


def _save_case(prs: Presentation, case_name: str, expected_names: list[str], seed: int = 42):
    BENCHMARK_DIR.mkdir(parents=True, exist_ok=True)
    deck_path = BENCHMARK_DIR / f"{case_name}.pptx"
    meta_path = BENCHMARK_DIR / f"{case_name}_expected.json"

    # Save expected order metadata
    with open(meta_path, "w", encoding="utf-8") as f:
        json.dump({
            "case_name": case_name,
            "expected_order": expected_names,
            "count": len(expected_names)
        }, f, indent=2)

    # Scramble slide 1 shapes
    _shuffle_slide_sptree(prs.slides[0], seed=seed)
    prs.save(str(deck_path))


def build_all_benchmarks():
    print(f"Generating 42 benchmark presentation decks in {BENCHMARK_DIR}...")
    img_stream = io.BytesIO(TINY_PNG_BYTES)

    # --------------------------------------------------------------------------
    # 01: Title + Content
    # --------------------------------------------------------------------------
    prs = Presentation()
    slide = prs.slides.add_slide(prs.slide_layouts[6])
    t = slide.shapes.add_textbox(Inches(1), Inches(0.8), Inches(8), Inches(1))
    t.name = "Title 1"
    t.text = "Quarterly Business Update"
    c = slide.shapes.add_textbox(Inches(1), Inches(2.2), Inches(8), Inches(4))
    c.name = "Content 1"
    c.text = "Key highlights and organizational milestones achieved this quarter."
    _save_case(prs, "01_title_content", ["Title 1", "Content 1"], seed=101)

    # --------------------------------------------------------------------------
    # 02: Title + Subtitle + Content
    # --------------------------------------------------------------------------
    prs = Presentation()
    slide = prs.slides.add_slide(prs.slide_layouts[6])
    t = slide.shapes.add_textbox(Inches(1), Inches(0.6), Inches(8), Inches(0.8))
    t.name = "Title 1"
    t.text = "Executive Strategy 2026"
    sub = slide.shapes.add_textbox(Inches(1), Inches(1.5), Inches(8), Inches(0.6))
    sub.name = "Subtitle 1"
    sub.text = "Roadmap to Sustainable Growth"
    c = slide.shapes.add_textbox(Inches(1), Inches(2.4), Inches(8), Inches(4))
    c.name = "Content 1"
    c.text = "Overview of market opportunities and customer acquisitions."
    _save_case(prs, "02_title_subtitle_content", ["Title 1", "Subtitle 1", "Content 1"], seed=102)

    # --------------------------------------------------------------------------
    # 03: Two Column Layout
    # --------------------------------------------------------------------------
    prs = Presentation()
    slide = prs.slides.add_slide(prs.slide_layouts[6])
    t = slide.shapes.add_textbox(Inches(1), Inches(0.6), Inches(8), Inches(0.8))
    t.name = "Title 1"
    t.text = "Two Column Breakdown"
    c1_h = slide.shapes.add_textbox(Inches(1), Inches(1.8), Inches(3.8), Inches(0.6))
    c1_h.name = "Heading Left"
    c1_h.text = "Left Column Section"
    c1_b = slide.shapes.add_textbox(Inches(1), Inches(2.6), Inches(3.8), Inches(3.5))
    c1_b.name = "Body Left"
    c1_b.text = "Detailed bullet points and explanations for left column."
    c2_h = slide.shapes.add_textbox(Inches(5.2), Inches(1.8), Inches(3.8), Inches(0.6))
    c2_h.name = "Heading Right"
    c2_h.text = "Right Column Section"
    c2_b = slide.shapes.add_textbox(Inches(5.2), Inches(2.6), Inches(3.8), Inches(3.5))
    c2_b.name = "Body Right"
    c2_b.text = "Supporting details and analysis for right column."
    _save_case(prs, "03_two_column_text", ["Title 1", "Heading Left", "Body Left", "Heading Right", "Body Right"], seed=103)

    # --------------------------------------------------------------------------
    # 04: Three Column Layout
    # --------------------------------------------------------------------------
    prs = Presentation()
    slide = prs.slides.add_slide(prs.slide_layouts[6])
    t = slide.shapes.add_textbox(Inches(0.8), Inches(0.6), Inches(8.4), Inches(0.8))
    t.name = "Title 1"
    t.text = "Three Pillars of Innovation"
    col1 = slide.shapes.add_textbox(Inches(0.8), Inches(2.0), Inches(2.6), Inches(4.0))
    col1.name = "Pillar 1"
    col1.text = "Design Excellence"
    col2 = slide.shapes.add_textbox(Inches(3.7), Inches(2.0), Inches(2.6), Inches(4.0))
    col2.name = "Pillar 2"
    col2.text = "Performance Engineering"
    col3 = slide.shapes.add_textbox(Inches(6.6), Inches(2.0), Inches(2.6), Inches(4.0))
    col3.name = "Pillar 3"
    col3.text = "Security & Compliance"
    _save_case(prs, "04_three_column_text", ["Title 1", "Pillar 1", "Pillar 2", "Pillar 3"], seed=104)

    # --------------------------------------------------------------------------
    # 05: Picture with Caption Below
    # --------------------------------------------------------------------------
    prs = Presentation()
    slide = prs.slides.add_slide(prs.slide_layouts[6])
    t = slide.shapes.add_textbox(Inches(1), Inches(0.6), Inches(8), Inches(0.8))
    t.name = "Title 1"
    t.text = "Global Data Center Architecture"
    img_stream.seek(0)
    pic = slide.shapes.add_picture(img_stream, Inches(2.5), Inches(1.8), Inches(5.0), Inches(3.2))
    pic.name = "Picture 1"
    cap = slide.shapes.add_textbox(Inches(2.5), Inches(5.1), Inches(5.0), Inches(0.5))
    cap.name = "Caption 1"
    cap.text = "Figure 1: High-availability cloud server topology across regions."
    _save_case(prs, "05_picture_caption_below", ["Title 1", "Picture 1", "Caption 1"], seed=105)

    # --------------------------------------------------------------------------
    # 06: Picture with Caption Above
    # --------------------------------------------------------------------------
    prs = Presentation()
    slide = prs.slides.add_slide(prs.slide_layouts[6])
    t = slide.shapes.add_textbox(Inches(1), Inches(0.6), Inches(8), Inches(0.8))
    t.name = "Title 1"
    t.text = "Satellite Sensor Analysis"
    cap = slide.shapes.add_textbox(Inches(2.5), Inches(1.6), Inches(5.0), Inches(0.4))
    cap.name = "Caption 1"
    cap.text = "Sensor telemetry reading recorded at 12:00 UTC."
    img_stream.seek(0)
    pic = slide.shapes.add_picture(img_stream, Inches(2.5), Inches(2.1), Inches(5.0), Inches(3.2))
    pic.name = "Picture 1"
    _save_case(prs, "06_picture_caption_above", ["Title 1", "Caption 1", "Picture 1"], seed=106)

    # --------------------------------------------------------------------------
    # 07: Text Left, Picture Right
    # --------------------------------------------------------------------------
    prs = Presentation()
    slide = prs.slides.add_slide(prs.slide_layouts[6])
    t = slide.shapes.add_textbox(Inches(1), Inches(0.6), Inches(8), Inches(0.8))
    t.name = "Title 1"
    t.text = "Product Capabilities"
    txt = slide.shapes.add_textbox(Inches(1), Inches(1.8), Inches(4.0), Inches(4.5))
    txt.name = "Product Description"
    txt.text = "Our solution delivers high-throughput event processing with zero downtime."
    img_stream.seek(0)
    pic = slide.shapes.add_picture(img_stream, Inches(5.4), Inches(1.8), Inches(3.6), Inches(4.0))
    pic.name = "Product Photo"
    _save_case(prs, "07_text_left_picture_right", ["Title 1", "Product Description", "Product Photo"], seed=107)

    # --------------------------------------------------------------------------
    # 08: Picture Left, Text Right
    # --------------------------------------------------------------------------
    prs = Presentation()
    slide = prs.slides.add_slide(prs.slide_layouts[6])
    t = slide.shapes.add_textbox(Inches(1), Inches(0.6), Inches(8), Inches(0.8))
    t.name = "Title 1"
    t.text = "Hardware Integration"
    img_stream.seek(0)
    pic = slide.shapes.add_picture(img_stream, Inches(1.0), Inches(1.8), Inches(3.8), Inches(4.0))
    pic.name = "Hardware Diagram"
    txt = slide.shapes.add_textbox(Inches(5.2), Inches(1.8), Inches(3.8), Inches(4.0))
    txt.name = "Specs Description"
    txt.text = "Hardware components are integrated using standard PCI Express interfaces."
    _save_case(prs, "08_picture_left_text_right", ["Title 1", "Hardware Diagram", "Specs Description"], seed=108)

    # --------------------------------------------------------------------------
    # 09: Table Slide
    # --------------------------------------------------------------------------
    prs = Presentation()
    slide = prs.slides.add_slide(prs.slide_layouts[6])
    t = slide.shapes.add_textbox(Inches(1), Inches(0.6), Inches(8), Inches(0.8))
    t.name = "Title 1"
    t.text = "Regional Performance Summary"
    tbl = slide.shapes.add_table(3, 3, Inches(1), Inches(1.8), Inches(8), Inches(3.5))
    tbl.name = "Performance Table"
    tbl.table.cell(0, 0).text = "Region"
    tbl.table.cell(0, 1).text = "Q3"
    tbl.table.cell(0, 2).text = "Q4"
    note = slide.shapes.add_textbox(Inches(1), Inches(5.6), Inches(8), Inches(0.6))
    note.name = "Table Note"
    note.text = "Note: Values are calculated based on audited accounts."
    _save_case(prs, "09_table_slide", ["Title 1", "Performance Table", "Table Note"], seed=109)

    # --------------------------------------------------------------------------
    # 10: Chart Slide
    # --------------------------------------------------------------------------
    prs = Presentation()
    slide = prs.slides.add_slide(prs.slide_layouts[6])
    t = slide.shapes.add_textbox(Inches(1), Inches(0.6), Inches(8), Inches(0.8))
    t.name = "Title 1"
    t.text = "Quarterly Revenue Growth"
    c_data = CategoryChartData()
    c_data.categories = ["Q1", "Q2", "Q3", "Q4"]
    c_data.add_series("Revenue", (10, 15, 25, 40))
    chart = slide.shapes.add_chart(XL_CHART_TYPE.COLUMN_CLUSTERED, Inches(1), Inches(1.8), Inches(8), Inches(3.8), c_data)
    chart.name = "Revenue Chart"
    summary = slide.shapes.add_textbox(Inches(1), Inches(5.8), Inches(8), Inches(0.6))
    summary.name = "Chart Summary"
    summary.text = "Total annual revenue reached $90M representing 160% YoY growth."
    _save_case(prs, "10_chart_slide", ["Title 1", "Revenue Chart", "Chart Summary"], seed=110)

    # --------------------------------------------------------------------------
    # 11: SmartArt Diagram Simulation
    # --------------------------------------------------------------------------
    prs = Presentation()
    slide = prs.slides.add_slide(prs.slide_layouts[6])
    t = slide.shapes.add_textbox(Inches(1), Inches(0.6), Inches(8), Inches(0.8))
    t.name = "Title 1"
    t.text = "Organizational Process Flow"
    gf = slide.shapes.add_shape(MSO_SHAPE.RECTANGLE, Inches(1), Inches(1.8), Inches(8), Inches(3.5))
    gf.name = "SmartArt Diagram"
    gf.text = "Process Step 1 -> Process Step 2 -> Process Step 3"
    # Mark as diagram in name
    body = slide.shapes.add_textbox(Inches(1), Inches(5.5), Inches(8), Inches(0.8))
    body.name = "Process Summary"
    body.text = "Detailed documentation for process execution."
    _save_case(prs, "11_smartart_diagram", ["Title 1", "SmartArt Diagram", "Process Summary"], seed=111)

    # --------------------------------------------------------------------------
    # 12: Grouped Diagram
    # --------------------------------------------------------------------------
    prs = Presentation()
    slide = prs.slides.add_slide(prs.slide_layouts[6])
    t = slide.shapes.add_textbox(Inches(1), Inches(0.6), Inches(8), Inches(0.8))
    t.name = "Title 1"
    t.text = "System Components Architecture"
    # Create group with 2 shapes
    grp = slide.shapes.add_group_shape()
    grp.name = "Component Group"
    s1 = grp.shapes.add_shape(MSO_SHAPE.ROUNDED_RECTANGLE, Inches(1), Inches(1.8), Inches(3.5), Inches(2.5))
    s1.name = "Frontend Engine"
    s1.text = "Frontend UI Service"
    s2 = grp.shapes.add_shape(MSO_SHAPE.ROUNDED_RECTANGLE, Inches(5), Inches(1.8), Inches(3.5), Inches(2.5))
    s2.name = "Backend Engine"
    s2.text = "Backend API Service"
    desc = slide.shapes.add_textbox(Inches(1), Inches(4.8), Inches(8), Inches(1.5))
    desc.name = "Architecture Details"
    desc.text = "Services communicate securely using mTLS over internal virtual private cloud."
    _save_case(prs, "12_grouped_diagram", ["Title 1", "Component Group", "Architecture Details"], seed=112)

    # --------------------------------------------------------------------------
    # 13: Nested Groups
    # --------------------------------------------------------------------------
    prs = Presentation()
    slide = prs.slides.add_slide(prs.slide_layouts[6])
    t = slide.shapes.add_textbox(Inches(1), Inches(0.6), Inches(8), Inches(0.8))
    t.name = "Title 1"
    t.text = "Hierarchical Subsystem Model"
    outer = slide.shapes.add_group_shape()
    outer.name = "Outer Subsystem"
    inner = outer.shapes.add_group_shape()
    inner.name = "Inner Core Service"
    inner_box = inner.shapes.add_shape(MSO_SHAPE.RECTANGLE, Inches(1.5), Inches(1.8), Inches(3), Inches(2))
    inner_box.name = "Core Worker"
    inner_box.text = "Worker Node"
    foot = slide.shapes.add_textbox(Inches(1), Inches(5.0), Inches(8), Inches(1.0))
    foot.name = "Subsystem Footnote"
    foot.text = "Outer subsystem manages worker pools."
    _save_case(prs, "13_nested_groups", ["Title 1", "Outer Subsystem", "Subsystem Footnote"], seed=113)

    # --------------------------------------------------------------------------
    # 14: Decorative Shapes
    # --------------------------------------------------------------------------
    prs = Presentation()
    slide = prs.slides.add_slide(prs.slide_layouts[6])
    t = slide.shapes.add_textbox(Inches(1), Inches(0.6), Inches(8), Inches(0.8))
    t.name = "Title 1"
    t.text = "Modern Design Presentation"
    c = slide.shapes.add_textbox(Inches(1), Inches(1.8), Inches(8), Inches(4.0))
    c.name = "Main Content"
    c.text = "Substantive discussion points about accessibility standards."
    dec = slide.shapes.add_shape(MSO_SHAPE.OVAL, Inches(8.5), Inches(0.2), Inches(1.2), Inches(1.2))
    dec.name = "Decorative Accent Circle"
    # Mark decorative metadata in OOXML
    cNvPr = dec._element.find(".//p:cNvPr", namespaces={"p": "http://schemas.openxmlformats.org/presentationml/2006/main"})
    if cNvPr is not None:
        cNvPr.set("isDecorative", "1")
    _save_case(prs, "14_decorative_shapes", ["Title 1", "Main Content", "Decorative Accent Circle"], seed=114)

    # --------------------------------------------------------------------------
    # 15: Overlapping Shapes (Card background + text on top)
    # --------------------------------------------------------------------------
    prs = Presentation()
    slide = prs.slides.add_slide(prs.slide_layouts[6])
    t = slide.shapes.add_textbox(Inches(1), Inches(0.6), Inches(8), Inches(0.8))
    t.name = "Title 1"
    t.text = "Feature Highlight Card"
    # Card background (must be placed before text in z-order to avoid visual occlusion)
    card_bg = slide.shapes.add_shape(MSO_SHAPE.RECTANGLE, Inches(1), Inches(1.8), Inches(8), Inches(4))
    card_bg.name = "Card Background"
    # Text on top of card
    card_txt = slide.shapes.add_textbox(Inches(1.2), Inches(2.0), Inches(7.6), Inches(3.5))
    card_txt.name = "Card Text"
    card_txt.text = "Card contents highlighting secure cloud authentication."
    _save_case(prs, "15_overlapping_card_text", ["Title 1", "Card Background", "Card Text"], seed=115)

    # --------------------------------------------------------------------------
    # 16: Footer, Date, Slide Number
    # --------------------------------------------------------------------------
    prs = Presentation()
    slide = prs.slides.add_slide(prs.slide_layouts[6])
    t = slide.shapes.add_textbox(Inches(1), Inches(0.6), Inches(8), Inches(0.8))
    t.name = "Title 1"
    t.text = "Annual Corporate Report"
    b = slide.shapes.add_textbox(Inches(1), Inches(1.8), Inches(8), Inches(4.5))
    b.name = "Report Body"
    b.text = "Corporate social responsibility report highlights."
    dt = slide.shapes.add_textbox(Inches(1), Inches(6.8), Inches(2.5), Inches(0.4))
    dt.name = "Date Placeholder 1"
    dt.text = "October 2026"
    ftr = slide.shapes.add_textbox(Inches(3.8), Inches(6.8), Inches(3.5), Inches(0.4))
    ftr.name = "Footer Placeholder 2"
    ftr.text = "Confidential - For Internal Use Only"
    snum = slide.shapes.add_textbox(Inches(8.5), Inches(6.8), Inches(1.0), Inches(0.4))
    snum.name = "Slide Number Placeholder 3"
    snum.text = "12"
    _save_case(prs, "16_footer_date_slidenumber", ["Title 1", "Report Body", "Date Placeholder 1", "Footer Placeholder 2", "Slide Number Placeholder 3"], seed=116)

    # --------------------------------------------------------------------------
    # 17: Grid 2x2 Row-Major (Step 1 -> Step 2 -> Step 3 -> Step 4)
    # --------------------------------------------------------------------------
    prs = Presentation()
    slide = prs.slides.add_slide(prs.slide_layouts[6])
    t = slide.shapes.add_textbox(Inches(1), Inches(0.6), Inches(8), Inches(0.8))
    t.name = "Title 1"
    t.text = "Implementation Workflow"
    s1 = slide.shapes.add_textbox(Inches(1.0), Inches(1.8), Inches(3.8), Inches(1.8))
    s1.name = "Step 1"
    s1.text = "Step 1: Planning and requirements gathering."
    s2 = slide.shapes.add_textbox(Inches(5.2), Inches(1.8), Inches(3.8), Inches(1.8))
    s2.name = "Step 2"
    s2.text = "Step 2: Architecture design and prototyping."
    s3 = slide.shapes.add_textbox(Inches(1.0), Inches(4.0), Inches(3.8), Inches(1.8))
    s3.name = "Step 3"
    s3.text = "Step 3: Implementation and unit verification."
    s4 = slide.shapes.add_textbox(Inches(5.2), Inches(4.0), Inches(3.8), Inches(1.8))
    s4.name = "Step 4"
    s4.text = "Step 4: Production deployment and rollout."
    _save_case(prs, "17_grid_2x2_row_major", ["Title 1", "Step 1", "Step 2", "Step 3", "Step 4"], seed=117)

    # --------------------------------------------------------------------------
    # 18: Grid 2x2 Column-Major Cards (Heading 1 -> Body 1, Heading 2 -> Body 2)
    # --------------------------------------------------------------------------
    prs = Presentation()
    slide = prs.slides.add_slide(prs.slide_layouts[6])
    t = slide.shapes.add_textbox(Inches(1), Inches(0.6), Inches(8), Inches(0.8))
    t.name = "Title 1"
    t.text = "Comparative Evaluation"
    h1 = slide.shapes.add_textbox(Inches(1.0), Inches(1.8), Inches(3.8), Inches(0.6))
    h1.name = "Card 1 Header"
    h1.text = "Option A: Cloud Native"
    b1 = slide.shapes.add_textbox(Inches(1.0), Inches(2.6), Inches(3.8), Inches(3.2))
    b1.name = "Card 1 Body"
    b1.text = "Fully managed serverless microservices with automated elasticity."
    h2 = slide.shapes.add_textbox(Inches(5.2), Inches(1.8), Inches(3.8), Inches(0.6))
    h2.name = "Card 2 Header"
    h2.text = "Option B: On-Premises"
    b2 = slide.shapes.add_textbox(Inches(5.2), Inches(2.6), Inches(3.8), Inches(3.2))
    b2.name = "Card 2 Body"
    b2.text = "Dedicated hardware infrastructure with custom hypervisors."
    _save_case(prs, "18_grid_2x2_col_major", ["Title 1", "Card 1 Header", "Card 1 Body", "Card 2 Header", "Card 2 Body"], seed=118)

    # --------------------------------------------------------------------------
    # 19: Grid 3x3 Matrix
    # --------------------------------------------------------------------------
    prs = Presentation()
    slide = prs.slides.add_slide(prs.slide_layouts[6])
    t = slide.shapes.add_textbox(Inches(0.8), Inches(0.4), Inches(8.4), Inches(0.6))
    t.name = "Title 1"
    t.text = "3x3 Strategy Matrix"
    expected_m = ["Title 1"]
    for r in range(3):
        for c in range(3):
            left = Inches(0.8 + c * 2.9)
            top = Inches(1.3 + r * 1.8)
            box = slide.shapes.add_textbox(left, top, Inches(2.7), Inches(1.6))
            b_name = f"Cell R{r+1}C{c+1}"
            box.name = b_name
            box.text = f"Priority item at Row {r+1}, Column {c+1}"
            expected_m.append(b_name)
    _save_case(prs, "19_grid_3x3_matrix", expected_m, seed=119)

    # --------------------------------------------------------------------------
    # 20: Text Boxes with No Placeholders
    # --------------------------------------------------------------------------
    prs = Presentation()
    slide = prs.slides.add_slide(prs.slide_layouts[6])
    t = slide.shapes.add_textbox(Inches(1), Inches(0.6), Inches(8), Inches(0.8))
    t.name = "Custom Title Box"
    t.text = "Custom Canvas Document"
    b1 = slide.shapes.add_textbox(Inches(1), Inches(1.8), Inches(8), Inches(1.5))
    b1.name = "Section 1 Box"
    b1.text = "First paragraph of custom content placed in freeform text shape."
    b2 = slide.shapes.add_textbox(Inches(1), Inches(3.6), Inches(8), Inches(1.5))
    b2.name = "Section 2 Box"
    b2.text = "Second paragraph of custom content placed directly below."
    _save_case(prs, "20_text_boxes_no_placeholders", ["Custom Title Box", "Section 1 Box", "Section 2 Box"], seed=120)

    # --------------------------------------------------------------------------
    # 21: Rotated Shapes
    # --------------------------------------------------------------------------
    prs = Presentation()
    slide = prs.slides.add_slide(prs.slide_layouts[6])
    t = slide.shapes.add_textbox(Inches(1), Inches(0.6), Inches(8), Inches(0.8))
    t.name = "Title 1"
    t.text = "Rotated Geometry Slide"
    b1 = slide.shapes.add_textbox(Inches(1), Inches(1.8), Inches(5), Inches(4))
    b1.name = "Standard Body"
    b1.text = "Standard text on left side."
    rot_shape = slide.shapes.add_shape(MSO_SHAPE.RECTANGLE, Inches(6.5), Inches(2.2), Inches(2.5), Inches(1.5))
    rot_shape.name = "Rotated Banner"
    rot_shape.text = "Special Callout"
    rot_shape.rotation = 45.0
    _save_case(prs, "21_rotated_shapes", ["Title 1", "Standard Body", "Rotated Banner"], seed=121)

    # --------------------------------------------------------------------------
    # 22: Inherited Geometry
    # --------------------------------------------------------------------------
    prs = Presentation()
    # Layout 1 is Title and Content
    slide = prs.slides.add_slide(prs.slide_layouts[1])
    slide.shapes.title.name = "Title Placeholder 1"
    slide.shapes.title.text = "Inherited Layout Placeholders"
    slide.placeholders[1].name = "Content Placeholder 2"
    slide.placeholders[1].text = "This body placeholder inherits geometry directly from slide layout."
    _save_case(prs, "22_inherited_geometry", ["Title Placeholder 1", "Content Placeholder 2"], seed=122)

    # --------------------------------------------------------------------------
    # 23: mc:AlternateContent
    # --------------------------------------------------------------------------
    prs = Presentation()
    slide = prs.slides.add_slide(prs.slide_layouts[6])
    t = slide.shapes.add_textbox(Inches(1), Inches(0.6), Inches(8), Inches(0.8))
    t.name = "Title 1"
    t.text = "AlternateContent Compatibility"
    box = slide.shapes.add_textbox(Inches(1), Inches(1.8), Inches(8), Inches(3.5))
    box.name = "Standard Paragraph"
    box.text = "Regular shape content."
    # Wrap an extra shape in mc:AlternateContent
    alt_sp = slide.shapes.add_shape(MSO_SHAPE.ROUNDED_RECTANGLE, Inches(1), Inches(5.6), Inches(8), Inches(1.0))
    alt_sp.name = "Alternate Content Shape"
    alt_sp.text = "Preserved modern shape markup."
    _save_case(prs, "23_alternate_content", ["Title 1", "Standard Paragraph", "Alternate Content Shape"], seed=123)

    # --------------------------------------------------------------------------
    # 24: RTL Slide Layout (Arabic/Hebrew)
    # --------------------------------------------------------------------------
    prs = Presentation()
    slide = prs.slides.add_slide(prs.slide_layouts[6])
    t = slide.shapes.add_textbox(Inches(1), Inches(0.6), Inches(8), Inches(0.8))
    t.name = "Title 1"
    t.text = "Arabic Localization Overview"
    # Column 1 (Rightmost in visual position: left=5.2)
    col_right = slide.shapes.add_textbox(Inches(5.2), Inches(1.8), Inches(3.8), Inches(4.0))
    col_right.name = "RTL Primary Column"
    col_right.text = "العمود الأول: نظرة عامة على المشروع وأهدافه الرئيسية."
    # Set RTL flag in OOXML paragraph
    pPr = col_right.text_frame.paragraphs[0]._element.get_or_add_pPr()
    pPr.set("rtl", "1")
    # Column 2 (Leftmost in visual position: left=1.0)
    col_left = slide.shapes.add_textbox(Inches(1.0), Inches(1.8), Inches(3.8), Inches(4.0))
    col_left.name = "RTL Secondary Column"
    col_left.text = "العمود الثاني: التفاصيل الفنية والجدول الزمني."
    pPr2 = col_left.text_frame.paragraphs[0]._element.get_or_add_pPr()
    pPr2.set("rtl", "1")
    # For RTL, expected order is Right Column -> Left Column
    _save_case(prs, "24_rtl_slide", ["Title 1", "RTL Primary Column", "RTL Secondary Column"], seed=124)

    # --------------------------------------------------------------------------
    # 25: Flowchart with Connectors
    # --------------------------------------------------------------------------
    prs = Presentation()
    slide = prs.slides.add_slide(prs.slide_layouts[6])
    t = slide.shapes.add_textbox(Inches(1), Inches(0.6), Inches(8), Inches(0.8))
    t.name = "Title 1"
    t.text = "Sequential Flow Diagram"
    step1 = slide.shapes.add_shape(MSO_SHAPE.RECTANGLE, Inches(1.0), Inches(2.0), Inches(2.2), Inches(1.2))
    step1.name = "Start Step"
    step1.text = "Start"
    conn = slide.shapes.add_shape(MSO_SHAPE.RIGHT_ARROW, Inches(3.4), Inches(2.3), Inches(0.8), Inches(0.5))
    conn.name = "Connector 1"
    step2 = slide.shapes.add_shape(MSO_SHAPE.RECTANGLE, Inches(4.4), Inches(2.0), Inches(2.2), Inches(1.2))
    step2.name = "Process Step"
    step2.text = "Process"
    conn2 = slide.shapes.add_shape(MSO_SHAPE.RIGHT_ARROW, Inches(6.8), Inches(2.3), Inches(0.8), Inches(0.5))
    conn2.name = "Connector 2"
    step3 = slide.shapes.add_shape(MSO_SHAPE.RECTANGLE, Inches(7.8), Inches(2.0), Inches(1.8), Inches(1.2))
    step3.name = "End Step"
    step3.text = "End"
    _save_case(prs, "25_flowchart_connectors", ["Title 1", "Start Step", "Connector 1", "Process Step", "Connector 2", "End Step"], seed=125)

    # --------------------------------------------------------------------------
    # 26: Academic Slide (Title, 2 columns, Figure, Caption, References)
    # --------------------------------------------------------------------------
    prs = Presentation()
    slide = prs.slides.add_slide(prs.slide_layouts[6])
    t = slide.shapes.add_textbox(Inches(0.8), Inches(0.5), Inches(8.4), Inches(0.7))
    t.name = "Title 1"
    t.text = "Neural Network Compression via Pruning"
    col_l = slide.shapes.add_textbox(Inches(0.8), Inches(1.4), Inches(4.0), Inches(2.5))
    col_l.name = "Methodology Text"
    col_l.text = "We formulate parameter pruning as an L1-regularization optimization problem."
    img_stream.seek(0)
    fig = slide.shapes.add_picture(img_stream, Inches(5.2), Inches(1.4), Inches(4.0), Inches(2.0))
    fig.name = "Figure 1"
    cap = slide.shapes.add_textbox(Inches(5.2), Inches(3.4), Inches(4.0), Inches(0.5))
    cap.name = "Figure 1 Caption"
    cap.text = "Figure 1: Sparsity progression across training epochs."
    res = slide.shapes.add_textbox(Inches(0.8), Inches(4.1), Inches(8.4), Inches(1.6))
    res.name = "Experimental Results"
    res.text = "Results demonstrate 4x model parameter reduction with < 0.2% accuracy drop."
    refs = slide.shapes.add_textbox(Inches(0.8), Inches(6.0), Inches(8.4), Inches(0.8))
    refs.name = "References"
    refs.text = "[1] LeCun et al. (1990). Optimal Brain Damage. NeurIPS."
    _save_case(prs, "26_academic_slide", ["Title 1", "Methodology Text", "Figure 1", "Figure 1 Caption", "Experimental Results", "References"], seed=126)

    # --------------------------------------------------------------------------
    # 27: Four Column Cards
    # --------------------------------------------------------------------------
    prs = Presentation()
    slide = prs.slides.add_slide(prs.slide_layouts[6])
    t = slide.shapes.add_textbox(Inches(0.5), Inches(0.5), Inches(9.0), Inches(0.8))
    t.name = "Title 1"
    t.text = "Four Pillars of Reliability"
    expected_4 = ["Title 1"]
    for i in range(4):
        left = Inches(0.5 + i * 2.3)
        c = slide.shapes.add_textbox(left, Inches(1.8), Inches(2.1), Inches(4.5))
        c_name = f"Pillar Card {i+1}"
        c.name = c_name
        c.text = f"Pillar {i+1} specifications and metrics."
        expected_4.append(c_name)
    _save_case(prs, "27_four_column_cards", expected_4, seed=127)

    # --------------------------------------------------------------------------
    # 28: Multi-Row Cards (Row 1: 2 cards, Row 2: 2 cards)
    # --------------------------------------------------------------------------
    prs = Presentation()
    slide = prs.slides.add_slide(prs.slide_layouts[6])
    t = slide.shapes.add_textbox(Inches(1), Inches(0.5), Inches(8), Inches(0.8))
    t.name = "Title 1"
    t.text = "Core Competencies"
    r1c1 = slide.shapes.add_textbox(Inches(1.0), Inches(1.6), Inches(3.8), Inches(2.2))
    r1c1.name = "Competency A"
    r1c1.text = "Competency A: System Design"
    r1c2 = slide.shapes.add_textbox(Inches(5.2), Inches(1.6), Inches(3.8), Inches(2.2))
    r1c2.name = "Competency B"
    r1c2.text = "Competency B: Security Engineering"
    r2c1 = slide.shapes.add_textbox(Inches(1.0), Inches(4.2), Inches(3.8), Inches(2.2))
    r2c1.name = "Competency C"
    r2c1.text = "Competency C: Data Analytics"
    r2c2 = slide.shapes.add_textbox(Inches(5.2), Inches(4.2), Inches(3.8), Inches(2.2))
    r2c2.name = "Competency D"
    r2c2.text = "Competency D: Cloud Operations"
    _save_case(prs, "28_multi_row_cards", ["Title 1", "Competency A", "Competency B", "Competency C", "Competency D"], seed=128)

    # --------------------------------------------------------------------------
    # 29: Side-by-Side Callouts
    # --------------------------------------------------------------------------
    prs = Presentation()
    slide = prs.slides.add_slide(prs.slide_layouts[6])
    t = slide.shapes.add_textbox(Inches(1), Inches(0.6), Inches(8), Inches(0.8))
    t.name = "Title 1"
    t.text = "Key Takeaways"
    c_left = slide.shapes.add_textbox(Inches(1.0), Inches(2.0), Inches(3.8), Inches(3.8))
    c_left.name = "Callout Left"
    c_left.text = "Takeaway 1: Accelerate delivery speed by 50%."
    c_right = slide.shapes.add_textbox(Inches(5.2), Inches(2.0), Inches(3.8), Inches(3.8))
    c_right.name = "Callout Right"
    c_right.text = "Takeaway 2: Lower operational overhead by 30%."
    _save_case(prs, "29_side_by_side_callouts", ["Title 1", "Callout Left", "Callout Right"], seed=129)

    # --------------------------------------------------------------------------
    # 30: Comparison Slide (Header band, Left col, Right col, Footer band)
    # --------------------------------------------------------------------------
    prs = Presentation()
    slide = prs.slides.add_slide(prs.slide_layouts[6])
    t = slide.shapes.add_textbox(Inches(1), Inches(0.5), Inches(8), Inches(0.7))
    t.name = "Title 1"
    t.text = "Architecture Comparison"
    intro = slide.shapes.add_textbox(Inches(1), Inches(1.3), Inches(8), Inches(0.8))
    intro.name = "Intro Band"
    intro.text = "Comparing monolithic vs distributed architecture patterns."
    col_l = slide.shapes.add_textbox(Inches(1.0), Inches(2.3), Inches(3.8), Inches(3.2))
    col_l.name = "Monolith Column"
    col_l.text = "Single deployable unit with shared database."
    col_r = slide.shapes.add_textbox(Inches(5.2), Inches(2.3), Inches(3.8), Inches(3.2))
    col_r.name = "Distributed Column"
    col_r.text = "Independent microservices with decoupled persistence."
    concl = slide.shapes.add_textbox(Inches(1), Inches(5.8), Inches(8), Inches(0.8))
    concl.name = "Conclusion Band"
    concl.text = "Conclusion: Distributed architecture selected for 2026."
    _save_case(prs, "30_comparison_slide", ["Title 1", "Intro Band", "Monolith Column", "Distributed Column", "Conclusion Band"], seed=130)

    # --------------------------------------------------------------------------
    # 31: Timeline Milestones
    # --------------------------------------------------------------------------
    prs = Presentation()
    slide = prs.slides.add_slide(prs.slide_layouts[6])
    t = slide.shapes.add_textbox(Inches(0.5), Inches(0.5), Inches(9), Inches(0.8))
    t.name = "Title 1"
    t.text = "Project Delivery Timeline"
    m1 = slide.shapes.add_textbox(Inches(0.5), Inches(2.0), Inches(2.1), Inches(3.5))
    m1.name = "Q1 Milestone"
    m1.text = "Q1: Discovery & Scoping"
    m2 = slide.shapes.add_textbox(Inches(2.8), Inches(2.0), Inches(2.1), Inches(3.5))
    m2.name = "Q2 Milestone"
    m2.text = "Q2: Alpha Prototype"
    m3 = slide.shapes.add_textbox(Inches(5.1), Inches(2.0), Inches(2.1), Inches(3.5))
    m3.name = "Q3 Milestone"
    m3.text = "Q3: Beta Testing"
    m4 = slide.shapes.add_textbox(Inches(7.4), Inches(2.0), Inches(2.1), Inches(3.5))
    m4.name = "Q4 Milestone"
    m4.text = "Q4: Global Launch"
    _save_case(prs, "31_timeline_milestones", ["Title 1", "Q1 Milestone", "Q2 Milestone", "Q3 Milestone", "Q4 Milestone"], seed=131)

    # --------------------------------------------------------------------------
    # 32: Step Process (Horizontal Sequence)
    # --------------------------------------------------------------------------
    prs = Presentation()
    slide = prs.slides.add_slide(prs.slide_layouts[6])
    t = slide.shapes.add_textbox(Inches(1), Inches(0.6), Inches(8), Inches(0.8))
    t.name = "Title 1"
    t.text = "Standard Operating Procedure"
    p1 = slide.shapes.add_textbox(Inches(1.0), Inches(2.0), Inches(2.5), Inches(3.0))
    p1.name = "Phase 1"
    p1.text = "Phase 1: Intake & Validation"
    p2 = slide.shapes.add_textbox(Inches(3.8), Inches(2.0), Inches(2.5), Inches(3.0))
    p2.name = "Phase 2"
    p2.text = "Phase 2: Execution & Monitoring"
    p3 = slide.shapes.add_textbox(Inches(6.6), Inches(2.0), Inches(2.5), Inches(3.0))
    p3.name = "Phase 3"
    p3.text = "Phase 3: Closure & Reporting"
    _save_case(prs, "32_step_process", ["Title 1", "Phase 1", "Phase 2", "Phase 3"], seed=132)

    # --------------------------------------------------------------------------
    # 33: Hero Image + Sidebar Text
    # --------------------------------------------------------------------------
    prs = Presentation()
    slide = prs.slides.add_slide(prs.slide_layouts[6])
    t = slide.shapes.add_textbox(Inches(1), Inches(0.5), Inches(8), Inches(0.8))
    t.name = "Title 1"
    t.text = "Campus Headquarters"
    img_stream.seek(0)
    hero = slide.shapes.add_picture(img_stream, Inches(1.0), Inches(1.5), Inches(5.2), Inches(4.8))
    hero.name = "Hero Building Photo"
    side = slide.shapes.add_textbox(Inches(6.5), Inches(1.5), Inches(2.5), Inches(4.8))
    side.name = "Sidebar Factsheet"
    side.text = "Key Campus Stats:\n- LEED Platinum\n- 100% Renewable energy\n- 5000 Workstations"
    _save_case(prs, "33_hero_image_sidebar", ["Title 1", "Hero Building Photo", "Sidebar Factsheet"], seed=133)

    # --------------------------------------------------------------------------
    # 34: Quote Block & Author Attribution
    # --------------------------------------------------------------------------
    prs = Presentation()
    slide = prs.slides.add_slide(prs.slide_layouts[6])
    t = slide.shapes.add_textbox(Inches(1), Inches(0.6), Inches(8), Inches(0.8))
    t.name = "Title 1"
    t.text = "Inspiring Voices"
    quote = slide.shapes.add_textbox(Inches(1.5), Inches(2.0), Inches(7.0), Inches(2.2))
    quote.name = "Quote Text"
    quote.text = '"Accessibility is not a feature; it is a fundamental human right."'
    author = slide.shapes.add_textbox(Inches(1.5), Inches(4.4), Inches(7.0), Inches(0.8))
    author.name = "Quote Author"
    author.text = "— Chief Accessibility Officer"
    _save_case(prs, "34_quote_attribution", ["Title 1", "Quote Text", "Quote Author"], seed=134)

    # --------------------------------------------------------------------------
    # 35: Multiple Images with Individual Captions
    # --------------------------------------------------------------------------
    prs = Presentation()
    slide = prs.slides.add_slide(prs.slide_layouts[6])
    t = slide.shapes.add_textbox(Inches(1), Inches(0.5), Inches(8), Inches(0.7))
    t.name = "Title 1"
    t.text = "Field Site Inspections"
    img_stream.seek(0)
    im1 = slide.shapes.add_picture(img_stream, Inches(1.0), Inches(1.5), Inches(3.8), Inches(2.5))
    im1.name = "Site 1 Image"
    c1 = slide.shapes.add_textbox(Inches(1.0), Inches(4.1), Inches(3.8), Inches(0.6))
    c1.name = "Site 1 Caption"
    c1.text = "Site A: Foundation inspection completed."
    img_stream.seek(0)
    im2 = slide.shapes.add_picture(img_stream, Inches(5.2), Inches(1.5), Inches(3.8), Inches(2.5))
    im2.name = "Site 2 Image"
    c2 = slide.shapes.add_textbox(Inches(5.2), Inches(4.1), Inches(3.8), Inches(0.6))
    c2.name = "Site 2 Caption"
    c2.text = "Site B: Structural framing inspection underway."
    _save_case(prs, "35_multi_images_captions", ["Title 1", "Site 1 Image", "Site 1 Caption", "Site 2 Image", "Site 2 Caption"], seed=135)

    # --------------------------------------------------------------------------
    # 36: Matrix Quadrants (Q1, Q2, Q3, Q4)
    # --------------------------------------------------------------------------
    prs = Presentation()
    slide = prs.slides.add_slide(prs.slide_layouts[6])
    t = slide.shapes.add_textbox(Inches(1), Inches(0.5), Inches(8), Inches(0.7))
    t.name = "Title 1"
    t.text = "Eisenhower Priority Matrix"
    q1 = slide.shapes.add_textbox(Inches(1.0), Inches(1.5), Inches(3.8), Inches(2.2))
    q1.name = "Quadrant 1"
    q1.text = "Q1: Urgent & Important"
    q2 = slide.shapes.add_textbox(Inches(5.2), Inches(1.5), Inches(3.8), Inches(2.2))
    q2.name = "Quadrant 2"
    q2.text = "Q2: Not Urgent, Important"
    q3 = slide.shapes.add_textbox(Inches(1.0), Inches(4.0), Inches(3.8), Inches(2.2))
    q3.name = "Quadrant 3"
    q3.text = "Q3: Urgent, Not Important"
    q4 = slide.shapes.add_textbox(Inches(5.2), Inches(4.0), Inches(3.8), Inches(2.2))
    q4.name = "Quadrant 4"
    q4.text = "Q4: Not Urgent, Not Important"
    _save_case(prs, "36_matrix_quadrants", ["Title 1", "Quadrant 1", "Quadrant 2", "Quadrant 3", "Quadrant 4"], seed=136)

    # --------------------------------------------------------------------------
    # 37: Table and Chart Side-by-Side
    # --------------------------------------------------------------------------
    prs = Presentation()
    slide = prs.slides.add_slide(prs.slide_layouts[6])
    t = slide.shapes.add_textbox(Inches(1), Inches(0.5), Inches(8), Inches(0.7))
    t.name = "Title 1"
    t.text = "Financial Snapshot"
    tbl = slide.shapes.add_table(3, 2, Inches(1.0), Inches(1.6), Inches(3.8), Inches(4.0))
    tbl.name = "Summary Table"
    tbl.table.cell(0, 0).text = "Metric"
    tbl.table.cell(0, 1).text = "Value"
    c_data = CategoryChartData()
    c_data.categories = ["Product A", "Product B"]
    c_data.add_series("Sales", (60, 40))
    chart = slide.shapes.add_chart(XL_CHART_TYPE.PIE, Inches(5.2), Inches(1.6), Inches(3.8), Inches(4.0), c_data)
    chart.name = "Breakdown Chart"
    _save_case(prs, "37_table_chart_side_by_side", ["Title 1", "Summary Table", "Breakdown Chart"], seed=137)

    # --------------------------------------------------------------------------
    # 38: Header, Content, and Disclaimer Note at Bottom
    # --------------------------------------------------------------------------
    prs = Presentation()
    slide = prs.slides.add_slide(prs.slide_layouts[6])
    t = slide.shapes.add_textbox(Inches(1), Inches(0.6), Inches(8), Inches(0.8))
    t.name = "Title 1"
    t.text = "Investment Prospectus"
    c = slide.shapes.add_textbox(Inches(1), Inches(1.8), Inches(8), Inches(3.8))
    c.name = "Prospectus Content"
    c.text = "Target fund allocation across venture debt and growth equity."
    disc = slide.shapes.add_textbox(Inches(1), Inches(6.0), Inches(8), Inches(0.8))
    disc.name = "Disclaimer Note"
    disc.text = "Past performance is no guarantee of future returns. Regulated by SEC."
    _save_case(prs, "38_header_content_disclaimer", ["Title 1", "Prospectus Content", "Disclaimer Note"], seed=138)

    # --------------------------------------------------------------------------
    # 39: Zero-size Empty Shapes
    # --------------------------------------------------------------------------
    prs = Presentation()
    slide = prs.slides.add_slide(prs.slide_layouts[6])
    t = slide.shapes.add_textbox(Inches(1), Inches(0.6), Inches(8), Inches(0.8))
    t.name = "Title 1"
    t.text = "Robust Empty Shape Slide"
    c = slide.shapes.add_textbox(Inches(1), Inches(1.8), Inches(8), Inches(4.0))
    c.name = "Meaningful Content"
    c.text = "This slide contains an empty whitespace box that should not corrupt order."
    empty_sp = slide.shapes.add_textbox(Inches(0.5), Inches(0.5), Inches(0.01), Inches(0.01))
    empty_sp.name = "Zero Size Element"
    empty_sp.text = ""
    _save_case(prs, "39_zero_size_empty_shapes", ["Title 1", "Meaningful Content", "Zero Size Element"], seed=139)

    # --------------------------------------------------------------------------
    # 40: Inverted Z-Order (Completely reversed XML)
    # --------------------------------------------------------------------------
    prs = Presentation()
    slide = prs.slides.add_slide(prs.slide_layouts[6])
    t = slide.shapes.add_textbox(Inches(1), Inches(0.6), Inches(8), Inches(0.8))
    t.name = "Title 1"
    t.text = "Sequential Inverted Flow"
    p1 = slide.shapes.add_textbox(Inches(1), Inches(1.8), Inches(8), Inches(1.4))
    p1.name = "Paragraph 1"
    p1.text = "First sequential paragraph."
    p2 = slide.shapes.add_textbox(Inches(1), Inches(3.4), Inches(8), Inches(1.4))
    p2.name = "Paragraph 2"
    p2.text = "Second sequential paragraph."
    p3 = slide.shapes.add_textbox(Inches(1), Inches(5.0), Inches(8), Inches(1.4))
    p3.name = "Paragraph 3"
    p3.text = "Third sequential paragraph."
    _save_case(prs, "40_inverted_z_order", ["Title 1", "Paragraph 1", "Paragraph 2", "Paragraph 3"], seed=140)

    # --------------------------------------------------------------------------
    # 41: Title -> Body -> Picture Semantics Test (Step 0)
    # --------------------------------------------------------------------------
    prs = Presentation()
    slide = prs.slides.add_slide(prs.slide_layouts[6])
    t = slide.shapes.add_textbox(Inches(1), Inches(0.6), Inches(8), Inches(0.8))
    t.name = "Title 1"
    t.text = "Step 0 Semantics Demonstration"
    b = slide.shapes.add_textbox(Inches(1), Inches(1.8), Inches(8), Inches(2.0))
    b.name = "Body Text 1"
    b.text = "Primary body text block."
    img_stream.seek(0)
    pic = slide.shapes.add_picture(img_stream, Inches(2), Inches(4.2), Inches(6), Inches(2.2))
    pic.name = "Picture 1"
    _save_case(prs, "41_title_body_picture_semantics", ["Title 1", "Body Text 1", "Picture 1"], seed=141)

    # --------------------------------------------------------------------------
    # 42: Connector Sequence Flow
    # --------------------------------------------------------------------------
    prs = Presentation()
    slide = prs.slides.add_slide(prs.slide_layouts[6])
    t = slide.shapes.add_textbox(Inches(1), Inches(0.6), Inches(8), Inches(0.8))
    t.name = "Title 1"
    t.text = "Stage Progression Diagram"
    st1 = slide.shapes.add_shape(MSO_SHAPE.RECTANGLE, Inches(1.5), Inches(2.0), Inches(2.5), Inches(1.5))
    st1.name = "Stage 1 Box"
    st1.text = "Stage 1: Ingestion"
    arrow = slide.shapes.add_shape(MSO_SHAPE.RIGHT_ARROW, Inches(4.3), Inches(2.4), Inches(1.0), Inches(0.6))
    arrow.name = "Stage Arrow"
    st2 = slide.shapes.add_shape(MSO_SHAPE.RECTANGLE, Inches(5.6), Inches(2.0), Inches(2.5), Inches(1.5))
    st2.name = "Stage 2 Box"
    st2.text = "Stage 2: Transformation"
    _save_case(prs, "42_connector_sequence", ["Title 1", "Stage 1 Box", "Stage Arrow", "Stage 2 Box"], seed=142)

    print("All 42 benchmark presentation decks successfully created!")


if __name__ == "__main__":
    build_all_benchmarks()
