"""next_action / lifecycle 的整合測試：走一遍 draft -> delivered -> ready -> applied。"""

import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT))

from lib.workflow import next_action  # noqa: E402

VALID_PROPOSAL = """\
---
id: PROP-0001
title: "測試用提案"
impact_surface:
  - .spec/db/schema.dbml
status: {status}
---

## 1. 為什麼 (Why)

因為要測試整個流程。

## 2. 目標 (Goals)

- 讓端到端測試通過

## 3. 非目標 (Non-Goals)

- 不處理無關的事

## 4. 影響範圍 (Impact Surface)

- db: deals 表
"""

INVALID_PROPOSAL = """\
---
id: PROP-0002
title: "缺少非目標區塊"
impact_surface:
  - x
status: draft
---

## 1. 為什麼 (Why)

沒有第三節。
"""

VALID_TASKS = """\
---
change: {change_id}
---

- [ ] task-a: 描述一 (touches: db/schema.dbml)
"""


def _make_change(tmp_path, status="draft", with_tasks=False, valid_proposal=True):
    change_id = "CP-153-discount-reason-visibility"
    change_dir = tmp_path / change_id
    change_dir.mkdir()

    body = VALID_PROPOSAL.format(status=status) if valid_proposal else INVALID_PROPOSAL
    (change_dir / "proposal.md").write_text(body, encoding="utf-8")

    if with_tasks:
        (change_dir / "tasks.md").write_text(VALID_TASKS.format(change_id=change_id), encoding="utf-8")

    return change_dir


def test_invalid_proposal_blocks(tmp_path):
    change_dir = _make_change(tmp_path, valid_proposal=False)
    result = next_action.compute_next(change_dir)
    assert result["next_action"] == "fix_proposal_lint"
    assert result["blocking_errors"]


def test_draft_without_tasks_reports_write_tasks_md_not_a_broken_suggestion(tmp_path):
    """回歸測試（issue #1）：draft 沒有 tasks.md 時，LINT_PASS 轉移的目標
    delivered 會要求 tasks.md，這個轉移現在必須被視為不可行，不能被建議成
    next_action=transition——不然照做下去，change 會立刻進入一個違反自身
    invariant 的狀態，而且連修正用的轉移都會被 gate_check 擋住，等於卡死。"""
    change_dir = _make_change(tmp_path, status="draft", with_tasks=False)
    result = next_action.compute_next(change_dir)
    assert result["next_action"] == "write_tasks_md"
    assert result["blocking_errors"]


def test_draft_with_tasks_already_written_suggests_auto_transition(tmp_path):
    """tasks.md 在 draft 階段就先寫好（draft 本身不要求，但沒人禁止提前寫），
    LINT_PASS 轉移到 delivered 後前提就已經滿足，應該正常建議這個轉移。"""
    change_dir = _make_change(tmp_path, status="draft", with_tasks=True)
    result = next_action.compute_next(change_dir)
    assert result["next_action"] == "transition"
    assert result["target_status"] == "delivered"
    assert not result["blocking_errors"]


def test_delivered_without_tasks_blocks(tmp_path):
    change_dir = _make_change(tmp_path, status="delivered", with_tasks=False)
    result = next_action.compute_next(change_dir)
    assert result["next_action"] == "write_tasks_md"


def test_delivered_with_tasks_awaits_manual_signal(tmp_path):
    change_dir = _make_change(tmp_path, status="delivered", with_tasks=True)
    result = next_action.compute_next(change_dir)
    assert result["next_action"] == "await_manual_signal"
    assert set(result["available_events"]) == {"ISSUE_FOUND", "DEV_DONE"}


def test_ready_awaits_merge(tmp_path):
    change_dir = _make_change(tmp_path, status="ready", with_tasks=True)
    result = next_action.compute_next(change_dir)
    assert result["next_action"] == "await_manual_signal"
    assert result["available_events"] == ["MERGED"]


