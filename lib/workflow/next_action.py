"""給定一個 change 資料夾，算出「下一步該做什麼」——結構化輸出，不是散文建議。

`gate_check()` 是核心：任何要改變 change 狀態的動作都必須先通過它，不管是走
`specflow next`（只是建議）還是 `specflow transition`（真正執行）。這兩者共用同
一份檢查邏輯，不允許各自維護一份導致行為不同步——OpenSpec 自己就踩過這個坑：
`openspec validate` 過了，`openspec archive` 才發現不合法（validate/archive 用
不同的檢查路徑，互相不同步）。這裡刻意只寫一份 gate，`compute_next` 用它來算
建議，`transition` 用它來擋下不合法的操作，兩邊看到的答案保證一致。

`check_state_prerequisites()` 是第二個關鍵函式：驗證「進入某個狀態」的前提條件
是否滿足。`gate_check` 用它驗證目前狀態，`compute_next`／`transition` 也用它
驗證轉移完成後的目標狀態（除非該轉移標記 `skip_target_check`）——曾經真的有過
一個漏洞：`gate_check` 只驗證目前狀態，沒驗證轉移後的狀態，導致一個合法操作
（例如 draft 通過 LINT_PASS）可以把 change 送進一個立刻違反自身 invariant 的
狀態（delivered 要求 tasks.md，但 draft 不要求，轉移當下沒人檢查 tasks.md 存不
存在），而且送進去之後連修正用的轉移事件都會被 gate_check 擋住，等於卡死。
現在任何轉移執行前都會先確認「執行後的狀態」本身就是合法的，不會產生一個一
出生就違規的 change。
"""

from __future__ import annotations

import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(REPO_ROOT))

from lib.linters import change_shape_lint, proposal_lint, task_lint  # noqa: E402
from lib.workflow import lifecycle as lifecycle_mod  # noqa: E402


def check_state_prerequisites(change_dir: Path, lc, status: str):
    """檢查『進入』某個狀態的前提條件是否已經滿足（目前只有 requires_tasks）。

    回傳 (ok, next_action, errors)：ok=True 時 next_action 是 None、errors 是
    空清單。這個函式故意跟 status 是「目前狀態」還是「轉移後的目標狀態」無關——
    呼叫端要驗證哪個狀態，就傳哪個狀態進來，邏輯只有一份。
    """
    if lc.requires_tasks(status):
        tasks_path = change_dir / "tasks.md"
        if not tasks_path.exists():
            return False, "write_tasks_md", [f"狀態 '{status}' 要求 tasks.md 存在，但目前沒有"]

        t_result = task_lint.lint_file(tasks_path, expected_change_id=change_dir.name)
        if not t_result.ok:
            return False, "fix_task_lint", t_result.errors

    return True, None, []


def _target_ok(change_dir: Path, lc, transition) -> bool:
    """轉移標記 skip_target_check 就不驗證目標狀態（目前只有 HOTFIX_LIVE 這種
    刻意設計成『先進入、事後補前提』的轉移會這樣標記），否則照常驗證。"""
    if transition.skip_target_check:
        return True
    return check_state_prerequisites(change_dir, lc, transition.target)[0]


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

    ok, action, errors = check_state_prerequisites(change_dir, lc, status)
    if not ok:
        return {
            "change_id": change_id,
            "status": status,
            "type": proposal_type,
            "lifecycle": lc,
            "ok": False,
            "next_action": action,
            "blocking_errors": errors,
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

    # 再篩一次：轉移後的目標狀態本身要合法（除非該轉移標記 skip_target_check），
    # 不然 `next` 會建議一個一執行就立刻爆炸的動作。
    viable = [t for t in available if _target_ok(change_dir, lc, t)]
    viable_auto = [t for t in viable if t.auto]
    viable_manual = [t for t in viable if not t.auto]

    if viable_auto:
        t = viable_auto[0]
        result = {
            "change_id": change_id,
            "status": status,
            "next_action": "transition",
            "suggested_command": f"specflow transition {change_id} {t.event}",
            "target_status": t.target,
            "blocking_errors": [],
        }
        # 即使有自動轉移可用，也不能把其他合法選項（例如緊急通道 HOTFIX_LIVE）
        # 悄悄藏起來——不然 AI/人只會看到「該走的正常流程」，永遠不知道還有
        # 別的合法選項存在。
        others = [x.event for x in viable if x is not t]
        if others:
            result["other_events"] = others
        return result

    if viable_manual:
        return {
            "change_id": change_id,
            "status": status,
            "next_action": "await_manual_signal",
            "available_events": [t.event for t in viable_manual],
            "blocking_errors": [],
        }

    # 沒有任何目前可行的轉移：找出最該報的那個原因。優先看本來預期的 auto
    # 轉移被什麼擋住（那通常是「正常流程」，最有指引價值）；沒有 auto 的話
    # 就看第一個 available 的轉移被什麼擋住。
    auto_all = [t for t in available if t.auto]
    blocker = auto_all[0] if auto_all else (available[0] if available else None)

    if blocker is None:
        return {
            "change_id": change_id,
            "status": status,
            "next_action": None,
            "blocking_errors": [],
            "message": "此狀態沒有任何合法轉移",
        }

    _ok, action, errors = check_state_prerequisites(change_dir, lc, blocker.target)
    return {
        "change_id": change_id,
        "status": status,
        "next_action": action,
        "blocking_errors": [
            f"轉移到 '{blocker.target}'（事件 {blocker.event}）前必須先滿足："
        ]
        + errors,
    }
