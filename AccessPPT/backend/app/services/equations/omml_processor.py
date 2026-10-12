"""
OMML (Office Math Markup Language) processing.

Converts native PowerPoint/Office equations (``m:oMath`` / ``m:oMathPara``) into
Presentation MathML plus a human-readable linear form. MathML is the interchange
format handed to the MathType adapter; the linear form is used for alt text and
reports. Constructs that are not understood are recorded in ``unsupported`` so the
classifier can route the equation to manual review instead of guessing.
"""
from __future__ import annotations

import unicodedata
from dataclasses import dataclass, field
from typing import Optional

from lxml import etree

M_NS = "http://schemas.openxmlformats.org/officeDocument/2006/math"
MML_NS = "http://www.w3.org/1998/Math/MathML"

FUNCTION_NAMES = {
    "sin", "cos", "tan", "cot", "sec", "csc", "arcsin", "arccos", "arctan",
    "sinh", "cosh", "tanh", "log", "ln", "exp", "lim", "max", "min", "det", "mod",
}


def _m(tag: str) -> str:
    return f"{{{M_NS}}}{tag}"


def _local(el) -> str:
    return etree.QName(el).localname if isinstance(el.tag, str) else ""


def _is_m(el) -> bool:
    return isinstance(el.tag, str) and etree.QName(el).namespace == M_NS


def _val(parent, path: str, default: Optional[str] = None) -> Optional[str]:
    """Return ``m:val`` of the first element matching ``path`` (e.g. 'm:fPr/m:type')."""
    if parent is None:
        return default
    node = parent.find(path, namespaces={"m": M_NS})
    if node is None:
        return default
    return node.get(_m("val"), default)


def _on(parent, path: str) -> bool:
    """OMML boolean property: present with no val, or val in (1, on, true)."""
    node = parent.find(path, namespaces={"m": M_NS}) if parent is not None else None
    if node is None:
        return False
    v = node.get(_m("val"))
    return v is None or v.lower() in ("1", "on", "true")


@dataclass
class OmmlConversion:
    mathml: str
    linear: str
    constructs: list[str] = field(default_factory=list)
    unsupported: list[str] = field(default_factory=list)

    @property
    def fully_supported(self) -> bool:
        return not self.unsupported


