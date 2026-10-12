"""Builders for representative equation test decks and fake MathType OLE objects."""
from __future__ import annotations

import io
import math
import struct
from copy import deepcopy

from lxml import etree
from pptx import Presentation
from pptx.chart.data import CategoryChartData
from pptx.enum.chart import XL_CHART_TYPE
from pptx.util import Inches

M = "http://schemas.openxmlformats.org/officeDocument/2006/math"
A14 = "http://schemas.microsoft.com/office/drawing/2010/main"
MC = "http://schemas.openxmlformats.org/markup-compatibility/2006"
P = "http://schemas.openxmlformats.org/presentationml/2006/main"
A = "http://schemas.openxmlformats.org/drawingml/2006/main"

ENDOFCHAIN, FREESECT, FATSECT, NOSTREAM = 0xFFFFFFFE, 0xFFFFFFFF, 0xFFFFFFFD, 0xFFFFFFFF


def build_ole_compound_file(streams: dict[str, bytes]) -> bytes:
    """Minimal CFB v3 writer (streams padded to 4 KiB so no mini stream is needed)."""
    names = list(streams)
    datas = [streams[n].ljust(4096, b"\0") for n in names]
    sectors_per = [math.ceil(len(d) / 512) for d in datas]
    dir_entries = 1 + len(names)
    dir_sectors = math.ceil(dir_entries / 4)
    first_data = 1 + dir_sectors
    fat = [FATSECT] + [i + 2 if i + 2 < 1 + dir_sectors else ENDOFCHAIN for i in range(dir_sectors)]
    starts, cur = [], first_data
    for n in sectors_per:
        starts.append(cur)
        fat += [cur + i + 1 for i in range(n - 1)] + [ENDOFCHAIN]
        cur += n
    assert len(fat) <= 128
    fat += [FREESECT] * (128 - len(fat))

    header = bytearray(512)
    header[0:8] = bytes.fromhex("D0CF11E0A1B11AE1")
    struct.pack_into("<HHHHH", header, 24, 0x3E, 3, 0xFFFE, 9, 6)
    struct.pack_into("<IIIIIIIII", header, 40, 0, 1, 1, 0, 4096, ENDOFCHAIN, 0, ENDOFCHAIN, 0)
    difat = [0] + [FREESECT] * 108
    struct.pack_into("<109I", header, 76, *difat)

    def entry(name, typ, child, start, size, right=NOSTREAM):
        e = bytearray(128)
        enc = name.encode("utf-16-le") + b"\0\0" if name else b""
        e[0:len(enc)] = enc
        struct.pack_into("<HBBIII", e, 64, len(enc), typ, 1, NOSTREAM, right, child)
        struct.pack_into("<IQ", e, 116, start, size)
        return bytes(e)

    entries = [entry("Root Entry", 5, 1 if names else NOSTREAM, ENDOFCHAIN, 0)]
    for i, n in enumerate(names):
        right = i + 2 if i + 1 < len(names) else NOSTREAM
        entries.append(entry(n, 2, NOSTREAM, starts[i], len(datas[i]), right))
    while len(entries) % 4:
        entries.append(entry("", 0, NOSTREAM, 0, 0))
    body = struct.pack("<128I", *fat) + b"".join(entries)
    for d in datas:
        body += d.ljust(math.ceil(len(d) / 512) * 512, b"\0")
    return bytes(header) + body


def fake_mathtype_ole() -> bytes:
    return build_ole_compound_file({"Equation Native": b"\x1c\x00MTEF-test-payload"})


PNG_1PX = bytes.fromhex(
    "89504e470d0a1a0a0000000d4948445200000001000000010806000000"
    "1f15c4890000000d49444154789c6360000002000154a24f5d0000000049454e44ae426082"
)


def r(text: str) -> str:
    return f'<m:r><a:rPr xmlns:a="{A}" lang="en-US" sz="2800"/><m:t>{text}</m:t></m:r>'


FRACTION = f"<m:f><m:num>{r('a')}</m:num><m:den>{r('b')}</m:den></m:f>"
RADICAL = f"<m:rad><m:radPr><m:degHide m:val='1'/></m:radPr><m:deg/><m:e>{r('x')}</m:e></m:rad>"
SUPSUB = (
    f"<m:sSup><m:e>{r('x')}</m:e><m:sup>{r('2')}</m:sup></m:sSup>{r('+')}"
    f"<m:sSub><m:e>{r('y')}</m:e><m:sub>{r('1')}</m:sub></m:sSub>"
)
INTEGRAL = (
    f"<m:nary><m:naryPr><m:chr m:val='∫'/></m:naryPr><m:sub>{r('0')}</m:sub><m:sup>{r('1')}</m:sup>"
    f"<m:e>{r('x')}{r('dx')}</m:e></m:nary>"
)
MATRIX = (
    "<m:d><m:dPr><m:begChr m:val='['/><m:endChr m:val=']'/></m:dPr><m:e><m:m>"
    f"<m:mr><m:e>{r('1')}</m:e><m:e>{r('0')}</m:e></m:mr><m:mr><m:e>{r('0')}</m:e><m:e>{r('1')}</m:e></m:mr>"
    "</m:m></m:e></m:d>"
)
EQARRAY = f"<m:eqArr><m:e>{r('x=1')}</m:e><m:e>{r('y=2')}</m:e></m:eqArr>"


