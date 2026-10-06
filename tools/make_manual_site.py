"""Build docs/manual.html, the manual as a web page, from the same Markdown the apps use.

    python tools/make_manual_site.py

The web page shows the whole book, with the parts that belong to one system marked "Linux" or "Android".
"""

from __future__ import annotations

import html
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
from juke import manual  # noqa: E402

# a block: the tags are alone on their lines (a piece inside a sentence is not a block; inline() handles that)
BLOCK_ONLY = re.compile(r"^<!--(linux|android)-->\n(.*?)^<!--/\1-->\n?", re.DOTALL | re.MULTILINE)


def inline(text: str) -> str:
    text = html.escape(text, quote=False)
    text = re.sub(r"`([^`]+)`", r"<code>\1</code>", text)
    text = re.sub(r"\*\*([^*]+)\*\*", r"<strong>\1</strong>", text)
    text = re.sub(r"\*([^*]+)\*", r"<em>\1</em>", text)
    text = re.sub(r"\[([^\]]+)\]\(([^)]+)\)", r'<a href="\2">\1</a>', text)
    # a piece for one system inside a sentence: "(Linux: …)" in its own colour
    text = re.sub(r"&lt;!--(linux|android)--&gt;(.*?)&lt;!--/\1--&gt;",
                  lambda m: f'<span class="il {m.group(1)}">{m.group(2)}</span>', text)
    return re.sub(r"&lt;!--(?:/)?(?:linux|android)--&gt;", "", text)


