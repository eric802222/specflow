"""lib.workflow.lifecycle 的單元測試。"""

import sys
import tempfile
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT))

from lib.workflow import lifecycle as lifecycle_mod  # noqa: E402


def test_bundled_default_requires_tasks_matches_design():
    lc = lifecycle_mod.load_lifecycle()
    assert lc.requires_tasks("draft") is False
    assert lc.requires_tasks("delivered") is True
    assert lc.requires_tasks("respec") is True
    assert lc.requires_tasks("ready") is True


def test_requires_tasks_defaults_false_for_unknown_state():
    lc = lifecycle_mod.load_lifecycle()
    assert lc.requires_tasks("not_a_real_state") is False


def test_unquoted_on_key_still_parsed_correctly():
    """回歸測試：YAML 1.1 會把沒加引號的 on: 解析成布林值 True 當 key，
    這裡故意寫一份沒加引號的版本，確認 transitions() 還是找得到。"""
    yaml_text = """\
id: test
initial: a
states:
  a:
    on:
      GO:
        target: b
        auto: true
  b:
    final: true
"""
    with tempfile.TemporaryDirectory() as d:
        p = Path(d) / "lifecycle.yaml"
        p.write_text(yaml_text, encoding="utf-8")
        lc = lifecycle_mod.load_lifecycle(p)

    transitions = lc.transitions("a")
    assert len(transitions) == 1
    assert transitions[0].event == "GO"
    assert transitions[0].target == "b"
    assert transitions[0].auto is True


def test_custom_lifecycle_can_override_bundled_default():
    yaml_text = """\
id: minimal
initial: only
states:
  only:
    final: true
"""
    with tempfile.TemporaryDirectory() as d:
        p = Path(d) / "lifecycle.yaml"
        p.write_text(yaml_text, encoding="utf-8")
        lc = lifecycle_mod.load_lifecycle(p)

    assert lc.id == "minimal"
    assert lc.is_final("only") is True
    assert lc.has_state("draft") is False  # 不是預設那五個狀態了


def test_hotfix_live_requires_matching_type():
    lc = lifecycle_mod.load_lifecycle()
    t = lc.find_transition("draft", "HOTFIX_LIVE")
    assert t is not None
    assert t.requires_type == "hotfix"


def test_available_transitions_filters_out_wrong_type():
    lc = lifecycle_mod.load_lifecycle()

    available_feature = lc.available_transitions("draft", "feature")
    assert "HOTFIX_LIVE" not in [t.event for t in available_feature]

    available_hotfix = lc.available_transitions("draft", "hotfix")
    assert "HOTFIX_LIVE" in [t.event for t in available_hotfix]
    assert "LINT_PASS" in [t.event for t in available_hotfix]  # 沒限制 type 的轉移永遠可見


def test_find_transition_returns_none_for_unknown_event():
    lc = lifecycle_mod.load_lifecycle()
    assert lc.find_transition("draft", "NOT_A_REAL_EVENT") is None


def test_live_pending_review_requires_tasks_and_leads_to_applied():
    lc = lifecycle_mod.load_lifecycle()
    assert lc.requires_tasks("live_pending_review") is True
    t = lc.find_transition("live_pending_review", "POSTREVIEW_DONE")
    assert t.target == "applied"


def test_hotfix_live_has_skip_target_check():
    lc = lifecycle_mod.load_lifecycle()
    t = lc.find_transition("draft", "HOTFIX_LIVE")
    assert t.skip_target_check is True


def test_lint_pass_does_not_skip_target_check():
    lc = lifecycle_mod.load_lifecycle()
    t = lc.find_transition("draft", "LINT_PASS")
    assert t.skip_target_check is False


def test_allows_reflects_bundled_capabilities():
    lc = lifecycle_mod.load_lifecycle()
    assert lc.allows("draft", "edit_proposal") is True
    assert lc.allows("draft", "generate_delivery") is False
    assert lc.allows("delivered", "generate_delivery") is True
    assert lc.allows("applied", "generate_delivery") is False


def test_allows_defaults_false_for_unknown_state_or_capability():
    lc = lifecycle_mod.load_lifecycle()
    assert lc.allows("not_a_real_state", "generate_delivery") is False
    assert lc.allows("delivered", "not_a_real_capability") is False


def test_baseline_captured_goes_to_dedicated_terminal_state():
    """baseline type 有自己專屬的終點狀態，不跟 applied 共用——applied 的
    requires_tasks=true 是為了留下開發痕跡設計的，baseline 純粹描述現況，
    永遠不會有 tasks.md，套用 applied 語意會讓它永久卡在「未完成」。"""
    lc = lifecycle_mod.load_lifecycle()
    t = lc.find_transition("draft", "BASELINE_CAPTURED")
    assert t is not None
    assert t.requires_type == "baseline"
    assert t.target == "baseline_recorded"
    assert lc.is_final("baseline_recorded") is True
    assert lc.requires_tasks("baseline_recorded") is False


def test_baseline_captured_available_only_for_baseline_type():
    lc = lifecycle_mod.load_lifecycle()
    available_feature = lc.available_transitions("draft", "feature")
    assert "BASELINE_CAPTURED" not in [t.event for t in available_feature]

    available_baseline = lc.available_transitions("draft", "baseline")
    assert "BASELINE_CAPTURED" in [t.event for t in available_baseline]