def _omath_para(*equations: str) -> str:
    inner = "".join(f"<m:oMath>{e}</m:oMath>" for e in equations)
    return f'<a14:m xmlns:a14="{A14}"><m:oMathPara xmlns:m="{M}">{inner}</m:oMathPara></a14:m>'


def add_equation_box(slide, equations: list[str], left=Inches(1), top=Inches(1), text_before: str = "",
                     wrap_alternate: bool = True):
    box = slide.shapes.add_textbox(left, top, Inches(4), Inches(1))
    sp = box._element
    p = sp.find(f".//{{{A}}}p")
    if text_before:
        box.text_frame.paragraphs[0].text = text_before
        p = sp.find(f".//{{{A}}}p")
    p.append(etree.fromstring(_omath_para(*equations)))
    if wrap_alternate:
        fallback = deepcopy(sp)
        for m in fallback.iter(f"{{{A14}}}m"):
            m.getparent().remove(m)
        ac = etree.SubElement(sp.getparent(), f"{{{MC}}}AlternateContent", nsmap={"mc": MC})
        sp.addprevious(ac)
        choice = etree.SubElement(ac, f"{{{MC}}}Choice", Requires="a14", nsmap={"a14": A14})
        choice.append(sp)
        etree.SubElement(ac, f"{{{MC}}}Fallback").append(fallback)
    return box


def build_test_deck(path: str) -> None:
    prs = Presentation()
    blank = prs.slide_layouts[6]

    s1 = prs.slides.add_slide(blank)                     # standalone equations + unrelated content
    add_equation_box(s1, [FRACTION], top=Inches(0.5))
    add_equation_box(s1, [RADICAL], top=Inches(1.7))
    add_equation_box(s1, [SUPSUB, INTEGRAL], top=Inches(2.9))
    tb = s1.shapes.add_textbox(Inches(5), Inches(0.5), Inches(3), Inches(1))
    tb.text_frame.text = "Introduction to trigonometry"
    tb.text_frame.paragraphs[0].runs[0].hyperlink.address = "https://example.com"
    s1.notes_slide.notes_text_frame.text = "Speaker notes"

    s2 = prs.slides.add_slide(blank)                     # matrix, multi-line, inline, table
    add_equation_box(s2, [MATRIX], wrap_alternate=False)
    add_equation_box(s2, [EQARRAY], top=Inches(2.2))
    add_equation_box(s2, [FRACTION], top=Inches(3.4), text_before="The ratio is ")
    tbl = s2.shapes.add_table(2, 2, Inches(5), Inches(1), Inches(3), Inches(1)).table
    tbl.cell(0, 0).text_frame.paragraphs[0]._p.append(etree.fromstring(_omath_para(FRACTION)))
    tbl.cell(1, 1).text = "plain"

    s3 = prs.slides.add_slide(blank)                     # existing MathType, math text, image, chart, group
    s3.shapes.add_ole_object(io.BytesIO(fake_mathtype_ole()), "Equation.DSMT4", Inches(1), Inches(1),
                             Inches(2), Inches(1))
    s3.shapes.add_textbox(Inches(1), Inches(2.5), Inches(3), Inches(1)).text_frame.text = "x^2 + y^2 = 1"
    pic = s3.shapes.add_picture(io.BytesIO(PNG_1PX), Inches(5), Inches(1), Inches(1), Inches(1))
    pic._element.find(f".//{{{P}}}cNvPr").set("descr", "Equation of a circle")
    data = CategoryChartData()
    data.categories = ["A", "B"]
    data.add_series("S", (1, 2))
    s3.shapes.add_chart(XL_CHART_TYPE.COLUMN_CLUSTERED, Inches(5), Inches(3), Inches(3), Inches(2), data)
    grp = s3.shapes.add_group_shape()
    add_equation_box(grp, [FRACTION], top=Inches(4.5), wrap_alternate=False)
    grp.shapes.add_textbox(Inches(1), Inches(6), Inches(2), Inches(0.5)).text_frame.text = "label"

    s4 = prs.slides.add_slide(blank)                     # paragraph-level animation
    animated = add_equation_box(s4, [FRACTION], wrap_alternate=False)
    sid = animated.shape_id
    timing = etree.fromstring(
        f'<p:timing xmlns:p="{P}"><p:tnLst><p:par><p:cTn id="1" dur="indefinite" nodeType="tmRoot">'
        f'<p:childTnLst><p:set><p:cBhvr><p:cTn id="2" dur="1"/><p:tgtEl><p:spTgt spid="{sid}">'
        f'<p:txEl><p:pRg st="0" end="0"/></p:txEl></p:spTgt></p:tgtEl><p:attrNameLst><p:attrName>'
        f'style.visibility</p:attrName></p:attrNameLst></p:cBhvr><p:to><p:strVal val="visible"/></p:to>'
        f'</p:set></p:childTnLst></p:cTn></p:par></p:tnLst></p:timing>'
    )
    s4._element.append(timing)
    prs.save(path)
