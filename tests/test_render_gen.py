"""render_gen 的單元測試：真正渲染 vs 退回原始內容，brownfield 空分類。

所有測試預設（autouse fixture）把三個外部工具呼叫（dbml-renderer / tsp compile /
wireframe-lofi）都模擬成「沒裝」，讓測試不依賴這台機器有沒有 Node.js、網路、
或 wireframe-lofi ——需要驗證「工具真的有裝」那條路徑的測試，個別用 monkeypatch
覆寫回「有裝」。
"""

import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT))

from lib.generators import render_gen  # noqa: E402

GLOSSARY = """\
version: 1
terms:
  - key: deal
    term: 交易
    status: [draft, approved]
"""

DBML = "enum deal_status {\n  draft\n  approved\n}\n"
TSP = "enum DealStatus {\n  draft,\n  approved,\n}\n"
WF = "body:\n  - when: { state: approved }\n    status.strong: 已核准\n"
LOGIC = """\
rules:
  - when: { current_status: pending_approval }
    then: { status: approved }
  - when: { current_status: pending_approval }
    then: { status: rejected }
"""


@pytest.fixture(autouse=True)
def _no_external_tools_by_default(monkeypatch):
    """預設模擬所有外部工具都沒裝，測試才不依賴這台機器的環境。"""
    monkeypatch.setattr(render_gen, "_try_render_dbml", lambda src, out: False)
    monkeypatch.setattr(render_gen, "_try_render_typespec", lambda src: None)
    monkeypatch.setattr(render_gen, "_find_wireframe_lofi_script", lambda: None)


def _make_spec_root(tmp_path, with_glossary=True, with_db=True, with_ui_nested=False):
    spec_root = tmp_path / ".spec"
    specs_dir = spec_root / "specs"
    specs_dir.mkdir(parents=True)

    if with_glossary:
        (specs_dir / "glossary.yaml").write_text(GLOSSARY, encoding="utf-8")

    if with_db:
        (specs_dir / "db").mkdir(parents=True)
        (specs_dir / "db" / "schema.dbml").write_text(DBML, encoding="utf-8")

    (specs_dir / "api").mkdir(parents=True)
    (specs_dir / "api" / "main.tsp").write_text(TSP, encoding="utf-8")

    if with_ui_nested:
        (specs_dir / "ui" / "pages").mkdir(parents=True)
        (specs_dir / "ui" / "pages" / "deal-detail.wf.yaml").write_text(WF, encoding="utf-8")
    else:
        (specs_dir / "ui").mkdir(parents=True)
        (specs_dir / "ui" / "deal-detail.wf.yaml").write_text(WF, encoding="utf-8")

    (specs_dir / "logic" / "rules").mkdir(parents=True)
    (specs_dir / "logic" / "rules" / "deal-approval.yaml").write_text(LOGIC, encoding="utf-8")

    return spec_root


def test_render_produces_index_and_all_pages(tmp_path):
    spec_root = _make_spec_root(tmp_path)
    out_dir = tmp_path / "dist"

    index = render_gen.render(spec_root, out_dir)

    assert (out_dir / "index.html").exists()
    assert (out_dir / "glossary.html").exists()
    assert index["glossary"] == "glossary.html"
    assert index["db"] == ["db/schema.html"]
    assert index["api"] == ["api/main.html"]
    assert index["logic"] == ["logic/rules/deal-approval.html"]
    assert (out_dir / "db" / "schema.html").exists()
    assert (out_dir / "logic" / "rules" / "deal-approval.html").exists()


def test_glossary_table_renders_terms(tmp_path):
    spec_root = _make_spec_root(tmp_path)
    out_dir = tmp_path / "dist"
    render_gen.render(spec_root, out_dir)

    html = (out_dir / "glossary.html").read_text(encoding="utf-8")
    assert "deal" in html
    assert "draft" in html
    assert "approved" in html


def test_missing_glossary_is_not_an_error(tmp_path):
    spec_root = _make_spec_root(tmp_path, with_glossary=False)
    out_dir = tmp_path / "dist"

    index = render_gen.render(spec_root, out_dir)

    assert index["glossary"] is None
    assert not (out_dir / "glossary.html").exists()
    assert "尚未建立" in (out_dir / "index.html").read_text(encoding="utf-8")


def test_missing_category_directory_is_not_an_error(tmp_path):
    spec_root = _make_spec_root(tmp_path, with_db=False)
    out_dir = tmp_path / "dist"

    index = render_gen.render(spec_root, out_dir)

    assert index["db"] == []
    assert "尚未建立" in (out_dir / "index.html").read_text(encoding="utf-8")


def test_index_links_are_all_valid_relative_paths(tmp_path):
    spec_root = _make_spec_root(tmp_path, with_ui_nested=True)
    out_dir = tmp_path / "dist"
    render_gen.render(spec_root, out_dir)

    index_html = (out_dir / "index.html").read_text(encoding="utf-8")
    for href in ["glossary.html", "db/schema.html", "api/main.html", "ui/pages/deal-detail.html", "logic/rules/deal-approval.html"]:
        assert f'href="{href}"' in index_html
        assert (out_dir / href).exists()


