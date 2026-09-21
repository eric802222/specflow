"""render_gen.py — 把 specs/ 底下的各層 DSL 渲染成「渲染後的產物」，供瀏覽器查看。

不重新發明每種 DSL 的渲染引擎，是去呼叫該生態系公認的既有工具，把產物彙整成一組
互相連結的靜態 HTML：

  - db/*.dbml     → 呼叫 dbml-renderer（npx @softwaretechnik/dbml-renderer）產生 ER 圖 SVG
  - api/*.tsp     → 呼叫 TypeSpec compiler 編譯成 OpenAPI3，接 Redoc 渲染成互動式 API 文件
  - ui/*.wf.yaml  → 呼叫 wireframe-lofi 的 wfyaml.py 產生真正的線框圖 HTML
  - logic/*.yaml  → 這層不需要外部工具，直接把決策規則渲染成真正的決策表格

這些外部工具都不是必要條件——使用者的環境不一定裝了 Node.js、TypeSpec compiler 或
wireframe-lofi。每一層渲染失敗時（工具沒裝、編譯出錯、逾時），一律優雅退回顯示原始
內容，並在頁面上印出「裝哪個工具、下什麼指令」的具體說明，不會讓整個 `specflow
render` 因為某一層渲染失敗就整個掛掉——這延續 brownfield 友善的設計原則：能力不足
是資訊，不是錯誤。

glossary.yaml 不需要外部工具，直接渲染成表格；這是唯一的例外，因為它的結構本來就
簡單到不需要借助任何渲染引擎。

用法：
    python3 render_gen.py <spec-root> <out-dir>
"""

from __future__ import annotations

import html as html_lib
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(REPO_ROOT))

try:
    import yaml
except ImportError:  # pragma: no cover
    yaml = None

CSS = """
:root { color-scheme: light dark; }
body { font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif;
       max-width: 860px; margin: 0 auto; padding: 24px 16px 64px; line-height: 1.6; }
header { margin-bottom: 24px; }
header a { text-decoration: none; font-size: 0.9em; }
h1 { margin: 8px 0 0; }
h2 { margin-top: 32px; }
table { border-collapse: collapse; width: 100%; margin: 16px 0; }
th, td { border: 1px solid #8884; padding: 6px 10px; text-align: left; vertical-align: top; }
th { background: #8882; }
pre { background: #8881; padding: 16px; border-radius: 6px; overflow-x: auto; white-space: pre-wrap; word-break: break-word; }
ul.category-list { list-style: none; padding: 0; }
ul.category-list li { padding: 4px 0; }
.empty { opacity: 0.6; font-style: italic; }
section { margin-bottom: 32px; }
.fallback-note { border: 1px solid #f803; background: #f801; padding: 12px 16px; border-radius: 6px; margin-bottom: 16px; }
.fallback-note pre { margin: 8px 0 0; background: #8882; }
"""

CATEGORY_LABELS = {"glossary": "Glossary", "db": "DB", "api": "API", "ui": "UI", "logic": "Logic"}
CATEGORY_PATTERNS = {
    "db": "*.dbml",
    "api": "*.tsp",
    "ui": "*.wf.yaml",
    "logic": "*.yaml",
}

INSTALL_NOTES = {
    "db": (
        "npm install -g @softwaretechnik/dbml-renderer\n"
        "# 或免安裝直接跑（第一次會下載）：\n"
        "npx --yes @softwaretechnik/dbml-renderer -i <path>.dbml -o <path>.svg"
    ),
    "api": (
        "# 在 api/（或上層）需要有裝好依賴的 npm 專案：\n"
        "npm install @typespec/compiler @typespec/http @typespec/openapi3\n"
        "npx tsp compile <path>.tsp --emit @typespec/openapi3 --output-dir out"
    ),
    "ui": (
        "git clone https://github.com/eric802222/wireframe-lofi\n"
        "pip3 install pyyaml\n"
        "export SPECFLOW_WIREFRAME_LOFI=$(pwd)/wireframe-lofi/wfyaml.py"
    ),
}

REDOC_CDN = "https://cdn.jsdelivr.net/npm/redoc@2.1.3/bundles/redoc.standalone.js"


# ---------------------------------------------------------------------------
# 共用頁面版型
# ---------------------------------------------------------------------------

def _page(title: str, body_html: str, back_href: str = None) -> str:
    back = f'<a href="{back_href}">&larr; 目錄</a>' if back_href else ""
    return f"""<!DOCTYPE html>
<html lang="zh-Hant">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{html_lib.escape(title)} — specflow</title>
<style>{CSS}</style>
</head>
<body>
<header>{back}<h1>{html_lib.escape(title)}</h1></header>
<main>{body_html}</main>
</body>
</html>
"""


