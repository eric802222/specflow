"""給定一個 change 資料夾，算出「下一步該做什麼」——結構化輸出，不是散文建議。

`gate_check()` 是核心：任何要改變 change 狀態的動作都必須先通過它，不管是走
`specflow next`（只是建議）還是 `specflow transition`（真正執行）。這兩者共用同
一份檢查邏輯，不允許各自維護一份導致行為不同步——OpenSpec 自己就踩過這個坑：
`openspec validate` 過了，`openspec archive` 才發現不合法（validate/archive 用
不同的檢查路徑，互相不同步）。這裡刻意只寫一份 gate，`compute_next` 用它來算
建議，`transition` 用它來擋下不合法的操作，兩邊看到的答案保證一致。
"""

from __future__ import annotations

import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(REPO_ROOT))

from lib.linters import change_shape_lint, proposal_lint, task_lint  # noqa: E402
from lib.workflow import lifecycle as lifecycle_mod  # noqa: E402


def gate_check(change_dir: Path, lifecycle_path: Path = None) -> dict:
    """跑完白名單 → proposal_lint → status 合法性 → （視狀態需要）task_lint。

    回傳的 dict 一定有 change_id / status / type / lifecycle / ok / next_action /
    blocking_errors 這幾個 key（type 要在 proposal_lint 過關後才讀得到，失敗在
    白名單那關的話沒有 type key）。ok=False 時 next_action 是失敗原因的代號
    （fix_change_shape / fix_proposal_lint / fix_proposal_status /
    write_tasks_md / fix_task_lint），呼叫端可以直接用來擋下操作或印訊息。
    """
    change_id = change_dir.name
    lc = lifecycle_mod.load_lifecycle(lifecycle_path)

    shape_result = change_shape_lint.lint_dir(change_dir)
    if not shape_result.ok:
        return {
            "change_id": change_id,
            "status": None,
            "lifecycle": lc,
            "ok": False,
            "next_action": "fix_change_shape",
            "blocking_errors": shape_result.errors,
        }

    proposal_path = change_dir / "proposal.md"
    p_result = proposal_lint.lint_file(proposal_path)
    fm = proposal_lint.read_frontmatter(proposal_path)
    status = (fm.get("status") if isinstance(fm, dict) else None) or lc.initial
    proposal_type = (fm.get("type") if isinstance(fm, dict) else None) or "feature"

    if not p_result.ok:
        return {
            "change_id": change_id,
            "status": status,
            "type": proposal_type,
            "lifecycle": lc,
            "ok": False,
            "next_action": "fix_proposal_lint",
            "blocking_errors": p_result.errors,
        }

    if not lc.has_state(status):
        return {
            "change_id": change_id,
            "status": status,
            "type": proposal_type,
            "lifecycle": lc,
            "ok": False,
            "next_action": "fix_proposal_status",
            "blocking_errors": [f"status '{status}' 不是合法狀態：{sorted(lc.states)}"],
        }

    tasks_path = change_dir / "tasks.md"
    if lc.requires_tasks(status):
        if not tasks_path.exists():
            return {
                "change_id": change_id,
                "status": status,
                "type": proposal_type,
                "lifecycle": lc,
                "ok": False,
                "next_action": "write_tasks_md",
                "blocking_errors": [f"status 已是 '{status}'，但缺少 tasks.md"],
            }

        t_result = task_lint.lint_file(tasks_path, expected_change_id=change_id)
        if not t_result.ok:
            return {
                "change_id": change_id,
                "status": status,
                "type": proposal_type,
                "lifecycle": lc,
                "ok": False,
                "next_action": "fix_task_lint",
                "blocking_errors": t_result.errors,
            }

    return {
        "change_id": change_id,
        "status": status,
        "type": proposal_type,
        "lifecycle": lc,
        "ok": True,
        "next_action": None,
        "blocking_errors": [],
    }


def compute_next(change_dir: Path, lifecycle_path: Path = None) -> dict:
    gate = gate_check(change_dir, lifecycle_path)

    if not gate["ok"]:
        return {
            "change_id": gate["change_id"],
            "status": gate["status"],
            "next_action": gate["next_action"],
            "blocking_errors": gate["blocking_errors"],
        }

    lc = gate["lifecycle"]
    status = gate["status"]
    change_id = gate["change_id"]
    proposal_type = gate["type"]

    if lc.is_final(status):
        return {
            "change_id": change_id,
            "status": status,
            "next_action": None,
            "blocking_errors": [],
            "message": "已是終點狀態，流程結束",
        }

    # 只考慮這個 proposal 的 type 有資格使用的轉移（例如 HOTFIX_LIVE 只有
    # type: hotfix 才看得到）——不這樣篩選的話，一般 feature 類型的 change
    # 會在 available_events 裡看到不該屬於它的緊急事件。
    available = lc.available_transitions(status, proposal_type)
    auto = [t for t in available if t.auto]
    manual = [t for t in available if not t.auto]

    if auto:
        t = auto[0]
        result = {
            "change_id": change_id,
            "status": status,
            "next_action": "transition",
            "suggested_command": f"specflow transition {change_id} {t.event}",
            "target_status": t.target,
            "blocking_errors": [],
        }
        # 即使有自動轉移可用，也不能把其他手動事件（例如緊急通道 HOTFIX_LIVE）
        # 悄悄藏起來——不然 AI/人只會看到「該走的正常流程」，永遠不知道還有
        # 別的合法選項存在。
        if manual:
            result["other_events"] = [m.event for m in manual]
        return result

    return {
        "change_id": change_id,
        "status": status,
        "next_action": "await_manual_signal",
        "available_events": [t.event for t in manual],
        "blocking_errors": [],
    }
