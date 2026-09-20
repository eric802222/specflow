"""issue #1 的端到端回歸測試：任何轉移執行前都必須先驗證「目標狀態」本身合法，
不是只驗證「目前狀態」合法。"""

import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT))

from bin import specflow as cli  # noqa: E402

VALID_PROPOSAL = """\
---
id: CP-1
title: "測試用提案"
impact_surface:
  - x
status: draft
---

## 1. 為什麼 (Why)

測試用。

## 2. 目標 (Goals)

- 測試

## 3. 非目標 (Non-Goals)

- 無
"""


def _run(argv):
    parser = cli.build_parser()
    args = parser.parse_args(argv)
    return args.func(args)


def test_transition_blocks_when_target_state_would_be_invalid(tmp_path):
    """draft 沒有 tasks.md 時，LINT_PASS 轉移到 delivered（要求 tasks.md）必須
    被擋下，不能讓 change 進入一個立刻違反自身 invariant 的狀態。"""
    spec_root = tmp_path / ".spec"
    change_dir = spec_root / "changes" / "CP-1"
    change_dir.mkdir(parents=True)
    (change_dir / "proposal.md").write_text(VALID_PROPOSAL, encoding="utf-8")

    exit_code = _run(["transition", "--spec-root", str(spec_root), "CP-1", "LINT_PASS"])

    assert exit_code == 1
    status_text = (change_dir / "proposal.md").read_text(encoding="utf-8")
    assert "status: draft" in status_text  # 沒有被改動


def test_transition_succeeds_once_tasks_written_first(tmp_path):
    """把 tasks.md 提前寫好，LINT_PASS 就能正常轉移到 delivered。"""
    spec_root = tmp_path / ".spec"
    change_dir = spec_root / "changes" / "CP-1"
    change_dir.mkdir(parents=True)
    (change_dir / "proposal.md").write_text(VALID_PROPOSAL, encoding="utf-8")
    (change_dir / "tasks.md").write_text(
        "---\nchange: CP-1\n---\n\n- [ ] task-a: 描述 (touches: x)\n",
        encoding="utf-8",
    )

    exit_code = _run(["transition", "--spec-root", str(spec_root), "CP-1", "LINT_PASS"])

    assert exit_code == 0
    status_text = (change_dir / "proposal.md").read_text(encoding="utf-8")
    assert "status: delivered" in status_text


def test_transition_cannot_get_stuck_after_being_blocked(tmp_path):
    """回歸測試：曾經一旦不小心進入非法狀態，連修正用的轉移都會被 gate_check
    擋死。現在因為根本不允許進入非法狀態，這個情境不該再發生——這裡驗證
    被擋下的那次操作完全沒有改變 change 的狀態，之後照正常路徑走仍然愃通。"""
    spec_root = tmp_path / ".spec"
    change_dir = spec_root / "changes" / "CP-1"
    change_dir.mkdir(parents=True)
    (change_dir / "proposal.md").write_text(VALID_PROPOSAL, encoding="utf-8")

    # 先嘗試一次會被擋下的轉移
    assert _run(["transition", "--spec-root", str(spec_root), "CP-1", "LINT_PASS"]) == 1

    # status 仍是 draft，補上 tasks.md 後同一個轉移應該能正常成功
    (change_dir / "tasks.md").write_text(
        "---\nchange: CP-1\n---\n\n- [ ] task-a: 描述 (touches: x)\n",
        encoding="utf-8",
    )
    assert _run(["transition", "--spec-root", str(spec_root), "CP-1", "LINT_PASS"]) == 0
