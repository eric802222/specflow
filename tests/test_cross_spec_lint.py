"""cross_spec_lint 的單元測試：驗證 db / api / ui / logic 四層的 status 一致性檢查。"""

import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT))

from lib.linters import cross_spec_lint as csl  # noqa: E402

GLOSSARY = """\
version: 1
terms:
  - key: deal
    term: 交易
    status: [draft, pending_approval, approved, rejected]
"""

DBML_OK = """\
enum deal_status {
  draft
  pending_approval
  approved
  rejected
}
"""

DBML_BAD = """\
enum deal_status {
  draft
  pending_approval
  aproved
  rejected
}
"""

TSP_OK = """\
enum DealStatus {
  draft,
  pending_approval,
  approved,
  rejected,
}
"""

TSP_BAD = """\
enum DealStatus {
  draft,
  approvd,
}
"""

WF_OK = """\
body:
  - when: { state: approved }
    status.strong: 已核准
  - when: { state: pending_approval }
    alert: 等待核准
"""

WF_BAD = """\
body:
  - when: { state: aproved }
    status.strong: 已核准
"""

LOGIC_OK = """\
rules:
  - when: { current_status: approved }
    then: { status: approved }
"""

LOGIC_BAD = """\
rules:
  - when: { current_status: approved }
    then: { status: aproved }
"""


def _write_spec(tmp_path, dbml=DBML_OK, tsp=TSP_OK, wf=WF_OK, logic=LOGIC_OK):
    glossary_path = tmp_path / "glossary.yaml"
    glossary_path.write_text(GLOSSARY, encoding="utf-8")

    spec_root = tmp_path / ".spec"
    (spec_root / "db").mkdir(parents=True)
    (spec_root / "db" / "schema.dbml").write_text(dbml, encoding="utf-8")

    (spec_root / "api").mkdir(parents=True)
    (spec_root / "api" / "main.tsp").write_text(tsp, encoding="utf-8")

    (spec_root / "ui" / "pages").mkdir(parents=True)
    (spec_root / "ui" / "pages" / "deal-detail.wf.yaml").write_text(wf, encoding="utf-8")

    (spec_root / "logic" / "rules").mkdir(parents=True)
    (spec_root / "logic" / "rules" / "deal-approval.yaml").write_text(logic, encoding="utf-8")

    return glossary_path, spec_root


def test_all_layers_consistent_passes(tmp_path):
    glossary_path, spec_root = _write_spec(tmp_path)
    result = csl.lint_entity(glossary_path, "deal", spec_root)
    assert result.ok, result.errors
    assert all(c.checked for c in result.checks)


def test_dbml_mismatch_detected(tmp_path):
    glossary_path, spec_root = _write_spec(tmp_path, dbml=DBML_BAD)
    result = csl.lint_entity(glossary_path, "deal", spec_root)
    assert not result.ok
    assert any("aproved" in e and "[db]" in e for e in result.errors)


def test_tsp_mismatch_detected(tmp_path):
    glossary_path, spec_root = _write_spec(tmp_path, tsp=TSP_BAD)
    result = csl.lint_entity(glossary_path, "deal", spec_root)
    assert not result.ok
    assert any("approvd" in e and "[api]" in e for e in result.errors)


def test_ui_mismatch_detected(tmp_path):
    glossary_path, spec_root = _write_spec(tmp_path, wf=WF_BAD)
    result = csl.lint_entity(glossary_path, "deal", spec_root)
    assert not result.ok
    assert any("aproved" in e and "[ui]" in e for e in result.errors)


def test_logic_mismatch_detected(tmp_path):
    glossary_path, spec_root = _write_spec(tmp_path, logic=LOGIC_BAD)
    result = csl.lint_entity(glossary_path, "deal", spec_root)
    assert not result.ok
    assert any("aproved" in e and "[logic]" in e for e in result.errors)


def test_unknown_entity_skipped_not_an_error(tmp_path):
    """回歸測試：接手一個還沒有規格的既有專案時，大多數實體本來就還沒被
    glossary.yaml 記錄，這不該讓 lint 報錯——只有「已經記錄、但記錄彼此
    矛盾」才算錯誤。「還沒治理」是資料，不是缺陷。"""
    glossary_path, spec_root = _write_spec(tmp_path)
    result = csl.lint_entity(glossary_path, "not_an_entity", spec_root)
    assert result.ok, result.errors
    assert all(not c.checked for c in result.checks)


def test_missing_layers_are_skipped_not_errors(tmp_path):
    glossary_path = tmp_path / "glossary.yaml"
    glossary_path.write_text(GLOSSARY, encoding="utf-8")
    spec_root = tmp_path / ".spec"  # 空的，沒有任何子目錄

    result = csl.lint_entity(glossary_path, "deal", spec_root)
    assert result.ok, result.errors
    assert all(not c.checked for c in result.checks)


# ---------------------------------------------------------------------------
# glossary.yaml 巢狀 nodes（DataHub-aligned Business Glossary，向後相容平舖 terms:）
# ---------------------------------------------------------------------------

NESTED_GLOSSARY = """\
version: "1"
source: helpdesk_spec
nodes:
  - name: 客服工單
    id: ticket-domain
    description: 客服工單相關術語
    terms:
      - name: 工單
        key: ticket
        type: entity
        status: [open, pending, closed]
      - name: 工單留言
        id: ticket_comment
        type: entity
    nodes:
      - name: SLA
        id: sla-sub
        terms:
          - name: 回應時限
            key: response_sla
            type: value
"""


def test_load_glossary_status_map_walks_nested_nodes():
    import tempfile
    with tempfile.TemporaryDirectory() as tmp:
        path = Path(tmp) / "glossary.yaml"
        path.write_text(NESTED_GLOSSARY, encoding="utf-8")

        status_map = csl.load_glossary_status_map(path)

        assert set(status_map.keys()) == {"ticket", "ticket_comment", "response_sla"}
        assert status_map["ticket"] == {"open", "pending", "closed"}


def test_load_glossary_status_map_accepts_id_as_key_alias():
    """巢狀格式的 term 可能只給 id（DataHub 慣例）沒給 key（specflow 既有
    欄位）——兩者都要能被識別成同一件事：term 的識別碼。"""
    import tempfile
    with tempfile.TemporaryDirectory() as tmp:
        path = Path(tmp) / "glossary.yaml"
        path.write_text(NESTED_GLOSSARY, encoding="utf-8")

        status_map = csl.load_glossary_status_map(path)
        assert "ticket_comment" in status_map  # 只有 id，沒有 key


def test_cross_spec_lint_works_against_nested_glossary(tmp_path):
    """端到端回歸測試：巢狀 glossary 底下的實體，一樣能正常跑完整套
    cross_spec_lint（不會因為換了 glossary 結構就整條檢查失效）。"""
    glossary_path = tmp_path / "glossary.yaml"
    nested_with_ticket_status = NESTED_GLOSSARY  # ticket 的 status 已含 open/pending/closed
    glossary_path.write_text(nested_with_ticket_status, encoding="utf-8")

    spec_root = tmp_path / ".spec"
    (spec_root / "logic" / "rules").mkdir(parents=True)
    (spec_root / "logic" / "rules" / "ticket.yaml").write_text(
        "rules:\n  - when: { current_status: open }\n    then: { status: closed }\n",
        encoding="utf-8",
    )

    result = csl.lint_entity(glossary_path, "ticket", spec_root)
    assert result.ok, result.errors
