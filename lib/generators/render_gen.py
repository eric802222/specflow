"""render_gen.py — 把 specs/ 底下的各層 DSL 渲染成一組靜態 HTML，供瀏覽器查看。

刻意不做「真正解析語法畫圖」這種事——DBML/TypeSpec 的語意渲染是它們自己生態系
的工具該做的事（dbdiagram.io、tsp compile 等），specflow 的角色只是把 specs/
底下所有規格檔案彙整成一個可以在瀏覽器打開、彼此連結的入口，讓沒有裝對應工具鏈
的人也能一頁一頁點過去看到內容——這正對應「Git-native spec aggregator」的定位：
不是自己重新發明一套渲染引擎，是把既有的規格接起來變成可瀏覽的東西。

glossary.yaml 是唯一額外做結構化呈現的（渲染成表格），因為它的結構簡單、
瀏覽器裡看表格比看原始 YAML 好讀很多；其餘檔案（dbml/tsp/wf.yaml/logic yaml）
一律用語法高亮的原始內容呈現，不假裝有能力解析每一種 DSL 的語意。

某個分類（db/api/ui/logic）底下沒有任何檔案時，目錄頁顯示「尚未建立」而不是
報錯——這是接手一個還沒有規格的既有專案時的正常起點狀態，不是缺陷。

用法：
    python3 render_gen.py <spec-root> <out-dir>
"""

from __future__ import annotations

import html as html_lib
import os
import sys
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
"""

CATEGORY_LABELS = {"glossary": "Glossary", "db": "DB", "api": "API", "ui": "UI", "logic": "Logic"}
CATEGORY_PATTERNS = {
    "db": "*.dbml",
    "api": "*.tsp",
    "ui": "*.wf.yaml",
    "logic": "*.yaml",
}


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


def _raw_page(title: str, raw_text: str, back_href: str) -> str:
    return _page(title, f"<pre><code>{html_lib.escape(raw_text)}</code></pre>", back_href=back_href)


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

            back_href = os.path.relpath(out_dir / "index.html", start=out_path.parent)
            back_href = Path(back_href).as_posix()

            raw = src_path.read_text(encoding="utf-8")
            out_path.write_text(_raw_page(f"{cat}/{rel.as_posix()}", raw, back_href=back_href), encoding="utf-8")
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
