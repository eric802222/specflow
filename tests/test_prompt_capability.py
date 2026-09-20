"""issue #2 / #3 的 CLI 端到端測試：`specflow prompt` 依 lifecycle 的 `allows`
capability 判斷能不能產生交付內容，不是自己在程式碼裡寫死規則。"""

import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT))

from bin import specflow as cli  # noqa: E402


def _git(repo_dir, *args):
    subprocess.run(["git", *args], cwd=repo_dir, check=True, capture_output=True)


DRAFT_PROPOSAL = """\
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

DELIVERED_PROPOSAL = DRAFT_PROPOSAL.replace("status: draft", "status: delivered")


def _run(argv):
    parser = cli.build_parser()
    args = parser.parse_args(argv)
    return args.func(args)


def _init_repo(tmp_path):
    repo_dir = tmp_path / "repo"
    repo_dir.mkdir()
    _git(repo_dir, "init", "-q")
    _git(repo_dir, "config", "user.email", "test@example.com")
    _git(repo_dir, "config", "user.name", "test")

    spec_root = repo_dir / ".spec"
    (spec_root / "specs" / "db").mkdir(parents=True)
    (spec_root / "specs" / "db" / "schema.dbml").write_text("Table x {}\n", encoding="utf-8")

    _git(repo_dir, "add", ".")
    _git(repo_dir, "commit", "-q", "-m", "init")
    _git(repo_dir, "branch", "-q", "-m", "main")

    return repo_dir, spec_root


def test_prompt_refused_when_status_does_not_allow_generate_delivery(tmp_path):
    """draft 狀態不在 allows 清單裡有 generate_delivery，不該讓 prompt 產生
    出來——draft 都還沒審完，交付內容還太早。"""
    repo_dir, spec_root = _init_repo(tmp_path)
    change_dir = spec_root / "changes" / "CP-1"
    change_dir.mkdir(parents=True)
    (change_dir / "proposal.md").write_text(DRAFT_PROPOSAL, encoding="utf-8")

    exit_code = _run(["prompt", "--spec-root", str(spec_root), "CP-1"])
    assert exit_code == 1


def test_prompt_succeeds_when_status_allows_generate_delivery(tmp_path):
    repo_dir, spec_root = _init_repo(tmp_path)
    change_dir = spec_root / "changes" / "CP-1"
    change_dir.mkdir(parents=True)
    (change_dir / "proposal.md").write_text(DELIVERED_PROPOSAL, encoding="utf-8")
    (change_dir / "tasks.md").write_text(
        "---\nchange: CP-1\n---\n\n- [ ] task-a: 描述 (touches: db/schema.dbml)\n",
        encoding="utf-8",
    )

    exit_code = _run(["prompt", "--spec-root", str(spec_root), "CP-1"])
    assert exit_code == 0


def test_prompt_refused_when_applied_state_does_not_allow_it(tmp_path):
    """applied 是終點狀態，allows 是空清單——已經封存的 change 不該再產生交付內容。"""
    repo_dir, spec_root = _init_repo(tmp_path)
    change_dir = spec_root / "changes" / "CP-1"
    change_dir.mkdir(parents=True)
    applied_proposal = DRAFT_PROPOSAL.replace("status: draft", "status: applied")
    (change_dir / "proposal.md").write_text(applied_proposal, encoding="utf-8")
    (change_dir / "tasks.md").write_text(
        "---\nchange: CP-1\n---\n\n- [ ] task-a: 描述 (touches: db/schema.dbml)\n",
        encoding="utf-8",
    )

    exit_code = _run(["prompt", "--spec-root", str(spec_root), "CP-1"])
    assert exit_code == 1
