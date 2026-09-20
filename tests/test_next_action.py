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


def test_draft_with_valid_proposal_suggests_auto_transition(tmp_path):
    change_dir = _make_change(tmp_path, status="draft")
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
