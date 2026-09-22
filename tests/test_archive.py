"""封存功能的測試：specflow archive、resolve_change_dir 的 archive fallback、
transition 走到終點狀態時的提示。

對應真實使用者回報的缺口：README 畫了 changes/archive/<id>/ 這個慣例，但一直
沒有任何程式碼真的實作它——這裡把回報裡點名的三件事都補上對應測試。
"""

import subprocess
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT))

from bin import specflow as cli  # noqa: E402


def _git(repo_dir, *args):
    subprocess.run(["git", *args], cwd=repo_dir, check=True, capture_output=True)


def _run(argv):
    parser = cli.build_parser()
    args = parser.parse_args(argv)
    return args.func(args)


VALID_TASKS = """\
---
change: CP-1
---

- [ ] task-a: 描述 (touches: x)
"""


def _make_change(spec_root, status="applied", change_type="feature"):
    change_dir = spec_root / "changes" / "CP-1"
    change_dir.mkdir(parents=True)
    (change_dir / "proposal.md").write_text(
        f"---\nid: CP-1\ntitle: \"測試\"\nimpact_surface:\n  - x\ntype: {change_type}\nstatus: {status}\n---\n\n"
        "## 1. 為什麼 (Why)\n\nx\n\n## 2. 目標 (Goals)\n\n- x\n\n## 3. 非目標 (Non-Goals)\n\n- x\n",
        encoding="utf-8",
    )
    (change_dir / "tasks.md").write_text(VALID_TASKS, encoding="utf-8")
    return change_dir


# ---------------------------------------------------------------------------
# specflow archive
# ---------------------------------------------------------------------------

def test_archive_moves_change_to_archive_dir(tmp_path):
    spec_root = tmp_path / ".spec"
    change_dir = _make_change(spec_root, status="applied")

    exit_code = _run(["archive", "--spec-root", str(spec_root), "CP-1"])

    assert exit_code == 0
    assert not change_dir.exists()
    archived = spec_root / "changes" / "archive" / "CP-1"
    assert archived.is_dir()
    assert (archived / "proposal.md").exists()
    assert (archived / "tasks.md").exists()


def test_archive_supports_baseline_recorded_as_final_state(tmp_path):
    spec_root = tmp_path / ".spec"
    _make_change(spec_root, status="baseline_recorded", change_type="baseline")

    exit_code = _run(["archive", "--spec-root", str(spec_root), "CP-1"])

    assert exit_code == 0
    assert (spec_root / "changes" / "archive" / "CP-1").is_dir()


def test_archive_blocks_non_final_status(tmp_path, capsys):
    spec_root = tmp_path / ".spec"
    change_dir = _make_change(spec_root, status="ready")

    exit_code = _run(["archive", "--spec-root", str(spec_root), "CP-1"])

    assert exit_code == 1
    assert change_dir.exists()  # 沒被搬走
    assert not (spec_root / "changes" / "archive").exists()

    captured = capsys.readouterr()
    assert "不是終點狀態" in captured.err


def test_archive_refuses_to_overwrite_existing_target(tmp_path):
    spec_root = tmp_path / ".spec"
    _make_change(spec_root, status="applied")
    existing = spec_root / "changes" / "archive" / "CP-1"
    existing.mkdir(parents=True)
    (existing / "marker.txt").write_text("既有內容", encoding="utf-8")

    exit_code = _run(["archive", "--spec-root", str(spec_root), "CP-1"])

    assert exit_code == 1
    assert (existing / "marker.txt").exists()  # 沒被蓋掉
    assert (spec_root / "changes" / "CP-1").exists()  # 原本的也還在，沒被搬走


def test_archive_missing_change_fails_clearly(tmp_path, capsys):
    spec_root = tmp_path / ".spec"
    spec_root.mkdir()

    exit_code = _run(["archive", "--spec-root", str(spec_root), "CP-DOES-NOT-EXIST"])

    assert exit_code == 1
    assert "找不到 change" in capsys.readouterr().err


