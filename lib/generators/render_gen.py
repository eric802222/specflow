"""render_gen.py — 把 specs/ 底下的各層 DSL 渲染成「渲染後的產物」，供瀏覽器查看。

不重新發明每種 DSL 的渲染引擎，是去呼叫該生態系公認的既有工具，把產物彙整成一組
互相連結的靜態 HTML。db/ui 兩層的「用哪個副檔名、呼叫哪個指令、裝哪個工具」都是
DEFAULT_DSL_CONFIG 裡的預設值，不是寫死不能改——<spec-root>/dsl.yaml 存在的話
會覆寫這些值，跟 change-lifecycle.yaml 可以被專案客製化是同一套模式：

    npx dbml-renderer 是 DBML 生態系公認的標準工具，適合當預設值；
    但 db 這層的檔案「一定是 DBML」、ui 這層的渲染器「一定是某個特定工具」，
    這種假設不該焊死在核心程式碼裡——一個專案想用別的 DB DSL（例如 Prisma
    schema）或別的線框圖渲染器，現在只要寫一份 dsl.yaml 就能整層換掉，不用
    碰 render_gen.py 一行程式碼。

  - story/*.md    → story.md 解析 YAML frontmatter 渲染成 Given/When/Then 卡片；
                    flow_*.md 渲染成 Mermaid 圖表；都不需要外部工具
  - db/*.dbml     → 預設呼叫 dbml-renderer 產生 ER 圖 SVG（可透過 dsl.yaml 換工具）
  - api/*.tsp     → 呼叫 TypeSpec compiler 編譯成 OpenAPI3，接 Redoc 渲染成互動式 API 文件
  - ui/*.wf.yaml  → 預設呼叫 wireframe-lofi 產生線框圖 HTML（可透過 dsl.yaml 換工具）
  - logic/*.yaml  → 這層不需要外部工具，直接把決策規則渲染成真正的決策表格

這些外部工具都不是必要條件——使用者的環境不一定裝了對應工具。每一層渲染失敗時
（工具沒裝、編譯出錯、逾時），一律優雅退回顯示原始內容，並在頁面上印出「裝哪個
工具、下什麼指令」的具體說明（同樣可被 dsl.yaml 覆寫），不會讓整個 `specflow
render` 因為某一層渲染失敗就整個掛掉。

glossary.yaml 不需要外部工具，直接渲染成表格；這是唯一的例外，因為它的結構本來就
簡單到不需要借助任何渲染引擎，也沒有「換一種 DSL」的問題。

用法：
    python3 render_gen.py <spec-root> <out-dir>
"""

from __future__ import annotations

import copy
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

