"""render_gen 的單元測試：真正渲染 vs 退回原始內容、dsl.yaml 覆寫、brownfield 空分類。

所有測試預設（autouse fixture）把外部工具呼叫都模擬成「沒裝」，讓測試不依賴
這台機器有沒有 Node.js、網路、或 wireframe-lofi——需要驗證「工具真的有裝」
那條路徑的測試，個別用 monkeypatch 覆寫回「有裝」。
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
    monkeypatch.setattr(render_gen, "_try_render_command", lambda cmd, src, out=None, timeout=90: False)
    monkeypatch.setattr(render_gen, "_try_render_typespec", lambda src: None)
    monkeypatch.setattr(render_gen, "_find_wireframe_lofi_script", lambda: None)


def _make_spec_root(tmp_path, with_glossary=True, with_db=True, with_ui_nested=False, dsl_yaml=None):
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

    if dsl_yaml is not None:
        (spec_root / "dsl.yaml").write_text(dsl_yaml, encoding="utf-8")

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
# DB：外部工具有裝 vs 沒裝
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
    def fake_render(cmd, src, out=None, timeout=90):
        out.write_text("<svg>fake ER diagram</svg>", encoding="utf-8")
        return True

    monkeypatch.setattr(render_gen, "_try_render_command", fake_render)

    spec_root = _make_spec_root(tmp_path)
    out_dir = tmp_path / "dist"
    render_gen.render(spec_root, out_dir)

    html = (out_dir / "db" / "schema.html").read_text(encoding="utf-8")
    assert "還沒渲染成產物" not in html
    assert '<img src="schema.svg"' in html
    assert (out_dir / "db" / "schema.svg").exists()


# ---------------------------------------------------------------------------
# dsl.yaml：pattern / render_command / install_note 都可以被覆寫
# ---------------------------------------------------------------------------

def test_dsl_yaml_overrides_db_pattern(tmp_path):
    """dsl.yaml 把 db 的 pattern 換成 *.prisma，原本的 .dbml 檔就不會被掃到，
    換成一個新的 .prisma 檔案要能被抓到——證明 core 沒有寫死「db 一定是 DBML」。"""
    dsl_yaml = "db:\n  pattern: '*.prisma'\n"
    spec_root = _make_spec_root(tmp_path, dsl_yaml=dsl_yaml)
    (spec_root / "specs" / "db" / "schema.prisma").write_text("model Deal {}\n", encoding="utf-8")

    out_dir = tmp_path / "dist"
    index = render_gen.render(spec_root, out_dir)

    assert index["db"] == ["db/schema.prisma".replace(".prisma", ".html")]
    assert (out_dir / "db" / "schema.html").exists()
    assert not (out_dir / "db" / "schema-2.html").exists()  # 原本的 .dbml 沒被掃到（不存在對應輸出）


def test_dsl_yaml_overrides_install_note(tmp_path):
    dsl_yaml = "db:\n  install_note: '改用內部工具：internal-db-render --in {src}'\n"
    spec_root = _make_spec_root(tmp_path, dsl_yaml=dsl_yaml)
    out_dir = tmp_path / "dist"
    render_gen.render(spec_root, out_dir)

    html = (out_dir / "db" / "schema.html").read_text(encoding="utf-8")
    assert "internal-db-render" in html
    assert "dbml-renderer" not in html  # 預設的安裝說明被換掉了


def test_dsl_yaml_overrides_render_command(tmp_path, monkeypatch):
    """render_command 被覆寫成別的工具時，_try_render_command 真的會拿到
    覆寫後的樣板，不是預設的 dbml-renderer 呼叫方式。"""
    captured = {}

    def fake_render(cmd, src, out=None, timeout=90):
        captured["cmd"] = cmd
        return False

    monkeypatch.setattr(render_gen, "_try_render_command", fake_render)

    dsl_yaml = "db:\n  render_command: ['my-tool', '--input', '{src}', '--output', '{out}']\n"
    spec_root = _make_spec_root(tmp_path, dsl_yaml=dsl_yaml)
    render_gen.render(spec_root, tmp_path / "dist")

    assert captured["cmd"] == ["my-tool", "--input", "{src}", "--output", "{out}"]


def test_no_dsl_yaml_uses_bundled_defaults(tmp_path):
    """沒有 dsl.yaml 時，load_dsl_config 回傳的就是內建預設值，不會意外變空。"""
    spec_root = _make_spec_root(tmp_path)
    config = render_gen.load_dsl_config(spec_root)

    assert config["db"]["pattern"] == "*.dbml"
    assert config["ui"]["pattern"] == "*.wf.yaml"
    assert "dbml-renderer" in config["db"]["install_note"]


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

    def fake_run(cmd, cwd=None, timeout=90):
        # 模擬 wfyaml.py 真的產生了輸出檔案
        target = Path(cmd[-1])
        target.parent.joinpath(target.name[: -len(".wf.yaml")] + ".html").write_text(
            "<html><body><h1>rendered wireframe here</h1></body></html>", encoding="utf-8"
        )
        return object()

    monkeypatch.setattr(render_gen, "_run", fake_run)

    spec_root = _make_spec_root(tmp_path)
    out_dir = tmp_path / "dist"
    render_gen.render(spec_root, out_dir)

    html = (out_dir / "ui" / "deal-detail.html").read_text(encoding="utf-8")
    assert "還沒渲染成產物" not in html
    assert "rendered wireframe here" in html
    assert "目錄" in html  # 有被插入回目錄的連結


def test_dsl_yaml_overrides_ui_render_command(tmp_path, monkeypatch):
    """ui.render_command 被覆寫時，走的是通用 command 樣板路徑，不是內建的
    wireframe-lofi 探索邏輯——證明 ui 這層真的可以換成別的工具，不是寫死。"""
    def fake_run(cmd, cwd=None, timeout=90):
        assert cmd[0] == "my-other-wireframe-tool"
        target = Path(cmd[1])
        target.parent.joinpath(target.name[: -len(".wf.yaml")] + ".html").write_text(
            "<html><body><h1>from another tool</h1></body></html>", encoding="utf-8"
        )
        return object()

    monkeypatch.setattr(render_gen, "_run", fake_run)
    # 這條測試要驗證「不去找 wireframe-lofi」，所以故意讓探索邏輯回傳有找到，
    # 確認即使找得到，只要 render_command 有值就不會用內建邏輯。
    monkeypatch.setattr(render_gen, "_find_wireframe_lofi_script", lambda: Path("/should/not/be/used.py"))

    dsl_yaml = "ui:\n  render_command: ['my-other-wireframe-tool', '{src}']\n"
    spec_root = _make_spec_root(tmp_path, dsl_yaml=dsl_yaml)
    out_dir = tmp_path / "dist"
    render_gen.render(spec_root, out_dir)

    html = (out_dir / "ui" / "deal-detail.html").read_text(encoding="utf-8")
    assert "from another tool" in html


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


# ---------------------------------------------------------------------------
# Story / Flow：Given/When/Then 需求意圖格式渲染
# ---------------------------------------------------------------------------

VALID_STORY = """\
---
name: "Trade-In 送審流程"
type: story
status: confirm
external_key: INTCUSSS-700
refs:
  - https://qnap-jira.qnap.com.tw/browse/INTCUSSS-700