def slug(text: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", text.casefold().encode("ascii", "ignore").decode()).strip("-") or "x"


def markdown(text: str, prefix: str, image_base: str) -> str:
    """The small part of Markdown the manual uses: headings, paragraphs, lists, tables, images, code."""
    out: list[str] = []
    lines = text.splitlines()
    i = 0
    while i < len(lines):
        line = lines[i].rstrip()
        if not line.strip() or line.strip() == "---":
            i += 1
        elif line.startswith("```"):
            code = []
            i += 1
            while i < len(lines) and not lines[i].startswith("```"):
                code.append(lines[i])
                i += 1
            i += 1
            out.append("<pre><code>" + html.escape("\n".join(code)) + "</code></pre>")
        elif line.startswith("## "):
            out.append(f'<h3 id="{prefix}-{slug(line[3:])}">{inline(line[3:])}</h3>')
            i += 1
        elif line.startswith("### "):
            out.append(f"<h4>{inline(line[4:])}</h4>")
            i += 1
        elif re.match(r"^!\[([^\]]*)\]\(([^)]+)\)$", line):
            alt, src = re.match(r"^!\[([^\]]*)\]\(([^)]+)\)$", line).groups()
            out.append(f'<figure><img src="{image_base}{src}" alt="{html.escape(alt)}" loading="lazy"><figcaption>{inline(alt)}</figcaption></figure>')
            i += 1
        elif line.startswith("|"):
            rows = []
            while i < len(lines) and lines[i].startswith("|"):
                cells = [c.strip() for c in lines[i].strip().strip("|").split("|")]
                if not all(set(c) <= set("-: ") for c in cells):
                    rows.append(cells)
                i += 1
            head, body = rows[0], rows[1:]
            out.append("<div class=\"tbl\"><table><thead><tr>" + "".join(f"<th>{inline(c)}</th>" for c in head) + "</tr></thead><tbody>"
                       + "".join("<tr>" + "".join(f"<td>{inline(c)}</td>" for c in row) + "</tr>" for row in body) + "</tbody></table></div>")
        elif re.match(r"^(- |\* |\d+\. )", line):
            ordered = bool(re.match(r"^\d+\. ", line))
            items = []
            while i < len(lines) and re.match(r"^(- |\* |\d+\. )", lines[i]):
                items.append(re.sub(r"^(- |\* |\d+\. )", "", lines[i]).strip())
                i += 1
            tag = "ol" if ordered else "ul"
            out.append(f"<{tag}>" + "".join(f"<li>{inline(x)}</li>" for x in items) + f"</{tag}>")
        else:
            para = [line.strip()]
            i += 1
            while i < len(lines) and lines[i].strip() and not re.match(r"^(#|\||- |\* |\d+\. |!\[|```)", lines[i]) and lines[i].strip() != "---":
                para.append(lines[i].strip())
                i += 1
            out.append(f"<p>{inline(' '.join(para))}</p>")
    return "\n".join(out)


def book(code: str) -> tuple[str, str]:
    """(index html, body html) of one language."""
    raw = (manual.MANUAL_DIR / f"manual-{code}.md").read_text(encoding="utf-8")
    label = {"linux": "Linux", "android": "Android"}

    def mark(match: re.Match) -> str:
        return f'\n\n<<{match.group(1)}>>\n{match.group(2)}\n<</{match.group(1)}>>\n\n'

    raw = re.sub(r"(<!--(?:linux|android)-->\n)(# [^\n]+\n)", r"\2\1", raw)       # a block that wraps a whole chapter starts after its title
    raw = re.sub(r"^(?!<!--).*\S.*<!--(?:linux|android)-->.*<!--/(?:linux|android)-->.*$", lambda m: m.group(0).replace("\n", " "), raw, flags=re.M)
    marked = BLOCK_ONLY.sub(mark, raw)
    chapters, current = [], None
    for line in marked.splitlines():
        if line.startswith("# "):
            current = [re.sub(r"^\d+\.\s*", "", line[2:]).strip(), []]
            chapters.append(current)
        elif current is not None:
            current[1].append(line)
    index, body = [], []
    for number, (title, lines) in enumerate(chapters, 1):
        cid = f"{code}-c{number}"
        text = "\n".join(lines)
        parts, sections = [], []
        for piece in re.split(r"(<<(?:/)?(?:linux|android)>>)", text):
            m = re.match(r"<<(/)?(linux|android)>>", piece)
            if m:
                parts.append(("close" if m.group(1) else "open", m.group(2)))
            else:
                parts.append(("text", piece))
        html_parts = []
        for kind, value in parts:
            if kind == "open":
                html_parts.append(f'<div class="plat {value}"><span class="pill">{label[value]}</span>')
            elif kind == "close":
                html_parts.append("</div>")
            else:
                html_parts.append(markdown(value, cid, "assets/manual/"))
                sections += re.findall(r"^## (.+)$", value, flags=re.M)
        index.append(f'<li><a href="#{cid}"><span class="n">{number}</span> {html.escape(title)}</a>'
                     + ("<ul>" + "".join(f'<li><a href="#{cid}-{slug(s)}">{html.escape(s)}</a></li>' for s in sections) + "</ul>" if sections else "") + "</li>")
        body.append(f'<section class="chapter" id="{cid}"><p class="chno">{number}</p><h2>{html.escape(title)}</h2>{"".join(html_parts)}</section>')
    return "\n".join(index), "\n".join(body)


PAGE = """<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Juke 1.0 — Manual</title>
<meta name="description" content="The complete manual of Juke 1.0, for Linux and Android, in English and Spanish.">
<meta name="theme-color" content="#181825">
<link rel="icon" type="image/svg+xml" href="assets/juke.svg">
<style>
:root { --base:#1e1e2e; --mantle:#181825; --crust:#11111b; --panel:#252538; --surface:#2f2f45; --border:#313147; --text:#cdd6f4; --sub:#9399b2; --muted:#6c7086; --accent:#7aa2f7; --accent2:#cba6f7; --grad:linear-gradient(120deg,#7aa2f7,#cba6f7); }
:root[data-theme="light"] { --base:#f4f5fb; --mantle:#ffffff; --crust:#eceefa; --panel:#ffffff; --surface:#eceefa; --border:#dcdff0; --text:#24273a; --sub:#5b6078; --muted:#8a8fa8; }
* { box-sizing: border-box; } html { scroll-behavior: smooth; scroll-padding-top: 76px; }
body { margin:0; background:var(--mantle); color:var(--text); font:16px/1.7 "Inter",system-ui,-apple-system,"Segoe UI","Cantarell","Roboto","Noto Sans",sans-serif; -webkit-font-smoothing:antialiased; }
a { color:var(--accent); } img { max-width:100%; height:auto; display:block; }
code,pre { font-family:"JetBrains Mono",ui-monospace,"DejaVu Sans Mono",monospace; }
nav { position:sticky; top:0; z-index:10; backdrop-filter:blur(14px); background:color-mix(in srgb,var(--mantle) 80%,transparent); border-bottom:1px solid var(--border); }
nav .in { width:min(1180px,100% - 32px); margin-inline:auto; display:flex; align-items:center; gap:14px; height:58px; }
.brand { display:flex; align-items:center; gap:10px; font-weight:700; text-decoration:none; color:var(--text); } .brand small { color:var(--muted); font-weight:500; }
.sp { flex:1; } .tool { background:var(--surface); color:var(--text); border:1px solid var(--border); border-radius:10px; padding:6px 12px; font:inherit; font-size:14px; cursor:pointer; text-decoration:none; }
.layout { width:min(1180px,100% - 32px); margin:0 auto; display:grid; grid-template-columns:290px 1fr; gap:44px; padding:34px 0 90px; }
aside { position:sticky; top:84px; align-self:start; max-height:calc(100vh - 110px); overflow:auto; padding-right:6px; font-size:14.5px; }
aside summary { font-size:12px; letter-spacing:.14em; text-transform:uppercase; color:var(--muted); margin:0 0 10px; font-weight:700; cursor:pointer; list-style:none; }
aside summary::-webkit-details-marker { display:none; } summary .lang.on { display:inline; }
aside ul { list-style:none; margin:0; padding:0; } aside > ul > li { margin:2px 0; } aside a { color:var(--sub); text-decoration:none; display:block; padding:4px 8px; border-radius:8px; }
aside a:hover { background:var(--surface); color:var(--text); } aside .n { display:inline-block; min-width:1.5em; color:var(--accent2); font-weight:700; }
aside ul ul { margin:0 0 6px 28px; } aside ul ul a { font-size:13px; padding:2px 8px; }
.cover { text-align:center; padding:12px 0 38px; border-bottom:1px solid var(--border); margin-bottom:10px; }
.cover img { margin:0 auto 14px; } .cover h1 { font-size:clamp(34px,6vw,56px); line-height:1.1; margin:0; letter-spacing:-.02em; }
.cover h1 b { background:var(--grad); -webkit-background-clip:text; background-clip:text; color:transparent; } .cover p { color:var(--sub); margin:8px 0 0; font-size:18px; }
.chapter { padding-top:34px; border-top:1px solid var(--border); margin-top:34px; } .chapter:first-of-type { border-top:0; margin-top:0; }
.chno { display:inline-block; margin:0 0 4px; font-weight:800; color:var(--accent2); letter-spacing:.1em; } .chapter h2 { font-size:clamp(26px,3.6vw,36px); line-height:1.2; margin:0 0 14px; letter-spacing:-.01em; }
h3 { font-size:21px; margin:28px 0 6px; } h4 { font-size:17px; margin:20px 0 4px; } p { margin:10px 0; } li { margin:4px 0; }
code { background:var(--surface); border:1px solid var(--border); border-radius:6px; padding:1px 6px; font-size:.88em; } pre { background:var(--crust); border:1px solid var(--border); border-radius:12px; padding:14px 16px; overflow:auto; } pre code { background:none; border:0; padding:0; }
figure { margin:18px 0; } figure img { border-radius:14px; border:1px solid var(--border); max-width:min(100%,760px); } figcaption { color:var(--muted); font-size:13.5px; margin-top:6px; }
.tbl { overflow-x:auto; margin:14px 0; } table { border-collapse:collapse; width:100%; font-size:15px; } th,td { text-align:left; padding:9px 12px; border-bottom:1px solid var(--border); vertical-align:top; } th { color:var(--muted); font-size:12px; letter-spacing:.08em; text-transform:uppercase; background:var(--panel); }
.plat { border-left:3px solid var(--border); padding:2px 0 2px 16px; margin:14px 0; } .plat.linux { border-color:var(--accent); } .plat.android { border-color:#a6e3a1; }
.pill { display:inline-block; font-size:11px; font-weight:700; letter-spacing:.1em; text-transform:uppercase; padding:2px 9px; border-radius:99px; background:var(--surface); color:var(--sub); margin-bottom:2px; } .plat.linux .pill { color:var(--accent); } .plat.android .pill { color:#6fcf7b; }
.il.linux { color:var(--accent); } .il.android { color:#6fcf7b; } .il::before { content:""; }
.lang { display:none; } .lang.on { display:block; }
@media (min-width:901px) { aside summary { pointer-events:none; } }
@media (max-width:900px) {
  .layout { grid-template-columns:1fr; gap:18px; padding-top:18px; } aside { position:static; max-height:none; }
  aside details { background:var(--panel); border:1px solid var(--border); border-radius:14px; padding:12px 14px; }
  aside summary { margin:0; font-size:13px; } aside summary::after { content:" ▾"; } aside details[open] summary { margin-bottom:10px; } aside details[open] summary::after { content:" ▴"; }
  nav .in { gap:8px; height:54px; } .brand small { display:none; } .tool { padding:6px 10px; }
  .cover { padding:0 0 22px; } .cover img { width:64px; height:64px; margin-bottom:8px; } .cover p { font-size:16px; }
  .chapter h2 { font-size:25px; } figure img { max-width:100%; } table { font-size:14px; } th,td { padding:8px 9px; }
}
@media print { nav,aside { display:none; } .layout { display:block; } body { background:#fff; color:#000; } }
</style>
</head>
<body>
<nav><div class="in">
  <a class="brand" href="./"><img src="assets/juke.svg" alt="" width="28" height="28"> Juke <small>1.0 · Manual</small></a>
  <span class="sp"></span>
  <a class="tool" href="./">← Juke</a>
  <button class="tool" id="lang" type="button" aria-label="Language">ES</button>
  <button class="tool" id="theme" type="button" aria-label="Theme">☾</button>
</div></nav>
<div class="layout">
  <aside>
    <details class="toc" open>
      <summary><span class="lang on" data-lang="en">Contents</span><span class="lang" data-lang="es">Contenido</span></summary>
      <div class="lang on" data-lang="en"><ul>@@INDEX_EN@@</ul></div>
      <div class="lang" data-lang="es"><ul>@@INDEX_ES@@</ul></div>
    </details>
  </aside>
  <main>
    <div class="cover"><img src="assets/icon.png" alt="Juke" width="96" height="96">
      <h1><b>Juke</b> 1.0</h1>
      <p class="lang on" data-lang="en">The manual — for Linux and Android</p><p class="lang" data-lang="es">El manual — para Linux y Android</p></div>
    <div class="lang on" data-lang="en">@@BODY_EN@@</div>
    <div class="lang" data-lang="es">@@BODY_ES@@</div>
  </main>
</div>
<script>
const root = document.documentElement;
function store(k, v) { try { if (v === undefined) return localStorage.getItem(k); localStorage.setItem(k, v); } catch (e) { return null; } }
let lang = store("juke-lang") || ((navigator.language || "en").startsWith("es") ? "es" : "en");
function apply() {
  document.querySelectorAll(".lang").forEach(el => el.classList.toggle("on", el.dataset.lang === lang));
  root.lang = lang; document.getElementById("lang").textContent = lang === "en" ? "ES" : "EN";
  document.title = lang === "es" ? "Juke 1.0 — Manual" : "Juke 1.0 — Manual";
}
document.getElementById("lang").onclick = () => { lang = lang === "en" ? "es" : "en"; store("juke-lang", lang); apply(); };
const dark = () => root.dataset.theme !== "light";
function paint() { document.getElementById("theme").textContent = dark() ? "☾" : "☀"; }
root.dataset.theme = store("juke-theme") || "dark";
document.getElementById("theme").onclick = () => { root.dataset.theme = dark() ? "light" : "dark"; store("juke-theme", root.dataset.theme); paint(); };
paint(); apply();
if (matchMedia("(max-width: 900px)").matches) document.querySelector(".toc").removeAttribute("open");
document.querySelectorAll(".toc a").forEach(a => a.addEventListener("click", () => { if (matchMedia("(max-width: 900px)").matches) document.querySelector(".toc").removeAttribute("open"); }));
</script>
</body>
</html>
"""


def main() -> None:
    en_index, en_body = book("en")
    es_index, es_body = book("es")
    page = (PAGE.replace("@@INDEX_EN@@", en_index).replace("@@INDEX_ES@@", es_index)
            .replace("@@BODY_EN@@", en_body).replace("@@BODY_ES@@", es_body))
    out = ROOT / "docs" / "manual.html"
    out.write_text(page, encoding="utf-8")
    print("wrote", out, f"({len(page) // 1024} KB)")


if __name__ == "__main__":
    main()