from lib.common import frontmatter as fm  # noqa: E402

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
.story-card { border: 1px solid #8884; border-radius: 10px; padding: 14px 18px; margin: 16px 0; }
.story-card.child { margin-left: 24px; border-style: dashed; }
.story-id { font-family: monospace; font-size: 0.85em; opacity: 0.7; }
.story-gwt dt { font-weight: 600; margin-top: 8px; }
.story-gwt dd { margin: 2px 0 0; }
.status-badge { display: inline-block; padding: 2px 10px; border-radius: 999px; font-size: 0.78em; font-weight: 600; }
.status-draft { background: #8882; }
.status-confirm { background: #1d71b822; color: #1d71b8; }
.status-living { background: #1a7f3722; color: #1a7f37; }
.refs-list a { display: block; }
"""

CATEGORY_LABELS = {
    "glossary": "Glossary", "story": "Story", "db": "DB", "api": "API", "ui": "UI", "logic": "Logic"
}

# 內建預設值——db/ui 兩層的 render_command 是「可覆寫」的建議值，不是唯一解。
# api 沒有 render_command（tsp compile+Redoc 這個策略太特化，沒有簡單的
# command 樣板可以套，維持專用程式碼路徑）；logic 完全不需要外部工具。
# render_command 裡的 {src}／{out} 會被實際路徑取代；ui 預設不需要 {out}
# （wireframe-lofi 的慣例是輸出跟輸入同目錄同檔名，見 _try_render_command）。
DEFAULT_DSL_CONFIG = {
    "story": {
        "pattern": "*.md",
        # 不需要外部工具：story.md 直接解析 YAML frontmatter 渲染成卡片，
        # flow_*.md（檔名前綴是判斷依據，不是可覆寫設定——這是這個層本身
        # 的命名慣例，不是外部工具的選型問題）渲染成 Mermaid 圖表。
        "install_note": (
            "這不是工具沒裝的問題——story.md 的 frontmatter 格式不符預期"
            "（缺 stories/status/goal 等必要欄位）。跑這個確認具體哪裡錯：\n"
            "python3 lib/linters/story_lint.py <story.md 路徑>"
        ),
    },
    "db": {
        "pattern": "*.dbml",
        "render_command": ["npx", "--yes", "@softwaretechnik/dbml-renderer", "-i", "{src}", "-o", "{out}"],
        "install_note": (
            "npm install -g @softwaretechnik/dbml-renderer\n"
            "# 或免安裝直接跑（第一次會下載）：\n"
            "npx --yes @softwaretechnik/dbml-renderer -i <path>.dbml -o <path>.svg"
        ),
    },
    "api": {
        "pattern": "*.tsp",
        "install_note": (
            "# 在 api/（或上層）需要有裝好依賴的 npm 專案：\n"
            "npm install @typespec/compiler @typespec/http @typespec/openapi3\n"
            "npx tsp compile <path>.tsp --emit @typespec/openapi3 --output-dir out"
        ),
    },
    "ui": {
        "pattern": "*.wf.yaml",
        # None 代表用內建的 wireframe-lofi 探索邏輯（SPECFLOW_WIREFRAME_LOFI 環境變數
        # 或 PATH 上找 wfyaml.py）。設成一份 command 樣板即可換成任何其他線框圖工具，
        # 假設是同一種輸出慣例：跟輸入同目錄同檔名、副檔名換成 .html。
        "render_command": None,
        "install_note": (
            "git clone https://github.com/eric802222/wireframe-lofi\n"
            "pip3 install pyyaml\n"
            "export SPECFLOW_WIREFRAME_LOFI=$(pwd)/wireframe-lofi/wfyaml.py"
        ),
    },
    "logic": {
        "pattern": "*.yaml",
    },
}

REDOC_CDN = "https://cdn.jsdelivr.net/npm/redoc@2.1.3/bundles/redoc.standalone.js"
MERMAID_CDN = "https://cdn.jsdelivr.net/npm/mermaid@10/dist/mermaid.min.js"


def load_dsl_config(spec_root: Path) -> dict:
    """讀 <spec-root>/dsl.yaml（可選），逐欄位淺層覆寫 DEFAULT_DSL_CONFIG。
    不存在就直接回傳預設值的副本——絕大多數專案完全不用寫這份檔案。"""
    config = copy.deepcopy(DEFAULT_DSL_CONFIG)
    dsl_path = spec_root / "dsl.yaml"
    if not dsl_path.exists() or yaml is None:
        return config

    overrides = yaml.safe_load(dsl_path.read_text(encoding="utf-8")) or {}
    for cat, cat_overrides in overrides.items():
        if cat not in config or not isinstance(cat_overrides, dict):
            continue
        config[cat].update(cat_overrides)
    return config


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


def _fallback_note(cat_config: dict) -> str:
    note = cat_config.get("install_note")
    if not note:
        return ""
    return (
        '<div class="fallback-note"><strong>還沒渲染成產物——目前顯示原始內容。</strong> '
        f"裝好對應工具後重跑 <code>specflow render</code> 就會換成真正的渲染結果："
        f"<pre>{html_lib.escape(note)}</pre></div>"
    )


def _raw_page(title: str, raw_text: str, back_href: str, cat_config: dict = None, rendered: bool = True) -> str:
    fallback = "" if rendered else _fallback_note(cat_config or {})
    return _page(title, fallback + f"<pre><code>{html_lib.escape(raw_text)}</code></pre>", back_href=back_href)


# ---------------------------------------------------------------------------
# 外部工具呼叫（失敗一律回 None／False，呼叫端負責退回原始內容）
# ---------------------------------------------------------------------------

def _run(cmd: list, cwd: str = None, timeout: int = 90):
    try:
        return subprocess.run(cmd, cwd=cwd, check=True, capture_output=True, timeout=timeout)
    except (FileNotFoundError, subprocess.CalledProcessError, subprocess.TimeoutExpired):
        return None


def _try_render_command(command_template: list, src_path: Path, out_path: Path = None, timeout: int = 90) -> bool:
    """把 command_template 裡的 {src}／{out} 換成實際路徑後執行。
    這是 db（跟被 dsl.yaml 覆寫過的 ui）共用的通用執行器——不管背後是
    dbml-renderer 還是任何其他團隊自己選的工具，呼叫方式都是同一套。"""
    cmd = [part.format(src=str(src_path), out=str(out_path) if out_path else "") for part in command_template]
    proc = _run(cmd, timeout=timeout)
    return proc is not None and (out_path is None or out_path.exists())


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
    """ui.render_command 沒被 dsl.yaml 覆寫時的內建預設探索邏輯：優先讀
    SPECFLOW_WIREFRAME_LOFI 環境變數（指向 wfyaml.py），找不到就試試看
    PATH 上有沒有 wfyaml.py。"""
    env = os.environ.get("SPECFLOW_WIREFRAME_LOFI")
    if env:
        p = Path(env).expanduser()
        if p.is_file():
            return p
    which = shutil.which("wfyaml.py")
    return Path(which) if which else None


def _try_render_ui(render_command, src_path: Path, ui_root: Path) -> str:
    """把整棵 ui/ 目錄複製到暫存區跑渲染指令（保留 components/layouts 等相對
    引用），回傳渲染後的完整 HTML 文字；失敗回 None。

    render_command 是 None 時走內建的 wireframe-lofi 探索邏輯；被 dsl.yaml
    設成一份 command 樣板時，直接照樣板執行——兩種情況都假設同一種輸出慣例：
    跟輸入同目錄、同檔名、副檔名換成 .html（這是目前唯一沒有一起通用化的
    地方：換一個線框圖工具，那個工具的輸出位置也要遵守這個慣例）。
    """
    with tempfile.TemporaryDirectory() as tmp:
        tmp_ui = Path(tmp) / "ui"
        shutil.copytree(ui_root, tmp_ui)
        rel = src_path.relative_to(ui_root)
        target = tmp_ui / rel

        if render_command is None:
            script = _find_wireframe_lofi_script()
            if script is None:
                return None
            proc = _run(["python3", str(script), str(target)], timeout=90)
        else:
            cmd = [part.format(src=str(target), out="") for part in render_command]
            proc = _run(cmd, timeout=90)

        if proc is None:
            return None

        # 線框圖工具的輸出慣例（跟輸入同目錄、同檔名、副檔名換成 .html）是
        # wireframe-lofi 自己的行為，已經實測確認過；換成別的工具時也假設
        # 遵守同一個慣例（見本函式 docstring）。
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


def _db_page(title: str, src_path: Path, out_path: Path, back_href: str, cat_config: dict) -> None:
    svg_path = out_path.with_suffix(".svg")
    command = cat_config.get("render_command")
    if command and _try_render_command(command, src_path, svg_path):
        body = f'<img src="{svg_path.name}" alt="{html_lib.escape(title)}" style="max-width:100%;height:auto;">'
        out_path.write_text(_page(title, body, back_href=back_href), encoding="utf-8")
        return

    raw = src_path.read_text(encoding="utf-8")
    out_path.write_text(_raw_page(title, raw, back_href, cat_config=cat_config, rendered=False), encoding="utf-8")


def _api_page(title: str, src_path: Path, out_path: Path, back_href: str, cat_config: dict) -> None:
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
    out_path.write_text(_raw_page(title, raw, back_href, cat_config=cat_config, rendered=False), encoding="utf-8")


_BODY_TAG_RE = re.compile(r"(<body[^>]*>)", re.IGNORECASE)


def _ui_page(title: str, src_path: Path, ui_root: Path, out_path: Path, back_href: str, cat_config: dict) -> None:
    rendered_html = _try_render_ui(cat_config.get("render_command"), src_path, ui_root)

    if rendered_html is not None:
        # 線框圖工具產出的通常是完整、自含的 HTML 文件（有自己的 <html><head>），
        # 不套我們自己的 _page 版型（會造成巢狀 <html>），只在 <body> 後插入一個
        # 回目錄的連結，其餘原樣輸出。
        back_link = f'<div style="padding:8px 16px;font-family:sans-serif;"><a href="{html_lib.escape(back_href)}">&larr; 目錄</a></div>'
        patched, n = _BODY_TAG_RE.subn(r"\1" + back_link, rendered_html, count=1)
        out_path.write_text(patched if n else rendered_html, encoding="utf-8")
        return

    raw = src_path.read_text(encoding="utf-8")
    out_path.write_text(_raw_page(title, raw, back_href, cat_config=cat_config, rendered=False), encoding="utf-8")


def _story_entry_html(entry: dict, is_child: bool = False) -> str:
    entry_id = html_lib.escape(str(entry.get("id", "")))
    given = html_lib.escape(str(entry.get("given", "")))
    when = html_lib.escape(str(entry.get("when", "")))
    then = html_lib.escape(str(entry.get("then", "")))

    body = (
        f'<div class="story-id">{entry_id}</div>'
        f'<dl class="story-gwt">'
        f'<dt>Given</dt><dd>{given}</dd>'
        f'<dt>When</dt><dd>{when}</dd>'
        f'<dt>Then</dt><dd>{then}</dd>'
        f'</dl>'
    )

    children = entry.get("children") or []
    children_html = "".join(_story_entry_html(c, is_child=True) for c in children if isinstance(c, dict))

    css_class = "story-card child" if is_child else "story-card"
    return f'<div class="{css_class}">{body}</div>{children_html}'


def _story_page(title: str, src_path: Path, back_href: str, cat_config: dict) -> str:
    """story.md 直接解析 YAML frontmatter 渲染成卡片，不需要任何外部工具——
    Given/When/Then 結構化資料本身就是渲染的來源，跟 logic 決策表是同一個道理。
    frontmatter 解析失敗或缺必要欄位時退回顯示原始內容（並算進「未渲染」統計），
    不強制先跑過 story_lint——lint 是給 gate_check 用的把關機制，render 只是
    盡力而為的展示層。
    """
    text = src_path.read_text(encoding="utf-8")
    data, _body, error = fm.load_frontmatter_data(text)
    if error or not isinstance(data, dict) or not isinstance(data.get("stories"), list):
        return _raw_page(title, text, back_href, cat_config=cat_config, rendered=False)

    status = str(data.get("status", ""))
    status_badge = f'<span class="status-badge status-{html_lib.escape(status)}">{html_lib.escape(status)}</span>'

    goal_html = f"<p><strong>Goal：</strong>{html_lib.escape(str(data.get('goal', '')))}</p>"

    refs = data.get("refs") or []
    refs_html = ""
    if refs:
        items = "".join(
            f'<li><a href="{html_lib.escape(str(r))}" target="_blank" rel="noopener">{html_lib.escape(str(r))}</a></li>'
            for r in refs
        )
        refs_html = f'<div><strong>Refs</strong><ul class="refs-list">{items}</ul></div>'

    external_key = data.get("external_key")
    key_html = f"<p><strong>Ticket：</strong>{html_lib.escape(str(external_key))}</p>" if external_key else ""

    stories_html = "".join(
        _story_entry_html(s) for s in data["stories"] if isinstance(s, dict)
    )

    header = f"<p>{status_badge}</p>{key_html}{goal_html}{refs_html}"
    return _page(title, header + stories_html, back_href=back_href)


_MERMAID_FENCE_RE = re.compile(r"^```mermaid\s*\n(.*?)\n```\s*$", re.DOTALL)


def _flow_page(title: str, src_path: Path, back_href: str) -> str:
    """flow_*.md 是 story 之後、plan 之前的動線對齊圖（Mermaid），不需要外部
    渲染工具——瀏覽器端跑 mermaid.js 直接畫。接受檔案內容是包在 ```mermaid
    fence 裡（標準 Markdown 寫法）或是純 Mermaid 原始碼兩種形式。
    """
    text = src_path.read_text(encoding="utf-8").strip()
    m = _MERMAID_FENCE_RE.match(text)
    diagram = m.group(1) if m else text

    body = (
        f'<pre class="mermaid">{html_lib.escape(diagram)}</pre>'
        f'<script src="{MERMAID_CDN}"></script>'
        f'<script>mermaid.initialize({{ startOnLoad: true }});</script>'
    )
    return _page(title, body, back_href=back_href)


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

    body = "".join(_section(k) for k in ("glossary", "story", "db", "api", "ui", "logic"))
    return _page("規格目錄", body, back_href=None)


# ---------------------------------------------------------------------------
# 主流程
# ---------------------------------------------------------------------------

def render(spec_root: Path, out_dir: Path) -> dict:
    """把 <spec-root>/specs/ 渲染成 out_dir 底下的一組 HTML，回傳索引結構
    {"glossary": "glossary.html" | None, "story": [...], "db": [...], "api": [...], "ui": [...], "logic": [...]}。
    每個分類實際用哪個副檔名 pattern、呼叫哪個渲染指令、顯示哪段安裝說明，
    先讀 <spec-root>/dsl.yaml（不存在就用內建預設值）。
    """
    specs_dir = spec_root / "specs"
    out_dir.mkdir(parents=True, exist_ok=True)
    dsl_config = load_dsl_config(spec_root)

    index = {"glossary": None, "story": [], "db": [], "api": [], "ui": [], "logic": []}

    glossary_path = specs_dir / "glossary.yaml"
    if glossary_path.exists():
        (out_dir / "glossary.html").write_text(_glossary_page(glossary_path), encoding="utf-8")
        index["glossary"] = "glossary.html"

    for cat, cat_config in dsl_config.items():
        cat_dir = specs_dir / cat
        if not cat_dir.exists():
            continue
        pattern = cat_config.get("pattern")
        if not pattern:
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

            if cat == "story":
                if src_path.name.startswith("flow_"):
                    out_path.write_text(_flow_page(title, src_path, back_href), encoding="utf-8")
                else:
                    out_path.write_text(_story_page(title, src_path, back_href, cat_config), encoding="utf-8")
            elif cat == "db":
                _db_page(title, src_path, out_path, back_href, cat_config)
            elif cat == "api":
                _api_page(title, src_path, out_path, back_href, cat_config)
            elif cat == "ui":
                _ui_page(title, src_path, cat_dir, out_path, back_href, cat_config)
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