goal: 業務主管審核時看不到申請理由，需要補上
stories:
  - id: trade_in_submit_with_reason
    given: 客服在 myRMA 送出 Trade-In 申請
    when: 填寫申請理由並送出
    then: 審核頁面能看到這次申請的理由
    children:
      - id: trade_in_submit_with_reason.reason_too_short
        given: 客服在送出申請時
        when: 理由字數不足 20 字
        then: 系統擋下並提示字數不足
---
"""

FLOW_MERMAID = """\
```mermaid
sequenceDiagram
    participant CS as 客服
    participant SP as Sales Portal
    CS->>SP: 送出申請
    SP-->>CS: 顯示審核結果
```
"""


def test_story_page_renders_given_when_then_cards(tmp_path):
    spec_root = tmp_path / ".spec"
    (spec_root / "specs" / "story").mkdir(parents=True)
    (spec_root / "specs" / "story" / "trade-in.story.md").write_text(VALID_STORY, encoding="utf-8")
    out_dir = tmp_path / "dist"

    index = render_gen.render(spec_root, out_dir)

    assert index["story"] == ["story/trade-in.story.html"]
    html = (out_dir / "story" / "trade-in.story.html").read_text(encoding="utf-8")
    assert "還沒渲染成產物" not in html
    assert "trade_in_submit_with_reason" in html
    assert "客服在 myRMA 送出 Trade-In 申請" in html
    assert "status-confirm" in html
    assert "trade_in_submit_with_reason.reason_too_short" in html
    assert "story-card child" in html  # children 有縮排樣式
    assert "INTCUSSS-700" in html
    assert "qnap-jira.qnap.com.tw" in html


def test_story_page_falls_back_on_malformed_content(tmp_path):
    spec_root = tmp_path / ".spec"
    (spec_root / "specs" / "story").mkdir(parents=True)
    (spec_root / "specs" / "story" / "broken.story.md").write_text(
        "---\nname: 缺東缺西\n---\n", encoding="utf-8"
    )
    out_dir = tmp_path / "dist"

    render_gen.render(spec_root, out_dir)

    html = (out_dir / "story" / "broken.story.html").read_text(encoding="utf-8")
    assert "還沒渲染成產物" in html
    assert "story_lint.py" in html


def test_flow_page_renders_mermaid_from_fenced_content(tmp_path):
    spec_root = tmp_path / ".spec"
    (spec_root / "specs" / "story").mkdir(parents=True)
    (spec_root / "specs" / "story" / "flow_trade_in_submit.md").write_text(FLOW_MERMAID, encoding="utf-8")
    out_dir = tmp_path / "dist"

    index = render_gen.render(spec_root, out_dir)

    assert index["story"] == ["story/flow_trade_in_submit.html"]
    html = (out_dir / "story" / "flow_trade_in_submit.html").read_text(encoding="utf-8")
    assert '<pre class="mermaid">' in html
    assert "sequenceDiagram" in html
    assert "```mermaid" not in html  # fence 標記本身要被剝掉，只留純 Mermaid 原始碼
    assert "mermaid.min.js" in html
    assert "mermaid.initialize" in html


def test_flow_page_accepts_unfenced_mermaid_source(tmp_path):
    spec_root = tmp_path / ".spec"
    (spec_root / "specs" / "story").mkdir(parents=True)
    (spec_root / "specs" / "story" / "flow_bare.md").write_text(
        "flowchart TD\n  A --> B\n", encoding="utf-8"
    )
    out_dir = tmp_path / "dist"

    render_gen.render(spec_root, out_dir)

    html = (out_dir / "story" / "flow_bare.html").read_text(encoding="utf-8")
    assert "flowchart TD" in html


def test_story_and_flow_coexist_in_same_directory(tmp_path):
    spec_root = tmp_path / ".spec"
    story_dir = spec_root / "specs" / "story"
    story_dir.mkdir(parents=True)
    (story_dir / "trade-in.story.md").write_text(VALID_STORY, encoding="utf-8")
    (story_dir / "flow_trade_in_submit.md").write_text(FLOW_MERMAID, encoding="utf-8")
    out_dir = tmp_path / "dist"

    index = render_gen.render(spec_root, out_dir)

    assert set(index["story"]) == {"story/trade-in.story.html", "story/flow_trade_in_submit.html"}