def _fallback_note(cat: str) -> str:
    note = INSTALL_NOTES.get(cat)
    if not note:
        return ""
    return (
        '<div class="fallback-note"><strong>還沒渲染成產物——目前顯示原始內容。</strong> '
        f"裝好對應工具後重跑 <code>specflow render</code> 就會換成真正的渲染結果："
        f"<pre>{html_lib.escape(note)}</pre></div>"
    )


def _raw_page(title: str, raw_text: str, back_href: str, cat: str = None, rendered: bool = True) -> str:
    fallback = "" if rendered else _fallback_note(cat)
    return _page(title, fallback + f"<pre><code>{html_lib.escape(raw_text)}</code></pre>", back_href=back_href)


# ---------------------------------------------------------------------------
# 外部工具呼叫（失敗一律回 None／False，呼叫端負責退回原始內容）
# ---------------------------------------------------------------------------

def _run(cmd: list, cwd: str = None, timeout: int = 90):
    try:
        return subprocess.run(cmd, cwd=cwd, check=True, capture_output=True, timeout=timeout)
    except (FileNotFoundError, subprocess.CalledProcessError, subprocess.TimeoutExpired):
        return None


def _try_render_dbml(src_path: Path, out_svg: Path) -> bool:
    """呼叫 dbml-renderer 把 DBML 轉成 ER 圖 SVG，寫到 out_svg。"""
    proc = _run(["npx", "--yes", "@softwaretechnik/dbml-renderer", "-i", str(src_path), "-o", str(out_svg)])
    return proc is not None and out_svg.exists()


def _find_npm_project_root(start: Path) -> Path:
    """從 start 往上找最近的 package.json 所在目錄（TypeSpec 專案的依賴通常宣告在這裡）。"""
    cur = start
    for _ in range(6):
        if (cur / "package.json").exists():
            return cur
        if cur.parent == cur:
            break
        cur = cur.parent
    return None


def _try_render_typespec(src_path: Path) -> dict:
    """呼叫 tsp compile 編譯成 OpenAPI3，回傳解析後的 dict；失敗回 None。

    TypeSpec 的 import 解析需要真正的 npm 專案（package.json + node_modules），
    不像 dbml-renderer 可以單次 npx 呼叫就跑——這裡假設目標專案已經自己
    `npm install` 過 TypeSpec 相關套件，只找 package.json 存不存在、
    node_modules 有沒有裝好，不會替使用者做全新安裝（那可能很慢、也可能
    裝到跟使用者專案版本衝突的東西）。
    """
    project_root = _find_npm_project_root(src_path)
    if project_root is None or not (project_root / "node_modules").exists():
        return None

    with tempfile.TemporaryDirectory() as tmp:
        out_dir = Path(tmp) / "out"
        proc = _run(
            ["npx", "tsp", "compile", str(src_path), "--emit", "@typespec/openapi3", "--output-dir", str(out_dir)],
            cwd=str(project_root),
            timeout=150,
        )
        if proc is None:
            return None

        candidates = sorted(out_dir.rglob("openapi*.yaml")) + sorted(out_dir.rglob("openapi*.json"))
        if not candidates:
            return None

        spec_path = candidates[0]
        text = spec_path.read_text(encoding="utf-8")
        try:
            if spec_path.suffix == ".json":
                return json.loads(text)
            return yaml.safe_load(text) if yaml is not None else None
        except Exception:
            return None


def _find_wireframe_lofi_script() -> Path:
    """優先讀 SPECFLOW_WIREFRAME_LOFI 環境變數（指向 wfyaml.py），
    找不到就試試看 PATH 上有沒有 wfyaml.py。"""
    env = os.environ.get("SPECFLOW_WIREFRAME_LOFI")
    if env:
        p = Path(env).expanduser()
        if p.is_file():
            return p
    which = shutil.which("wfyaml.py")
    return Path(which) if which else None


