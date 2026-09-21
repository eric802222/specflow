"""這輪修復的端到端測試：init 自動產 tasks.md、lint 吃 change-id、
transition 的 --auto-commit / --commit-ref、REVIEW_PASS/REVIEW_REJECT 完整路徑、
warn_if_no_specs_touch 提醒、REVIEW_PASS 真正檢查 review.md 有沒有待處理項目。"""

import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT))

from bin import specflow as cli  # noqa: E402


def _git(repo_dir, *args):
    subprocess.run(["git", *args], cwd=repo_dir, check=True, capture_output=True)


def _run(argv):
    parser = cli.build_parser()
    args = parser.parse_args(argv)
    return args.func(args)


VALID_PROPOSAL = """\
---
id: CP-1
title: "測試用提案"
impact_surface:
  - x
status: {status}
---

## 1. 為什麼 (Why)

測試用。

## 2. 目標 (Goals)

- 測試

## 3. 非目標 (Non-Goals)

- 無
"""

VALID_TASKS = """\
---
change: CP-1
---

- [ ] task-a: 描述 (touches: x)
"""


def _init_git_repo(tmp_path):
    repo_dir = tmp_path / "repo"
    repo_dir.mkdir()
    _git(repo_dir, "init", "-q")
    _git(repo_dir, "config", "user.email", "test@example.com")
    _git(repo_dir, "config", "user.name", "test")
    (repo_dir / "README.md").write_text("x", encoding="utf-8")
    _git(repo_dir, "add", ".")
    _git(repo_dir, "commit", "-q", "-m", "init")
    return repo_dir


# ---------------------------------------------------------------------------
# init 自動產 tasks.md（feature/bugfix 才產，baseline/hotfix 不產）
# ---------------------------------------------------------------------------

def test_init_feature_auto_generates_tasks_md(tmp_path):
    spec_root = tmp_path / ".spec"
    spec_root.mkdir()
    _run(["init", "--spec-root", str(spec_root), "CP-1", "標題"])
    assert (spec_root / "changes" / "CP-1" / "tasks.md").exists()


def test_init_baseline_does_not_generate_tasks_md(tmp_path):
    spec_root = tmp_path / ".spec"
    spec_root.mkdir()
    _run(["init", "--spec-root", str(spec_root), "CP-1", "標題", "--type", "baseline"])
    assert not (spec_root / "changes" / "CP-1" / "tasks.md").exists()


def test_init_hotfix_does_not_generate_tasks_md(tmp_path):
    """hotfix 的 tasks.md 設計上是事後才補的驗屍報告，init 當下自動生一份
    假的反而是誤導。"""
    spec_root = tmp_path / ".spec"
    spec_root.mkdir()
    _run(["init", "--spec-root", str(spec_root), "CP-1", "標題", "--type", "hotfix"])
    assert not (spec_root / "changes" / "CP-1" / "tasks.md").exists()


# ---------------------------------------------------------------------------
# lint 吃 change-id
# ---------------------------------------------------------------------------

def test_lint_accepts_change_id_not_just_path(tmp_path):
    spec_root = tmp_path / ".spec"
    change_dir = spec_root / "changes" / "CP-1"
    change_dir.mkdir(parents=True)
    (change_dir / "proposal.md").write_text(VALID_PROPOSAL.format(status="draft"), encoding="utf-8")

    exit_code = _run(["lint", "--spec-root", str(spec_root), "CP-1"])
    assert exit_code == 0


# ---------------------------------------------------------------------------
# transition 的 --commit-ref（純紀錄）跟 --auto-commit（真的 git commit）
# ---------------------------------------------------------------------------

def test_transition_commit_ref_writes_frontmatter_without_git_action(tmp_path):
    spec_root = tmp_path / ".spec"
    change_dir = spec_root / "changes" / "CP-1"
    change_dir.mkdir(parents=True)
    (change_dir / "proposal.md").write_text(VALID_PROPOSAL.format(status="draft"), encoding="utf-8")
    (change_dir / "tasks.md").write_text(VALID_TASKS, encoding="utf-8")

    exit_code = _run(
        ["transition", "--spec-root", str(spec_root), "CP-1", "LINT_PASS", "--commit-ref", "abc1234"]
    )
    assert exit_code == 0
    text = (change_dir / "proposal.md").read_text(encoding="utf-8")
    assert "implementation_commit: abc1234" in text


