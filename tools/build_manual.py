"""MANUAL.md → MANUAL.html 변환 (목차·제목 앵커·체크리스트 포함, 외부 의존 없는 단일 파일).

실행: .venv/bin/python tools/build_manual.py
"""

from __future__ import annotations

import html
import re
from pathlib import Path
from urllib.parse import unquote

from markdown_it import MarkdownIt

ROOT = Path(__file__).resolve().parent.parent


def slugify(text: str) -> str:
    """GitHub 방식 앵커: 소문자, 문장부호 제거, 공백 → '-'."""
    text = text.strip().lower()
    text = re.sub(r"[^\w\- ]", "", text)
    return text.replace(" ", "-")


def build() -> Path:
    src = (ROOT / "MANUAL.md").read_text(encoding="utf-8")
    md = MarkdownIt("commonmark", {"html": False, "linkify": False}).enable("table")
    tokens = md.parse(src)

    toc: list[tuple[int, str, str]] = []
    title = "pdf2md 매뉴얼"
    for i, tok in enumerate(tokens):
        if tok.type == "heading_open":
            text = tokens[i + 1].content
            slug = slugify(re.sub(r"`", "", text))
            tok.attrSet("id", slug)
            level = int(tok.tag[1])
            if level == 1:
                title = text
            elif level == 2:
                toc.append((level, text, slug))
        for child in tok.children or []:
            if child.type != "link_open":
                continue
            href = child.attrGet("href") or ""
            if href.startswith("#"):
                child.attrSet("href", unquote(href))  # 한글 앵커를 id와 같은 형태로
            elif href.startswith("http"):
                child.attrSet("target", "_blank")
                child.attrSet("rel", "noopener")

    body = md.renderer.render(tokens, md.options, {})
    # 체크리스트: <li>[ ] ...  → 체크박스
    body = re.sub(r"<li>\[ \] ", '<li class="task"><input type="checkbox"> ', body)
    body = re.sub(r"<li>\[x\] ", '<li class="task"><input type="checkbox" checked> ', body)
    # 표는 가로 스크롤 래퍼로 감싼다
    body = body.replace("<table>", '<div class="tbl"><table>').replace("</table>", "</table></div>")

    def toc_label(text: str) -> str:
        return html.escape(text).replace("`", "")

    toc_html = "\n".join(f'<li><a href="#{s}">{toc_label(t)}</a></li>' for _, t, s in toc)

    page = TEMPLATE.replace("{{title}}", html.escape(title)).replace("{{toc}}", toc_html).replace("{{body}}", body)
    out = ROOT / "MANUAL.html"
    out.write_text(page, encoding="utf-8")
    return out