def _try_render_wireframe(script: Path, src_path: Path, ui_root: Path) -> str:
    """把整棵 ui/ 目錄複製到暫存區跑 wfyaml.py（保留 components/layouts 等相對引用），
    回傳渲染後的完整 HTML 文字；失敗回 None。輸出規則已實測確認：
    跟輸入同目錄、同檔名（<name>.wf.yaml -> <name>.html），輸出本身自含
    （CSS/icon 都內嵌，不依賴外部 assets/），所以不需要額外複製資產。"""
    with tempfile.TemporaryDirectory() as tmp:
        tmp_ui = Path(tmp) / "ui"
        shutil.copytree(ui_root, tmp_ui)
        rel = src_path.relative_to(ui_root)
        target = tmp_ui / rel

        proc = _run(["python3", str(script), str(target)], timeout=90)
        if proc is None:
            return None

        expected = target.parent / (target.name[: -len(".wf.yaml")] + ".html")
        if not expected.exists():
            return None
        return expected.read_text(encoding="utf-8")


# ---------------------------------------------------------------------------
# 各分類的頁面產生器
# ---------------------------------------------------------------------------

def _glossary_page(glossary_path: Path) -> str:
    if yaml is None:
        raise RuntimeError("需要 pyyaml 才能渲染 glossary.yaml")

    data = yaml.safe_load(glossary_path.read_text(encoding="utf-8")) or {}
    terms = data.get("terms", []) or []

    rows = []
    for t in terms:
        key = html_lib.escape(str(t.get("key", "")))
        term = html_lib.escape(str(t.get("term", "")))
        status = ", ".join(html_lib.escape(str(s)) for s in (t.get("status") or []))
        rows.append(f"<tr><td><code>{key}</code></td><td>{term}</td><td>{status}</td></tr>")

    body = (
        "<table><thead><tr><th>key</th><th>term</th><th>status</th></tr></thead>"
        f"<tbody>{''.join(rows) if rows else '<tr><td colspan=3 class=empty>尚未定義任何實體</td></tr>'}</tbody></table>"
    )
    return _page("Glossary", body, back_href="index.html")


def _db_page(title: str, src_path: Path, out_path: Path, back_href: str) -> None:
    svg_path = out_path.with_suffix(".svg")
    if _try_render_dbml(src_path, svg_path):
        body = f'<img src="{svg_path.name}" alt="{html_lib.escape(title)}" style="max-width:100%;height:auto;">'
        out_path.write_text(_page(title, body, back_href=back_href), encoding="utf-8")
        return

    raw = src_path.read_text(encoding="utf-8")
    out_path.write_text(_raw_page(title, raw, back_href, cat="db", rendered=False), encoding="utf-8")


def _api_page(title: str, src_path: Path, out_path: Path, back_href: str) -> None:
    spec = _try_render_typespec(src_path)
    if spec is not None:
        spec_json = json.dumps(spec)
        body = (
            '<div id="redoc-container"></div>'
            f'<script src="{REDOC_CDN}"></script>'
            f"<script>Redoc.init({spec_json}, {{}}, document.getElementById('redoc-container'));</script>"
        )
        out_path.write_text(_page(title, body, back_href=back_href), encoding="utf-8")
        return

    raw = src_path.read_text(encoding="utf-8")
    out_path.write_text(_raw_page(title, raw, back_href, cat="api", rendered=False), encoding="utf-8")


_BODY_TAG_RE = re.compile(r"(<body[^>]*>)", re.IGNORECASE)


def _ui_page(title: str, src_path: Path, ui_root: Path, out_path: Path, back_href: str) -> None:
    script = _find_wireframe_lofi_script()
    rendered_html = _try_render_wireframe(script, src_path, ui_root) if script else None

    if rendered_html is not None:
        # wireframe-lofi 產出的是完整、自含的 HTML 文件（有自己的 <html><head>），
        # 不套我們自己的 _page 版型（會造成巢狀 <html>），只在 <body> 後插入一個
        # 回目錄的連結，其餘原樣輸出。
        back_link = f'<div style="padding:8px 16px;font-family:sans-serif;"><a href="{html_lib.escape(back_href)}">&larr; 目錄</a></div>'
        patched, n = _BODY_TAG_RE.subn(r"\1" + back_link, rendered_html, count=1)
        out_path.write_text(patched if n else rendered_html, encoding="utf-8")
        return

    raw = src_path.read_text(encoding="utf-8")
    out_path.write_text(_raw_page(title, raw, back_href, cat="ui", rendered=False), encoding="utf-8")


