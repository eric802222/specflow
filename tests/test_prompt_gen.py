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