TEMPLATE = """<!DOCTYPE html>
<html lang="ko">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<link rel="icon" href="data:,">
<title>{{title}}</title>
<style>
  :root { --bg:#f6f5f1; --panel:#fff; --ink:#1c1b18; --muted:#6b6860; --line:#e3e0d8;
          --accent:#2f5d50; --accent-soft:#e4eeea; --mono:ui-monospace,"SF Mono",Menlo,monospace; }
  @media (prefers-color-scheme: dark) {
    :root { --bg:#151513; --panel:#1e1e1b; --ink:#ecebe6; --muted:#9a978e; --line:#33322d;
            --accent:#7fb8a6; --accent-soft:#24312d; } }
  * { box-sizing:border-box; }
  html { scroll-padding-top:20px; }
  body { margin:0; background:var(--bg); color:var(--ink);
         font:16px/1.7 -apple-system,"Apple SD Gothic Neo","Pretendard",system-ui,sans-serif; }
  .layout { display:grid; grid-template-columns:240px minmax(0, 860px); gap:32px; justify-content:center; padding:32px 24px 80px; }
  nav { position:sticky; top:32px; align-self:start; font-size:14px; }
  nav .label { font-size:12px; letter-spacing:.06em; text-transform:uppercase; color:var(--muted); margin-bottom:8px; }
  nav ol { list-style:none; margin:0; padding:0; border-left:2px solid var(--line); }
  nav a { display:block; padding:4px 0 4px 14px; margin-left:-2px; color:var(--muted); text-decoration:none; border-left:2px solid transparent; }
  nav a:hover { color:var(--ink); }
  nav a.on { color:var(--accent); border-color:var(--accent); font-weight:600; }
  main { background:var(--panel); border:1px solid var(--line); border-radius:14px; padding:40px 48px; }
  @media (max-width: 900px) { .layout { grid-template-columns:1fr; } nav { display:none; } main { padding:28px 22px; } }
  h1 { font-size:30px; line-height:1.3; letter-spacing:-.02em; margin:0 0 12px; }
  h2 { font-size:22px; letter-spacing:-.01em; margin:48px 0 14px; padding-top:8px; }
  h3 { font-size:17px; margin:28px 0 10px; }
  h1 + p { color:var(--muted); }
  hr { border:0; border-top:1px solid var(--line); margin:36px 0; }
  a { color:var(--accent); }
  code { font-family:var(--mono); font-size:.88em; background:var(--bg); border:1px solid var(--line); padding:1px 5px; border-radius:5px; }
  pre { background:#1c1b18; color:#ecebe6; padding:14px 18px; border-radius:10px; overflow-x:auto; position:relative; }
  pre code { background:none; border:0; padding:0; color:inherit; font-size:14px; }
  pre .copy { position:absolute; top:8px; right:8px; font:12px -apple-system,sans-serif; padding:3px 9px; border-radius:6px;
              border:1px solid #444; background:#2a2926; color:#ddd; cursor:pointer; opacity:0; transition:opacity .15s; }
  pre:hover .copy, pre .copy:focus { opacity:1; }
  .tbl { overflow-x:auto; margin:14px 0; }
  table { border-collapse:collapse; width:100%; font-size:14.5px; }
  th, td { border:1px solid var(--line); padding:8px 12px; text-align:left; vertical-align:top; }
  th { background:var(--bg); font-weight:600; white-space:nowrap; }
  blockquote { margin:16px 0; padding:10px 16px; background:var(--accent-soft); border-left:3px solid var(--accent); border-radius:0 8px 8px 0; }
  blockquote p { margin:6px 0; }
  li { margin:4px 0; }
  li.task { list-style:none; margin-left:-22px; }
  li.task input { accent-color:var(--accent); margin-right:8px; transform:scale(1.15); }
  @media print { nav, pre .copy { display:none; } .layout { display:block; padding:0; } main { border:0; padding:0; }
                 pre { background:#f4f4f4; color:#000; border:1px solid #ccc; } h2 { break-after:avoid; } }
</style>
</head>
<body>
<div class="layout">
  <nav aria-label="목차"><div class="label">목차</div><ol>
{{toc}}
  </ol></nav>
  <main>
{{body}}
  </main>
</div>
<script>
  // 코드 블록 복사 버튼
  document.querySelectorAll("pre").forEach((pre) => {
    const b = document.createElement("button");
    b.className = "copy"; b.type = "button"; b.textContent = "복사";
    b.onclick = async () => {
      await navigator.clipboard.writeText(pre.querySelector("code").innerText.replace(/\\n$/, ""));
      b.textContent = "복사됨"; setTimeout(() => (b.textContent = "복사"), 1500);
    };
    pre.append(b);
  });
  // 현재 읽는 절을 목차에 표시
  const links = [...document.querySelectorAll("nav a")];
  const io = new IntersectionObserver((entries) => {
    entries.forEach((e) => {
      if (e.isIntersecting) links.forEach((a) => a.classList.toggle("on", a.hash === "#" + CSS.escape(e.target.id) || decodeURIComponent(a.hash) === "#" + e.target.id));
    });
  }, { rootMargin: "0px 0px -70% 0px" });
  document.querySelectorAll("main h2[id]").forEach((h) => io.observe(h));
</script>
</body>
</html>
"""

if __name__ == "__main__":
    print(build())
