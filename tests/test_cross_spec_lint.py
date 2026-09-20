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