def test_archive_auto_commit_uses_git_mv(tmp_path):
    repo_dir = tmp_path / "repo"
    repo_dir.mkdir()
    _git(repo_dir, "init", "-q")
    _git(repo_dir, "config", "user.email", "test@example.com")
    _git(repo_dir, "config", "user.name", "test")

    spec_root = repo_dir / ".spec"
    _make_change(spec_root, status="applied")
    _git(repo_dir, "add", ".")
    _git(repo_dir, "commit", "-q", "-m", "add change")

    exit_code = _run(["archive", "--spec-root", str(spec_root), "CP-1", "--auto-commit"])

    assert exit_code == 0
    assert (spec_root / "changes" / "archive" / "CP-1").is_dir()

    status = subprocess.run(
        ["git", "status", "--porcelain"], cwd=repo_dir, capture_output=True, text=True
    ).stdout
    assert status.strip() == ""  # 沒有留下 dirty 工作區

    log = subprocess.run(
        ["git", "log", "-1", "--pretty=%s"], cwd=repo_dir, capture_output=True, text=True
    ).stdout
    assert "archive" in log
    assert "CP-1" in log


# ---------------------------------------------------------------------------
# resolve_change_dir 的 archive fallback
# ---------------------------------------------------------------------------

def test_resolve_change_dir_finds_archived_change(tmp_path):
    spec_root = tmp_path / ".spec"
    archived_dir = spec_root / "changes" / "archive" / "CP-1"
    archived_dir.mkdir(parents=True)

    result = cli.resolve_change_dir(spec_root, "CP-1")
    assert result == archived_dir


def test_resolve_change_dir_prefers_active_over_archived(tmp_path):
    """同一個 id 理論上不該同時存在於 changes/ 跟 changes/archive/，但如果真的
    發生了，優先信任還在跑的那份，不是封存的舊版本。"""
    spec_root = tmp_path / ".spec"
    active_dir = spec_root / "changes" / "CP-1"
    active_dir.mkdir(parents=True)
    (spec_root / "changes" / "archive" / "CP-1").mkdir(parents=True)

    result = cli.resolve_change_dir(spec_root, "CP-1")
    assert result == active_dir


def test_next_works_on_archived_change(tmp_path):
    """回歸測試：封存之後 `specflow next <id>` 不該直接查不到——封存要對 lint
    隱形，但對查詢仍然可見。"""
    spec_root = tmp_path / ".spec"
    change_dir = _make_change(spec_root, status="applied")
    _run(["archive", "--spec-root", str(spec_root), "CP-1"])
    assert not change_dir.exists()

    exit_code = _run(["next", "--spec-root", str(spec_root), "CP-1"])
    assert exit_code == 0  # 終點狀態，next_action 是 None，沒有 blocking_errors


# ---------------------------------------------------------------------------
# transition 走到終點狀態時的提示
# ---------------------------------------------------------------------------

def test_transition_hints_archive_when_reaching_final_state(tmp_path, capsys):
    spec_root = tmp_path / ".spec"
    change_dir = spec_root / "changes" / "CP-1"
    change_dir.mkdir(parents=True)
    (change_dir / "proposal.md").write_text(
        "---\nid: CP-1\ntitle: \"測試\"\nimpact_surface:\n  - x\ntype: feature\nstatus: merge_ready\n---\n\n"
        "## 1. 為什麼 (Why)\n\nx\n\n## 2. 目標 (Goals)\n\n- x\n\n## 3. 非目標 (Non-Goals)\n\n- x\n",
        encoding="utf-8",
    )
    (change_dir / "tasks.md").write_text(VALID_TASKS, encoding="utf-8")

    exit_code = _run(["transition", "--spec-root", str(spec_root), "CP-1", "MERGED"])

    assert exit_code == 0
    captured = capsys.readouterr()
    assert "已到終點狀態" in captured.err
    assert "specflow archive CP-1" in captured.err


def test_transition_does_not_hint_archive_for_non_final_target(tmp_path, capsys):
    spec_root = tmp_path / ".spec"
    change_dir = spec_root / "changes" / "CP-1"
    change_dir.mkdir(parents=True)
    (change_dir / "proposal.md").write_text(
        "---\nid: CP-1\ntitle: \"測試\"\nimpact_surface:\n  - x\ntype: feature\nstatus: ready\n---\n\n"
        "## 1. 為什麼 (Why)\n\nx\n\n## 2. 目標 (Goals)\n\n- x\n\n## 3. 非目標 (Non-Goals)\n\n- x\n",
        encoding="utf-8",
    )
    (change_dir / "tasks.md").write_text(VALID_TASKS, encoding="utf-8")

    exit_code = _run(["transition", "--spec-root", str(spec_root), "CP-1", "REVIEW_PASS"])

    assert exit_code == 0
    captured = capsys.readouterr()
    assert "已到終點狀態" not in captured.err  # merge_ready 不是終點，不該出現提示