class _Converter:
    def __init__(self):
        self.constructs: set[str] = set()
        self.unsupported: set[str] = set()

    # ── MathML element helpers ──────────────────────────────────────────────
    @staticmethod
    def el(tag: str, *children, text: Optional[str] = None, **attrs):
        node = etree.Element(f"{{{MML_NS}}}{tag}", nsmap={None: MML_NS})
        for k, v in attrs.items():
            node.set(k.replace("_", "-"), v)
        if text is not None:
            node.text = text
        for c in children:
            if c is not None:
                node.append(c)
        return node

    def row(self, items: list) -> etree._Element:
        items = [i for i in items if i is not None]
        if len(items) == 1:
            return items[0]
        return self.el("mrow", *items)

    # ── Linear text helpers ─────────────────────────────────────────────────
    @staticmethod
    def group(s: str) -> str:
        s = s.strip()
        if len(s) <= 1 or (s.startswith("(") and s.endswith(")") and s.count("(") == 1):
            return s
        return f"({s})"

    # ── Traversal ────────────────────────────────────────────────────────────
    def children(self, parent) -> tuple[list, str]:
        """Convert the content children of an OMML container (m:e, m:num, ...)."""
        nodes, texts = [], []
        if parent is None:
            return nodes, ""
        for child in parent:
            if not _is_m(child):
                continue
            name = _local(child)
            if name.endswith("Pr") or name == "ctrlPr":
                continue
            res = self.convert(child)
            if res is None:
                continue
            node, text = res
            if isinstance(node, list):
                nodes.extend(node)
            else:
                nodes.append(node)
            texts.append(text)
        return nodes, "".join(texts)

    def arg(self, parent, name: str):
        child = parent.find(_m(name))
        nodes, text = self.children(child)
        if not nodes:
            return self.el("mrow"), text
        return self.row(nodes), text

    def convert(self, el):
        name = _local(el)
        handler = getattr(self, f"_h_{name}", None)
        if handler is not None:
            return handler(el)
        if name in ("e", "num", "den", "sub", "sup", "deg", "lim", "fName", "oMath", "box"):
            nodes, text = self.children(el)
            return self.row(nodes) if nodes else self.el("mrow"), text
        self.unsupported.add(name)
        nodes, text = self.children(el)
        return self.row(nodes) if nodes else self.el("mrow"), text

    # ── Runs / tokens ────────────────────────────────────────────────────────
    def _h_r(self, el):
        text = "".join(t.text or "" for t in el.findall(_m("t")))
        rpr = el.find(_m("rPr"))
        sty = _val(rpr, "m:sty")
        if rpr is not None and _on(rpr, "m:nor"):
            return self.el("mtext", text=text), text
        return self.tokens(text, plain=(sty in ("p", "b"))), unicodedata.normalize("NFKC", text)

    def tokens(self, raw: str, plain: bool = False) -> list:
        text = unicodedata.normalize("NFKC", raw)
        out: list = []
        i = 0
        while i < len(text):
            ch = text[i]
            if ch.isspace():
                i += 1
                continue
            if ch.isdigit() or (ch == "." and i + 1 < len(text) and text[i + 1].isdigit()):
                j = i
                while j < len(text) and (text[j].isdigit() or text[j] == "."):
                    j += 1
                out.append(self.el("mn", text=text[i:j]))
                i = j
                continue
            if ch.isalpha():
                j = i
                while j < len(text) and text[j].isalpha():
                    j += 1
                word = text[i:j]
                if word in FUNCTION_NAMES or (plain and len(word) > 1):
                    out.append(self.el("mi", text=word, mathvariant="normal") if len(word) == 1 else self.el("mi", text=word))
                else:
                    for c in word:
                        out.append(self.el("mi", text=c, mathvariant="normal") if plain else self.el("mi", text=c))
                i = j
                continue
            out.append(self.el("mo", text=ch))
            i += 1
        return out

    # ── Structures ───────────────────────────────────────────────────────────
    def _h_f(self, el):
        self.constructs.add("fraction")
        ftype = _val(el, "m:fPr/m:type", "bar")
        num, nt = self.arg(el, "num")
        den, dt = self.arg(el, "den")
        attrs = {}
        if ftype == "noBar":
            attrs["linethickness"] = "0"
        elif ftype in ("skw", "lin"):
            attrs["bevelled"] = "true"
        return self.el("mfrac", num, den, **attrs), f"{self.group(nt)}/{self.group(dt)}"

    def _h_rad(self, el):
        self.constructs.add("radical")
        base, bt = self.arg(el, "e")
        deg_el = el.find(_m("deg"))
        deg_nodes, dt = self.children(deg_el)
        if _on(el.find(_m("radPr")), "m:degHide") or not deg_nodes:
            return self.el("msqrt", base), f"√{self.group(bt)}"
        return self.el("mroot", base, self.row(deg_nodes)), f"root({dt}, {bt})"

    def _h_sSup(self, el):
        self.constructs.add("superscript")
        b, bt = self.arg(el, "e")
        s, st = self.arg(el, "sup")
        return self.el("msup", b, s), f"{bt}^{self.group(st)}"

    def _h_sSub(self, el):
        self.constructs.add("subscript")
        b, bt = self.arg(el, "e")
        s, st = self.arg(el, "sub")
        return self.el("msub", b, s), f"{bt}_{self.group(st)}"

    def _h_sSubSup(self, el):
        self.constructs.update(("subscript", "superscript"))
        b, bt = self.arg(el, "e")
        sb, sbt = self.arg(el, "sub")
        sp, spt = self.arg(el, "sup")
        return self.el("msubsup", b, sb, sp), f"{bt}_{self.group(sbt)}^{self.group(spt)}"

    def _h_sPre(self, el):
        self.constructs.add("prescript")
        b, bt = self.arg(el, "e")
        sb, sbt = self.arg(el, "sub")
        sp, spt = self.arg(el, "sup")
        node = self.el("mmultiscripts", b, self.el("mprescripts"), sb, sp)
        return node, f"_{self.group(sbt)}^{self.group(spt)}{bt}"

    def _h_nary(self, el):
        pr = el.find(_m("naryPr"))
        op = _val(pr, "m:chr", "∫")
        self.constructs.add({"∑": "summation", "∏": "product"}.get(op, "integral" if op in "∫∬∭∮" else "n-ary"))
        loc = _val(pr, "m:limLoc", "subSup" if op in "∫∬∭∮" else "undOvr")
        sub_hide, sup_hide = _on(pr, "m:subHide"), _on(pr, "m:supHide")
        mo = self.el("mo", text=op)
        sb, sbt = self.arg(el, "sub")
        sp, spt = self.arg(el, "sup")
        body, bodyt = self.arg(el, "e")
        under, over = (loc == "undOvr"), loc == "undOvr"
        if sub_hide and sup_hide:
            head = mo
        elif sup_hide:
            head = self.el("munder" if under else "msub", mo, sb)
        elif sub_hide:
            head = self.el("mover" if over else "msup", mo, sp)
        else:
            head = self.el("munderover" if under else "msubsup", mo, sb, sp)
        lin = op + ("" if sub_hide else f"_{self.group(sbt)}") + ("" if sup_hide else f"^{self.group(spt)}")
        return self.el("mrow", head, body), f"{lin} {bodyt}"

    def _h_d(self, el):
        pr = el.find(_m("dPr"))
        beg = _val(pr, "m:begChr", "(")
        end = _val(pr, "m:endChr", ")")
        sep = _val(pr, "m:sepChr", "|")
        parts, texts = [], []
        for e in el.findall(_m("e")):
            nodes, t = self.children(e)
            parts.append(self.row(nodes) if nodes else self.el("mrow"))
            texts.append(t)
        items = []
        if beg:
            items.append(self.el("mo", text=beg, fence="true"))
        for idx, p in enumerate(parts):
            if idx:
                items.append(self.el("mo", text=sep, separator="true"))
            items.append(p)
        if end:
            items.append(self.el("mo", text=end, fence="true"))
        self.constructs.add("delimiter")
        return self.el("mrow", *items), f"{beg or ''}{sep.join(texts)}{end or ''}"

    def _h_func(self, el):
        self.constructs.add("function")
        name, nt = self.arg(el, "fName")
        body, bt = self.arg(el, "e")
        return self.el("mrow", name, self.el("mo", text="\u2061"), body), f"{nt} {bt}" if not bt.startswith("(") else f"{nt}{bt}"

    def _h_limLow(self, el):
        self.constructs.add("limit")
        b, bt = self.arg(el, "e")
        lim, lt = self.arg(el, "lim")
        return self.el("munder", b, lim), f"{bt}_{self.group(lt)}"

    def _h_limUpp(self, el):
        self.constructs.add("limit")
        b, bt = self.arg(el, "e")
        lim, lt = self.arg(el, "lim")
        return self.el("mover", b, lim), f"{bt}^{self.group(lt)}"

    def _h_acc(self, el):
        self.constructs.add("accent")
        ch = _val(el, "m:accPr/m:chr", "\u0302")
        b, bt = self.arg(el, "e")
        return self.el("mover", b, self.el("mo", text=ch), accent="true"), f"{bt}{ch}"

    def _h_bar(self, el):
        self.constructs.add("bar")
        pos = _val(el, "m:barPr/m:pos", "bot")
        b, bt = self.arg(el, "e")
        if pos == "top":
            return self.el("mover", b, self.el("mo", text="\u00AF"), accent="true"), f"overline({bt})"
        return self.el("munder", b, self.el("mo", text="_"), accentunder="true"), f"underline({bt})"

    def _h_groupChr(self, el):
        self.constructs.add("group_character")
        pr = el.find(_m("groupChrPr"))
        ch = _val(pr, "m:chr", "\u23DF")
        pos = _val(pr, "m:pos", "bot")
        b, bt = self.arg(el, "e")
        tag = "mover" if pos == "top" else "munder"
        return self.el(tag, b, self.el("mo", text=ch)), bt

    def _h_m(self, el):
        self.constructs.add("matrix")
        rows, trows = [], []
        for mr in el.findall(_m("mr")):
            cells, tcells = [], []
            for e in mr.findall(_m("e")):
                nodes, t = self.children(e)
                cells.append(self.el("mtd", *(nodes or [self.el("mrow")])))
                tcells.append(t)
            rows.append(self.el("mtr", *cells))
            trows.append("[" + ", ".join(tcells) + "]")
        return self.el("mtable", *rows), "[" + ", ".join(trows) + "]"

    def _h_eqArr(self, el):
        self.constructs.add("equation_array")
        rows, texts = [], []
        for e in el.findall(_m("e")):
            nodes, t = self.children(e)
            rows.append(self.el("mtr", self.el("mtd", *(nodes or [self.el("mrow")]))))
            texts.append(t)
        return self.el("mtable", *rows, columnalign="left"), "; ".join(texts)

    def _h_borderBox(self, el):
        self.constructs.add("border_box")
        b, bt = self.arg(el, "e")
        return self.el("menclose", b, notation="box"), bt

    def _h_box(self, el):
        b, bt = self.arg(el, "e")
        return b, bt

    def _h_phant(self, el):
        b, bt = self.arg(el, "e")
        if _on(el.find(_m("phantPr")), "m:show"):
            return b, bt
        return self.el("mphantom", b), ""