def test_applied_is_terminal(tmp_path):
    change_dir = _make_change(tmp_path, status="applied", with_tasks=True)
    result = next_action.compute_next(change_dir)
    assert result["next_action"] is None
    assert not result["blocking_errors"]


def test_unknown_status_blocks(tmp_path):
    change_dir = _make_change(tmp_path, status="not_a_real_state")
    result = next_action.compute_next(change_dir)
    assert result["next_action"] == "fix_proposal_status"


def test_extra_file_blocks_before_anything_else(tmp_path):
    change_dir = _make_change(tmp_path, status="draft")
    (change_dir / "NOTES.md").write_text("AI 自己多寫的", encoding="utf-8")
    result = next_action.compute_next(change_dir)
    assert result["next_action"] == "fix_change_shape"
    assert result["status"] is None


def test_gate_check_blocks_shape_violation_regardless_of_status(tmp_path):
    """回歸測試：之前 transition 只在 auto 事件才重驗 proposal_lint，manual 事件
    （DEV_DONE 等）完全沒被驗證，導致白名單/task_lint 形同虛設。gate_check 現在
    是 next 與 transition 共用的唯一入口，這裡直接鎖住它對違規案例不會放行。"""
    change_dir = _make_change(tmp_path, status="delivered", with_tasks=True)
    (change_dir / "NOTES.md").write_text("不該存在", encoding="utf-8")

    gate = next_action.gate_check(change_dir)
    assert gate["ok"] is False
    assert gate["next_action"] == "fix_change_shape"


def test_gate_check_blocks_when_tasks_missing_even_if_shape_and_proposal_ok(tmp_path):
    change_dir = _make_change(tmp_path, status="delivered", with_tasks=False)

    gate = next_action.gate_check(change_dir)
    assert gate["ok"] is False
    assert gate["next_action"] == "write_tasks_md"


def test_gate_check_passes_when_everything_valid(tmp_path):
    change_dir = _make_change(tmp_path, status="delivered", with_tasks=True)

    gate = next_action.gate_check(change_dir)
    assert gate["ok"] is True
    assert gate["status"] == "delivered"


def test_check_state_prerequisites_flags_missing_tasks(tmp_path):
    """issue #1 的核心單元測試：驗證『進入』某個狀態的前提，不是驗證目前狀態。"""
    change_dir = _make_change(tmp_path, status="draft", with_tasks=False)
    gate = next_action.gate_check(change_dir)
    lc = gate["lifecycle"]

    ok, action, errors = next_action.check_state_prerequisites(change_dir, lc, "delivered")
    assert ok is False
    assert action == "write_tasks_md"
    assert errors


def test_check_state_prerequisites_passes_when_tasks_exist(tmp_path):
    change_dir = _make_change(tmp_path, status="draft", with_tasks=True)
    gate = next_action.gate_check(change_dir)
    lc = gate["lifecycle"]

    ok, action, errors = next_action.check_state_prerequisites(change_dir, lc, "delivered")
    assert ok is True
    assert action is None
    assert errors == []


HOTFIX_PROPOSAL = """\
---
id: PROP-0003
title: "資料庫連線池爆掉"
impact_surface:
  - .spec/db/schema.dbml
type: hotfix
status: draft
---

## 症狀 (Symptom)

連線數衝到上限，API 全部逾時。
"""


def _make_hotfix_change(tmp_path):
    change_id = "CP-999-hotfix"
    change_dir = tmp_path / change_id
    change_dir.mkdir()
    (change_dir / "proposal.md").write_text(HOTFIX_PROPOSAL, encoding="utf-8")
    return change_dir


