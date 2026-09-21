"""prompt_gen 的單元測試：用臨時 git repo 驗證組出來的 Prompt 內容。"""

import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT))

from lib.generators import prompt_gen  # noqa: E402


def _git(repo_dir, *args):
    subprocess.run(["git", *args], cwd=repo_dir, check=True, capture_output=True)


PROPOSAL = """\
---
id: CP-1
title: "換貨折扣申請新增理由欄位"
impact_surface:
  - .spec/db/schema.dbml
status: delivered
---

## 1. 為什麼 (Why)

業務看不到理由。

## 3. 非目標 (Non-Goals)

- 不做自動核准
"""


def _init_repo_with_change(tmp_path):
    repo_dir = tmp_path / "repo"
    repo_dir.mkdir()
    _git(repo_dir, "init", "-q")
    _git(repo_dir, "config", "user.email", "test@example.com")
    _git(repo_dir, "config", "user.name", "test")

    spec_root = repo_dir / ".spec"
    specs_dir = spec_root / "specs"
    (specs_dir / "db").mkdir(parents=True)
    (specs_dir / "db" / "schema.dbml").write_text("Table x {}\n", encoding="utf-8")

    change_dir = spec_root / "changes" / "CP-1"
    change_dir.mkdir(parents=True)
    (change_dir / "proposal.md").write_text(PROPOSAL, encoding="utf-8")

    _git(repo_dir, "add", ".")
    _git(repo_dir, "commit", "-q", "-m", "init")
    _git(repo_dir, "branch", "-q", "-m", "main")

    return repo_dir, spec_root, change_dir


def test_prompt_includes_title_and_diff(tmp_path):
    repo_dir, spec_root, change_dir = _init_repo_with_change(tmp_path)

    _git(repo_dir, "checkout", "-q", "-b", "change/CP-1")
    (spec_root / "specs" / "db" / "schema.dbml").write_text(
        "Table x { reason_note text }\n", encoding="utf-8"
    )
    _git(repo_dir, "add", ".")
    _git(repo_dir, "commit", "-q", "-m", "add reason_note")

    prompt = prompt_gen.build_prompt("CP-1", change_dir, spec_root, base_ref="main")

    assert "換貨折扣申請新增理由欄位" in prompt
    assert "reason_note" in prompt
    assert "db: 1 個檔案" in prompt
    assert "業務看不到理由" in prompt


def test_prompt_notes_when_no_diff(tmp_path):
    repo_dir, spec_root, change_dir = _init_repo_with_change(tmp_path)

    prompt = prompt_gen.build_prompt("CP-1", change_dir, spec_root, base_ref="main")
    assert "無變更" in prompt


def test_prompt_includes_tasks_content(tmp_path):
    """回歸測試（issue #2）：交付內容必須真的包含 tasks.md，不能只有 proposal
    摘要跟 diff——不然 commit 訊息要求的 <task-id>，AI 根本沒東西可以引用。"""
    repo_dir, spec_root, change_dir = _init_repo_with_change(tmp_path)
    (change_dir / "tasks.md").write_text(
        "---\nchange: CP-1\n---\n\n"
        "- [ ] add-reason-field: 加上 reason_note 欄位 (touches: db/schema.dbml)\n"
        "- [ ] show-in-ui: 核准頁面顯示理由 (touches: ui/pages/approval.wf.yaml)\n",
        encoding="utf-8",
    )

    prompt = prompt_gen.build_prompt("CP-1", change_dir, spec_root, base_ref="main")

    assert "add-reason-field" in prompt
    assert "show-in-ui" in prompt
    assert "reason_note" in prompt
    # 順序要保留，不能被打散重排
    assert prompt.index("add-reason-field") < prompt.index("show-in-ui")


def test_prompt_notes_when_tasks_missing(tmp_path):
    """tasks.md 還沒建立時，輸出裡要清楚說明，不能假裝有內容。"""
    repo_dir, spec_root, change_dir = _init_repo_with_change(tmp_path)

    prompt = prompt_gen.build_prompt("CP-1", change_dir, spec_root, base_ref="main")
    assert "尚未建立 tasks.md" in prompt


def test_base_ref_auto_detects_master_when_not_specified(tmp_path):
    """回歸測試：新 repo 預設分支常常是 master 不是 main，之前 base_ref 預設值
    寫死 'main'，這種 repo 一律直接噴 'fatal: bad revision main'。現在不明確
    傳 base_ref 時要能自動找到真正存在的預設分支。"""
    repo_dir = tmp_path / "repo"
    repo_dir.mkdir()
    _git(repo_dir, "init", "-q")
    _git(repo_dir, "config", "user.email", "test@example.com")
    _git(repo_dir, "config", "user.name", "test")

    spec_root = repo_dir / ".spec"
    specs_dir = spec_root / "specs"
    (specs_dir / "db").mkdir(parents=True)
    (specs_dir / "db" / "schema.dbml").write_text("Table x {}\n", encoding="utf-8")

    change_dir = spec_root / "changes" / "CP-1"
    change_dir.mkdir(parents=True)
    (change_dir / "proposal.md").write_text(PROPOSAL, encoding="utf-8")

    _git(repo_dir, "add", ".")
    _git(repo_dir, "commit", "-q", "-m", "init")
    _git(repo_dir, "branch", "-q", "-m", "master")  # 明確模擬預設分支是 master

    # 不傳 base_ref（None），要能自動 fallback 到 master，而不是噴錯
    prompt = prompt_gen.build_prompt("CP-1", change_dir, spec_root, base_ref=None)
    assert "base_ref" not in prompt  # 不該把變數名字面值漏出來
    assert "相對於 master" in prompt


def test_delivery_requirements_only_mention_layers_actually_touched(tmp_path):
    """回歸測試（issue #14）：交付要求原本無條件塞進 db/api/logic 三條指示，
    一個完全沒用某種 DSL 的專案，AI 讀到會困惑那些檔案哪來的。現在只有 diff
    實際動到的層才會出現對應指示。"""
    repo_dir, spec_root, change_dir = _init_repo_with_change(tmp_path)

    _git(repo_dir, "checkout", "-q", "-b", "change/CP-1")
    (spec_root / "specs" / "db" / "schema.dbml").write_text(
        "Table x { reason_note text }\n", encoding="utf-8"
    )
    _git(repo_dir, "add", ".")
    _git(repo_dir, "commit", "-q", "-m", "add reason_note")

    prompt = prompt_gen.build_prompt("CP-1", change_dir, spec_root, base_ref="main")

    assert "若 diff 修改了 db/schema.dbml" in prompt  # 這次 diff 真的動了 db
    assert "若 diff 修改了 api/main.tsp" not in prompt  # 沒動 api，不該出現
    assert "若 diff 修改了 logic/rules" not in prompt  # 沒動 logic，不該出現
    assert "只實作 diff 中涉及的規格變更" in prompt  # 固定項目仍然存在
    assert "每完成一個 task 就 commit 一次" in prompt  # 固定項目仍然存在


def test_delivery_requirements_omit_all_conditional_items_when_no_diff(tmp_path):
    repo_dir, spec_root, change_dir = _init_repo_with_change(tmp_path)

    prompt = prompt_gen.build_prompt("CP-1", change_dir, spec_root, base_ref="main")

    assert "若 diff 修改了 db/schema.dbml" not in prompt
    assert "若 diff 修改了 api/main.tsp" not in prompt
    assert "若 diff 修改了 logic/rules" not in prompt
    assert "只實作 diff 中涉及的規格變更" in prompt
