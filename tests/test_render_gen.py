"""render_gen 的單元測試：目錄頁、glossary 表格、原始內容分頁、brownfield 空分類。"""

import sys
from pathlib import Path

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
WF = "body:\n  - when: { state: approved }\n    status.strong: 已核準\n"
LOGIC = "rules:\n  - when: { current_status: approved }\n    then: { status: approved }\n"


def _make_spec_root(tmp_path, with_glossary=True, with_db=True, with_ui_nested=False):
    spec_root = tmp_path / ".spec"
    specs_dir = spec_root / "specs"

    if with_glossary:
        specs_dir.mkdir(parents=True)
        (specs_dir / "glossary.yaml").write_text(GLOSSARY, encoding="utf-8")
    else:
        specs_dir.mkdir(parents=True)

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


def test_raw_pages_escape_content(tmp_path):
    spec_root = _make_spec_root(tmp_path)
    out_dir = tmp_path / "dist"
    render_gen.render(spec_root, out_dir)

    html = (out_dir / "db" / "schema.html").read_text(encoding="utf-8")
    assert "enum deal_status" in html
    assert "<script>" not in html  # 沒有被拿來當 HTML 直接插入


def test_missing_glossary_is_not_an_error(tmp_path):
    """brownfield 場景：glossary.yaml 不存在時，render 要能正常跑完，目錄頁顯示尚未建立。"""
    spec_root = _make_spec_root(tmp_path, with_glossary=False)
    out_dir = tmp_path / "dist"

    index = render_gen.render(spec_root, out_dir)

    assert index["glossary"] is None
    assert not (out_dir / "glossary.html").exists()
    index_html = (out_dir / "index.html").read_text(encoding="utf-8")
    assert "尚未建立" in index_html


def test_missing_category_directory_is_not_an_error(tmp_path):
    spec_root = _make_spec_root(tmp_path, with_db=False)
    out_dir = tmp_path / "dist"

    index = render_gen.render(spec_root, out_dir)

    assert index["db"] == []
    index_html = (out_dir / "index.html").read_text(encoding="utf-8")
    assert "尚未建立" in index_html


def test_nested_ui_path_preserves_subfolder_and_back_link(tmp_path):
    """ui/pages/xxx.wf.yaml 這種巢狀路徑，輸出要保留子資料夾結構，
    回目錄的連結深度也要跟著正確（不能寫死 '../index.html'）。"""
    spec_root = _make_spec_root(tmp_path, with_ui_nested=True)
    out_dir = tmp_path / "dist"

    index = render_gen.render(spec_root, out_dir)

    assert index["ui"] == ["ui/pages/deal-detail.html"]
    out_path = out_dir / "ui" / "pages" / "deal-detail.html"
    assert out_path.exists()
    html = out_path.read_text(encoding="utf-8")
    assert 'href="../../index.html"' in html


def test_flat_ui_path_back_link_depth(tmp_path):
    spec_root = _make_spec_root(tmp_path, with_ui_nested=False)
    out_dir = tmp_path / "dist"
    render_gen.render(spec_root, out_dir)

    html = (out_dir / "ui" / "deal-detail.html").read_text(encoding="utf-8")
    assert 'href="../index.html"' in html


def test_index_links_are_all_valid_relative_paths(tmp_path):
    spec_root = _make_spec_root(tmp_path, with_ui_nested=True)
    out_dir = tmp_path / "dist"
    render_gen.render(spec_root, out_dir)

    index_html = (out_dir / "index.html").read_text(encoding="utf-8")
    for href in ["glossary.html", "db/schema.html", "api/main.html", "ui/pages/deal-detail.html", "logic/rules/deal-approval.html"]:
        assert f'href="{href}"' in index_html
        assert (out_dir / href).exists()
