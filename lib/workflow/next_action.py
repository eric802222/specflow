"""給定一個 change 資料夾，算出「下一步該做什麼」——結構化輸出，不是散文建議。

設計目的：人跟 AI 呼叫同一支函式、拿到同一份 JSON 契約，不需要另外解釋上下文。
"""

from __future__ import annotations

import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(REPO_ROOT))

from lib.linters import change_shape_lint, proposal_lint, task_lint  # noqa: E402
from lib.workflow import lifecycle as lifecycle_mod  # noqa: E402

NEEDS_TASKS_FROM = {"delivered", "respec", "ready"}


def compute_next(change_dir: Path, lifecycle_path: Path = None) -> dict:
    change_id = change_dir.name
    lc = lifecycle_mod.load_lifecycle(lifecycle_path)

    result = {"change_id": change_id}

    # 1) 檔案白名單——最先檢查，因為這是「這個資料夾合不合法」的前提
    shape_result = change_shape_lint.lint_dir(change_dir)
    if not shape_result.ok:
        result.update(status=None, next_action="fix_change_shape", blocking_errors=shape_result.errors)
        return result

    proposal_path = change_dir / "proposal.md"

    # 2) proposal_lint
    p_result = proposal_lint.lint_file(proposal_path)
    fm = proposal_lint.read_frontmatter(proposal_path)
    status = fm.get("status") if isinstance(fm, dict) else None
    status = status or lc.initial
    result["status"] = status

    if not p_result.ok:
        result.update(next_action="fix_proposal_lint", blocking_errors=p_result.errors)
        return result

    if not lc.has_state(status):
        result.update(
            next_action="fix_proposal_status",
            blocking_errors=[f"status '{status}' 不是合法狀態：{sorted(lc.states)}"],
        )
        return result

    # 3) tasks.md（進入 delivered 之後才要求存在）
    tasks_path = change_dir / "tasks.md"
    if status in NEEDS_TASKS_FROM:
        if not tasks_path.exists():
            result.update(
                next_action="write_tasks_md",
                blocking_errors=[f"status 已是 '{status}'，但缺少 tasks.md"],
            )
            return result

        t_result = task_lint.lint_file(tasks_path, expected_change_id=change_id)
        if not t_result.ok:
            result.update(next_action="fix_task_lint", blocking_errors=t_result.errors)
            return result

    # 4) 依狀態機決定下一步
    if lc.is_final(status):
        result.update(next_action=None, blocking_errors=[], message="已是終點狀態，流程結束")
        return result

    auto = lc.auto_transitions(status)
    if auto:
        t = auto[0]
        result.update(
            next_action="transition",
            suggested_command=f"specflow transition {change_id} {t.event}",
            target_status=t.target,
            blocking_errors=[],
        )
        return result

    manual = lc.manual_transitions(status)
    result.update(
        next_action="await_manual_signal",
        available_events=[t.event for t in manual],
        blocking_errors=[],
    )
    return result