def convert_omath(element) -> OmmlConversion:
    """Convert an ``m:oMath`` or ``m:oMathPara`` element to MathML."""
    conv = _Converter()
    display = "inline"
    if _local(element) == "oMathPara":
        display = "block"
        lines = [conv.convert(om) for om in element.findall(_m("oMath"))]
        if len(lines) == 1:
            body, linear = lines[0]
        else:
            conv.constructs.add("multi_line")
            body = conv.el("mtable", *[conv.el("mtr", conv.el("mtd", n)) for n, _ in lines], columnalign="left")
            linear = "; ".join(t for _, t in lines)
    else:
        body, linear = conv.convert(element)
    math = etree.Element(f"{{{MML_NS}}}math", nsmap={None: MML_NS})
    math.set("display", display)
    math.append(body)
    etree.cleanup_namespaces(math)
    return OmmlConversion(
        mathml=etree.tostring(math, encoding="unicode"),
        linear=" ".join(linear.split()),
        constructs=sorted(conv.constructs),
        unsupported=sorted(conv.unsupported),
    )


def combine_mathml(mathml_items: list[str]) -> str:
    """Stack several MathML equations vertically into one block equation."""
    if len(mathml_items) == 1:
        return mathml_items[0]
    math = etree.Element(f"{{{MML_NS}}}math", nsmap={None: MML_NS})
    math.set("display", "block")
    table = etree.SubElement(math, f"{{{MML_NS}}}mtable", columnalign="left")
    for item in mathml_items:
        src = etree.fromstring(item.encode("utf-8"))
        tr = etree.SubElement(table, f"{{{MML_NS}}}mtr")
        td = etree.SubElement(tr, f"{{{MML_NS}}}mtd")
        for child in list(src):
            td.append(child)
    etree.cleanup_namespaces(math)
    return etree.tostring(math, encoding="unicode")


def find_top_level_equations(root) -> list:
    """Return every ``m:oMathPara`` and each ``m:oMath`` not inside an ``m:oMathPara``."""
    found = []
    for node in root.iter(_m("oMathPara"), _m("oMath")):
        if _local(node) == "oMath":
            parent = node.getparent()
            if parent is not None and _local(parent) == "oMathPara" and _is_m(parent):
                continue
        found.append(node)
    return found