def test_hotfix_type_surfaces_emergency_event_when_normal_path_blocked(tmp_path):
    """回歸測試：hotfix 類型在 draft 階段還沒寫 tasks.md 是常態（tasks.md 本來
    就是事後才補的驗屍報告）。LINT_PASS 的目標 delivered 要求 tasks.md，這時候
    不可行；HOTFIX_LIVE 標記了 skip_target_check，仍然可行。這裡要確認在
    LINT_PASS 被擋住時，HOTFIX_LIVE 沒有被一起犧牲掉——找不到可行的 auto
    轉移，要退而求其次找可行的 manual 轉移，而不是直接放棄回報。"""
    change_dir = _make_hotfix_change(tmp_path)
    result = next_action.compute_next(change_dir)

    assert result["next_action"] == "await_manual_signal"
    assert result["available_events"] == ["HOTFIX_LIVE"]


def test_hotfix_type_with_tasks_already_written_prefers_normal_path(tmp_path):
    """如果 tasks.md 已經先寫好了，LINT_PASS 的目標前提也滿足，應該正常建議
    走 LINT_PASS，HOTFIX_LIVE 仍然作為 other_events 露出，不會被藏起來。"""
    change_id = "CP-999-hotfix"
    change_dir = tmp_path / change_id
    change_dir.mkdir()
    (change_dir / "proposal.md").write_text(HOTFIX_PROPOSAL, encoding="utf-8")
    (change_dir / "tasks.md").write_text(VALID_TASKS.format(change_id=change_id), encoding="utf-8")

    result = next_action.compute_next(change_dir)
    assert result["next_action"] == "transition"
    assert result["suggested_command"].endswith("LINT_PASS")
    assert "other_events" in result
    assert "HOTFIX_LIVE" in result["other_events"]


def test_feature_type_without_tasks_reports_write_tasks_md(tmp_path):
    change_dir = _make_change(tmp_path, status="draft", with_tasks=False)  # 預設 feature type
    result = next_action.compute_next(change_dir)

    assert result["next_action"] == "write_tasks_md"
    assert "other_events" not in result  # feature 類型在 draft 沒有其他手動事件可選


def test_gate_check_rejects_hotfix_live_for_feature_type_via_transition_layer(tmp_path):
    """gate_check 本身不擋 type 不合法的事件（那是 lifecycle 層的事），但
    確認 available_transitions 在來源頭就把它篩掉，兩層合起來才不會漏放。"""
    change_dir = _make_change(tmp_path, status="draft")  # feature type
    gate = next_action.gate_check(change_dir)
    lc = gate["lifecycle"]
    available = lc.available_transitions(gate["status"], gate["type"])
    assert "HOTFIX_LIVE" not in [t.event for t in available]


VALID_DESIGN = """\
---
change: {change_id}
---

## ⏳ 待確認（0）

## 決策 (Decisions)

### ✅ D1 — 示範決策

理由。
"""

INVALID_DESIGN = """\
---
change: {change_id}
---

## 決策 (Decisions)

### ⏳ D1 — 缺摘要的決策

還沒定案，但檔案最上方沒有待確認摘要區塊。
"""


def test_gate_check_passes_when_design_md_absent(tmp_path):
    """design.md 是可選檔案，不存在時完全不影響 gate_check。"""
    change_dir = _make_change(tmp_path, status="delivered", with_tasks=True)
    gate = next_action.gate_check(change_dir)
    assert gate["ok"] is True


def test_gate_check_passes_when_design_md_valid(tmp_path):
    change_dir = _make_change(tmp_path, status="delivered", with_tasks=True)
    change_id = change_dir.name
    (change_dir / "design.md").write_text(VALID_DESIGN.format(change_id=change_id), encoding="utf-8")

    gate = next_action.gate_check(change_dir)
    assert gate["ok"] is True


def test_gate_check_blocks_when_design_md_invalid(tmp_path):
    """design.md 雖然是可選的，但只要它存在就必須合法——不會因為可選就放鬆檢查。"""
    change_dir = _make_change(tmp_path, status="delivered", with_tasks=True)
    change_id = change_dir.name
    (change_dir / "design.md").write_text(INVALID_DESIGN.format(change_id=change_id), encoding="utf-8")

    gate = next_action.gate_check(change_dir)
    assert gate["ok"] is False
    assert gate["next_action"] == "fix_design_lint"