# ---------------------------------------------------------------------------
# DB：dbml-renderer 有裝 vs 沒裝
# ---------------------------------------------------------------------------

def test_db_falls_back_to_raw_content_with_install_note(tmp_path):
    spec_root = _make_spec_root(tmp_path)
    out_dir = tmp_path / "dist"
    render_gen.render(spec_root, out_dir)

    html = (out_dir / "db" / "schema.html").read_text(encoding="utf-8")
    assert "還沒渲染成產物" in html
    assert "dbml-renderer" in html
    assert "enum deal_status" in html  # 原始內容仍然要看得到
    assert "<script>" not in html  # 沒有被拿來當 HTML 直接插入


def test_db_uses_real_render_when_tool_available(tmp_path, monkeypatch):
    def fake_dbml_render(src, out_svg):
        out_svg.write_text("<svg>fake ER diagram</svg>", encoding="utf-8")
        return True

    monkeypatch.setattr(render_gen, "_try_render_dbml", fake_dbml_render)

    spec_root = _make_spec_root(tmp_path)
    out_dir = tmp_path / "dist"
    render_gen.render(spec_root, out_dir)

    html = (out_dir / "db" / "schema.html").read_text(encoding="utf-8")
    assert "還沒渲染成產物" not in html
    assert '<img src="schema.svg"' in html
    assert (out_dir / "db" / "schema.svg").exists()


# ---------------------------------------------------------------------------
# API：TypeSpec compiler 有裝 vs 沒裝
# ---------------------------------------------------------------------------

def test_api_falls_back_to_raw_content_with_install_note(tmp_path):
    spec_root = _make_spec_root(tmp_path)
    out_dir = tmp_path / "dist"
    render_gen.render(spec_root, out_dir)

    html = (out_dir / "api" / "main.html").read_text(encoding="utf-8")
    assert "還沒渲染成產物" in html
    assert "tsp compile" in html
    assert "enum DealStatus" in html


def test_api_uses_redoc_when_typespec_compiles(tmp_path, monkeypatch):
    monkeypatch.setattr(render_gen, "_try_render_typespec", lambda src: {"openapi": "3.0.0", "info": {"title": "x"}})

    spec_root = _make_spec_root(tmp_path)
    out_dir = tmp_path / "dist"
    render_gen.render(spec_root, out_dir)

    html = (out_dir / "api" / "main.html").read_text(encoding="utf-8")
    assert "還沒渲染成產物" not in html
    assert "Redoc.init" in html
    assert "redoc.standalone.js" in html
    assert '"openapi": "3.0.0"' in html


# ---------------------------------------------------------------------------
# UI：wireframe-lofi 有裝 vs 沒裝
# ---------------------------------------------------------------------------

def test_ui_falls_back_to_raw_content_with_install_note(tmp_path):
    spec_root = _make_spec_root(tmp_path)
    out_dir = tmp_path / "dist"
    render_gen.render(spec_root, out_dir)

    html = (out_dir / "ui" / "deal-detail.html").read_text(encoding="utf-8")
    assert "還沒渲染成產物" in html
    assert "SPECFLOW_WIREFRAME_LOFI" in html
    assert "status.strong" in html


def test_ui_uses_wireframe_lofi_when_available(tmp_path, monkeypatch):
    monkeypatch.setattr(render_gen, "_find_wireframe_lofi_script", lambda: Path("/fake/wfyaml.py"))
    monkeypatch.setattr(
        render_gen,
        "_try_render_wireframe",
        lambda script, src, ui_root: "<html><body><h1>rendered wireframe here</h1></body></html>",
    )

    spec_root = _make_spec_root(tmp_path)
    out_dir = tmp_path / "dist"
    render_gen.render(spec_root, out_dir)

    html = (out_dir / "ui" / "deal-detail.html").read_text(encoding="utf-8")
    assert "還沒渲染成產物" not in html
    assert "rendered wireframe here" in html
    assert "目錄" in html  # 有被插入回目錄的連結


# ---------------------------------------------------------------------------
# Logic：不需要外部工具，直接渲染成真正的決策表格
# ---------------------------------------------------------------------------

def test_logic_renders_real_decision_table(tmp_path):
    spec_root = _make_spec_root(tmp_path)
    out_dir = tmp_path / "dist"
    render_gen.render(spec_root, out_dir)

    html = (out_dir / "logic" / "rules" / "deal-approval.html").read_text(encoding="utf-8")
    assert "還沒渲染成產物" not in html
    assert "<table" in html
    assert "when.current_status" in html
    assert "then.status" in html
    assert "pending_approval" in html
    assert "approved" in html
    assert "rejected" in html