def test_transition_auto_commit_creates_real_git_commit(tmp_path):
    repo_dir = _init_git_repo(tmp_path)
    spec_root = repo_dir / ".spec"
    change_dir = spec_root / "changes" / "CP-1"
    change_dir.mkdir(parents=True)
    (change_dir / "proposal.md").write_text(VALID_PROPOSAL.format(status="draft"), encoding="utf-8")
    (change_dir / "tasks.md").write_text(VALID_TASKS, encoding="utf-8")
    _git(repo_dir, "add", ".")
    _git(repo_dir, "commit", "-q", "-m", "add change")

    exit_code = _run(
        ["transition", "--spec-root", str(spec_root), "CP-1", "LINT_PASS", "--auto-commit"]
    )
    assert exit_code == 0

    status = subprocess.run(
        ["git", "status", "--porcelain"], cwd=repo_dir, capture_output=True, text=True
    ).stdout
    assert status.strip() == ""  # 沒有留下 dirty 工作區

    log = subprocess.run(
        ["git", "log", "-1", "--pretty=%s"], cwd=repo_dir, capture_output=True, text=True
    ).stdout
    assert "CP-1" in log
    assert "LINT_PASS" in log


# ---------------------------------------------------------------------------
# REVIEW_PASS / REVIEW_REJECT 完整路徑
# ---------------------------------------------------------------------------

def _make_ready_change(tmp_path):
    spec_root = tmp_path / ".spec"
    change_dir = spec_root / "changes" / "CP-1"
    change_dir.mkdir(parents=True)
    (change_dir / "proposal.md").write_text(VALID_PROPOSAL.format(status="ready"), encoding="utf-8")
    (change_dir / "tasks.md").write_text(VALID_TASKS, encoding="utf-8")
    return spec_root, change_dir


def test_review_pass_reaches_merge_ready(tmp_path):
    spec_root, change_dir = _make_ready_change(tmp_path)
    exit_code = _run(["transition", "--spec-root", str(spec_root), "CP-1", "REVIEW_PASS"])
    assert exit_code == 0
    assert "status: merge_ready" in (change_dir / "proposal.md").read_text(encoding="utf-8")


def test_review_reject_sends_back_to_respec(tmp_path):
    spec_root, change_dir = _make_ready_change(tmp_path)
    exit_code = _run(["transition", "--spec-root", str(spec_root), "CP-1", "REVIEW_REJECT"])
    assert exit_code == 0
    assert "status: respec" in (change_dir / "proposal.md").read_text(encoding="utf-8")


def test_ready_can_no_longer_transition_directly_to_merged(tmp_path):
    spec_root, change_dir = _make_ready_change(tmp_path)
    exit_code = _run(["transition", "--spec-root", str(spec_root), "CP-1", "MERGED"])
    assert exit_code == 1
    assert "status: ready" in (change_dir / "proposal.md").read_text(encoding="utf-8")


# ---------------------------------------------------------------------------
# warn_if_no_specs_touch：MERGED 沒動 specs/ 時要有提醒，但不擋流程
# ---------------------------------------------------------------------------

def test_merged_warns_when_impact_surface_has_no_specs_path(tmp_path, capsys):
    spec_root = tmp_path / ".spec"
    change_dir = spec_root / "changes" / "CP-1"
    change_dir.mkdir(parents=True)
    proposal_no_specs = VALID_PROPOSAL.format(status="merge_ready").replace(
        "impact_surface:\n  - x", "impact_surface:\n  - some/unrelated/file.txt"
    )
    (change_dir / "proposal.md").write_text(proposal_no_specs, encoding="utf-8")
    (change_dir / "tasks.md").write_text(VALID_TASKS, encoding="utf-8")

    exit_code = _run(["transition", "--spec-root", str(spec_root), "CP-1", "MERGED"])
    assert exit_code == 0  # 純提醒，不擋流程
    assert "status: applied" in (change_dir / "proposal.md").read_text(encoding="utf-8")

    captured = capsys.readouterr()
    assert "沒有任何一項落在 specs/ 底下" in captured.err


