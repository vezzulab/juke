"""Turns the Juke (Linux) SVG glyphs into Android vector drawables: res/drawable/ic_<name>.xml.

Every shape is white so Compose can tint it with the theme colours. Run: python3 tools/make_icons.py <path to juke/gui/icons.py>
"""
import ast
import re
import sys
from pathlib import Path
from xml.etree import ElementTree as ET

src = Path(sys.argv[1]).read_text()
tree = ast.parse(src)
glyphs = {}
for node in tree.body:
    if isinstance(node, ast.AnnAssign) and getattr(node.target, "id", "") == "_GLYPHS":
        glyphs = ast.literal_eval(node.value)
WANT = ["play", "pause", "prev", "next", "stop", "shuffle", "repeat", "repeat-one", "search", "note", "artist", "album", "server",
        "queue", "radio", "globe", "gear", "more", "playlist", "sliders", "refresh", "folder", "trash", "close", "plus", "chevron", "eq", "heart", "heart-outline", "volume"]


def f(x):
    return ("%.3f" % float(x)).rstrip("0").rstrip(".")


def circle(cx, cy, r):
    return f"M{f(cx - r)},{f(cy)}a{f(r)},{f(r)} 0 1,0 {f(2 * r)},0a{f(r)},{f(r)} 0 1,0 {f(-2 * r)},0z"


def rect(x, y, w, h, rx):
    rx = min(rx, w / 2, h / 2)
    return (f"M{f(x + rx)},{f(y)}h{f(w - 2 * rx)}a{f(rx)},{f(rx)} 0 0,1 {f(rx)},{f(rx)}v{f(h - 2 * rx)}a{f(rx)},{f(rx)} 0 0,1 {f(-rx)},{f(rx)}"
            f"h{f(-(w - 2 * rx))}a{f(rx)},{f(rx)} 0 0,1 {f(-rx)},{f(-rx)}v{f(-(h - 2 * rx))}a{f(rx)},{f(rx)} 0 0,1 {f(rx)},{f(-rx)}z")


def paths(kind, body):
    root = ET.fromstring(f'<g xmlns="http://www.w3.org/2000/svg">{body}</g>')
    out = []
    for el in root:
        tag = el.tag.split("}")[1]
        a = el.attrib
        if tag == "path":
            d = a["d"]
        elif tag == "circle":
            d = circle(float(a["cx"]), float(a["cy"]), float(a["r"]))
        elif tag == "rect":
            d = rect(float(a["x"]), float(a["y"]), float(a["width"]), float(a["height"]), float(a.get("rx", 0)))
        else:
            raise SystemExit(f"unsupported {tag}")
        filled = kind == "fill" or a.get("fill") == "currentColor"
        out.append((d, filled))
    return out


dest = Path(__file__).resolve().parent.parent / "app/src/main/res/drawable"
for name in WANT:
    kind, body = glyphs[name]
    lines = ['<vector xmlns:android="http://schemas.android.com/apk/res/android" android:width="24dp" android:height="24dp"',
             '    android:viewportWidth="24" android:viewportHeight="24">']
    for d, filled in paths(kind, body):
        d = re.sub(r"\s+", " ", d)
        if kind == "fill":
            lines.append(f'    <path android:fillColor="#FFFFFFFF" android:pathData="{d}"/>')
        elif filled:
            lines.append(f'    <path android:fillColor="#FFFFFFFF" android:strokeColor="#FFFFFFFF" android:strokeWidth="2" android:pathData="{d}"/>')
        else:
            lines.append(f'    <path android:strokeColor="#FFFFFFFF" android:strokeWidth="2" android:strokeLineCap="round" android:strokeLineJoin="round" android:pathData="{d}"/>')
    lines.append("</vector>")
    (dest / f"ic_{name.replace('-', '_')}.xml").write_text("\n".join(lines) + "\n")
print("wrote", len(WANT), "icons")