def _logic_page(title: str, src_path: Path, back_href: str) -> str:
    """決策規則本身就是結構化資料，不需要外部工具，直接渲染成真正的決策表格
    （列 = 規則、欄 = when/then 用到的各個 key）。"""
    if yaml is None:
        return _raw_page(title, src_path.read_text(encoding="utf-8"), back_href)

    data = yaml.safe_load(src_path.read_text(encoding="utf-8")) or {}
    rules = data.get("rules", []) or []
    if not rules:
        return _raw_page(title, src_path.read_text(encoding="utf-8"), back_href)

    when_keys, then_keys = [], []
    for r in rules:
        for k in (r.get("when") or {}):
            if k not in when_keys:
                when_keys.append(k)
        for k in (r.get("then") or {}):
            if k not in then_keys:
                then_keys.append(k)

    header = "".join(f"<th>when.{html_lib.escape(k)}</th>" for k in when_keys)
    header += "".join(f"<th>then.{html_lib.escape(k)}</th>" for k in then_keys)

    row_html = []
    for r in rules:
        when, then = r.get("when") or {}, r.get("then") or {}
        cells = "".join(f"<td>{html_lib.escape(str(when.get(k, '—')))}</td>" for k in when_keys)
        cells += "".join(f"<td>{html_lib.escape(str(then.get(k, '—')))}</td>" for k in then_keys)
        row_html.append(f"<tr>{cells}</tr>")

    body = f"<table><thead><tr>{header}</tr></thead><tbody>{''.join(row_html)}</tbody></table>"
    return _page(title, body, back_href=back_href)


def _index_page(index: dict) -> str:
    def _section(key: str) -> str:
        title = CATEGORY_LABELS[key]
        items = index.get(key)
        if key == "glossary":
            if items:
                return f'<section><h2>{title}</h2><ul class="category-list"><li><a href="{items}">glossary.yaml</a></li></ul></section>'
            return f'<section><h2>{title}</h2><p class="empty">尚未建立</p></section>'
        if not items:
            return f'<section><h2>{title}</h2><p class="empty">尚未建立</p></section>'
        lis = "".join(f'<li><a href="{href}">{href}</a></li>' for href in items)
        return f'<section><h2>{title}</h2><ul class="category-list">{lis}</ul></section>'

    body = "".join(_section(k) for k in ("glossary", "db", "api", "ui", "logic"))
    return _page("規格目錄", body, back_href=None)


# ---------------------------------------------------------------------------
# 主流程
# ---------------------------------------------------------------------------

def render(spec_root: Path, out_dir: Path) -> dict:
    """把 <spec-root>/specs/ 渲染成 out_dir 底下的一組 HTML，回傳索引結構
    {"glossary": "glossary.html" | None, "db": [...], "api": [...], "ui": [...], "logic": [...]}。
    """
    specs_dir = spec_root / "specs"
    out_dir.mkdir(parents=True, exist_ok=True)

    index = {"glossary": None, "db": [], "api": [], "ui": [], "logic": []}

    glossary_path = specs_dir / "glossary.yaml"
    if glossary_path.exists():
        (out_dir / "glossary.html").write_text(_glossary_page(glossary_path), encoding="utf-8")
        index["glossary"] = "glossary.html"

    for cat, pattern in CATEGORY_PATTERNS.items():
        cat_dir = specs_dir / cat
        if not cat_dir.exists():
            continue
        suffix_to_strip = pattern[1:]  # 去掉開頭的 "*"，例如 "*.wf.yaml" -> ".wf.yaml"

        for src_path in sorted(cat_dir.rglob(pattern)):
            rel = src_path.relative_to(cat_dir)
            name_without_suffix = (
                rel.name[: -len(suffix_to_strip)] if rel.name.endswith(suffix_to_strip) else rel.stem
            )
            out_rel = Path(cat) / rel.parent / f"{name_without_suffix}.html"
            out_path = out_dir / out_rel
            out_path.parent.mkdir(parents=True, exist_ok=True)

            back_href = Path(os.path.relpath(out_dir / "index.html", start=out_path.parent)).as_posix()
            title = f"{cat}/{rel.as_posix()}"

            if cat == "db":
                _db_page(title, src_path, out_path, back_href)
            elif cat == "api":
                _api_page(title, src_path, out_path, back_href)
            elif cat == "ui":
                _ui_page(title, src_path, cat_dir, out_path, back_href)
            elif cat == "logic":
                out_path.write_text(_logic_page(title, src_path, back_href), encoding="utf-8")

            index[cat].append(out_rel.as_posix())

    (out_dir / "index.html").write_text(_index_page(index), encoding="utf-8")
    return index


def main(argv=None) -> int:
    argv = argv if argv is not None else sys.argv[1:]
    if len(argv) < 2:
        print("用法: render_gen.py <spec-root> <out-dir>", file=sys.stderr)
        return 2

    spec_root = Path(argv[0])
    out_dir = Path(argv[1])
    render(spec_root, out_dir)
    print(f"已產出：{(out_dir / 'index.html').resolve()}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