def test_merged_no_warning_when_impact_surface_has_specs_path(tmp_path, capsys):
    spec_root = tmp_path / ".spec"
    change_dir = spec_root / "changes" / "CP-1"
    change_dir.mkdir(parents=True)
    proposal_with_specs = VALID_PROPOSAL.format(status="merge_ready").replace(
        "impact_surface:\n  - x", "impact_surface:\n  - .spec/specs/db/schema.dbml"
    )
    (change_dir / "proposal.md").write_text(proposal_with_specs, encoding="utf-8")
    (change_dir / "tasks.md").write_text(VALID_TASKS, encoding="utf-8")

    exit_code = _run(["transition", "--spec-root", str(spec_root), "CP-1", "MERGED"])
    assert exit_code == 0

    captured = capsys.readouterr()
    assert "沒有任何一項落在 specs/ 底下" not in captured.err


# ---------------------------------------------------------------------------
# REVIEW_PASS 真正檢查 review.md 有沒有還沒結案的項目（issue #11）
# ---------------------------------------------------------------------------

REVIEW_WITH_PENDING = """\
---
change: CP-1
---

## 🔴 待處理（1）

- **F1** — status 比對用字串常數，沒有集中定義

## Review 發現 (Findings)

### ⏳ F1 — status 比對用字串常數，沒有集中定義

- **位置**：src/api/roster_api.py
- **問題**：字串各自手打，容易打錯字
- **選項**：
  - [ ] 拉一個常數類別集中管理
  - [ ] 這次不動，開新 change 處理
  - [ ] 其他補充：
"""

REVIEW_ALL_RESOLVED = """\
---
change: CP-1
---

## 🔴 待處理（0）

## Review 發現 (Findings)

### ✅ F1 — status 比對用字串常數，沒有集中定義

- **位置**：src/api/roster_api.py
- **問題**：字串各自手打，容易打錯字
- **處置**：這次不動，開 CP-2 另外處理
"""


def _make_ready_change_with_review(tmp_path, review_text):
    spec_root = tmp_path / ".spec"
    change_dir = spec_root / "changes" / "CP-1"
    change_dir.mkdir(parents=True)
    (change_dir / "proposal.md").write_text(VALID_PROPOSAL.format(status="ready"), encoding="utf-8")
    (change_dir / "tasks.md").write_text(VALID_TASKS, encoding="utf-8")
    (change_dir / "review.md").write_text(review_text, encoding="utf-8")
    return spec_root, change_dir


def test_review_pass_blocked_when_review_has_pending_findings(tmp_path, capsys):
    """回歸測試（issue #11）：review.md 明明還有 ⏳ 待處理項目，REVIEW_PASS
    之前是直接放行的——這等於整套 review.md 機制形同虛設。現在必須被擋下。"""
    spec_root, change_dir = _make_ready_change_with_review(tmp_path, REVIEW_WITH_PENDING)

    exit_code = _run(["transition", "--spec-root", str(spec_root), "CP-1", "REVIEW_PASS"])
    assert exit_code == 1
    assert "status: ready" in (change_dir / "proposal.md").read_text(encoding="utf-8")  # 沒有被轉移

    captured = capsys.readouterr()
    assert "還有 1 個待處理項目未結案" in captured.err
    assert "F1" in captured.err


def test_review_pass_succeeds_when_all_findings_resolved(tmp_path):
    spec_root, change_dir = _make_ready_change_with_review(tmp_path, REVIEW_ALL_RESOLVED)

    exit_code = _run(["transition", "--spec-root", str(spec_root), "CP-1", "REVIEW_PASS"])
    assert exit_code == 0
    assert "status: merge_ready" in (change_dir / "proposal.md").read_text(encoding="utf-8")


def test_review_pass_succeeds_when_review_md_absent(tmp_path):
    """review.md 是可選檔案，不存在時 REVIEW_PASS 不受影響（不強制一定要寫）。"""
    spec_root = tmp_path / ".spec"
    change_dir = spec_root / "changes" / "CP-1"
    change_dir.mkdir(parents=True)
    (change_dir / "proposal.md").write_text(VALID_PROPOSAL.format(status="ready"), encoding="utf-8")
    (change_dir / "tasks.md").write_text(VALID_TASKS, encoding="utf-8")

    exit_code = _run(["transition", "--spec-root", str(spec_root), "CP-1", "REVIEW_PASS"])
    assert exit_code == 0
    assert "status: merge_ready" in (change_dir / "proposal.md").read_text(encoding="utf-8")
