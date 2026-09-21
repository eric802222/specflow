"""change_shape_lint 的單元測試。"""

import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT))

from lib.linters import change_shape_lint  # noqa: E402


def test_allowed_files_only_passes(tmp_path):
    change_dir = tmp_path / "CP-153"
    change_dir.mkdir()
    (change_dir / "proposal.md").write_text("x", encoding="utf-8")
    (change_dir / "tasks.md").write_text("x", encoding="utf-8")

    result = change_shape_lint.lint_dir(change_dir)
    assert result.ok, result.errors


def test_extra_file_fails(tmp_path):
    change_dir = tmp_path / "CP-153"
    change_dir.mkdir()
    (change_dir / "proposal.md").write_text("x", encoding="utf-8")
    (change_dir / "NOTES.md").write_text("AI 自己多寫的說明文件", encoding="utf-8")

    result = change_shape_lint.lint_dir(change_dir)
    assert not result.ok
    assert any("NOTES.md" in e for e in result.errors)


def test_subdirectory_fails(tmp_path):
    change_dir = tmp_path / "CP-153"
    change_dir.mkdir()
    (change_dir / "proposal.md").write_text("x", encoding="utf-8")
    (change_dir / "delta").mkdir()

    result = change_shape_lint.lint_dir(change_dir)
    assert not result.ok
    assert any("子目錄" in e for e in result.errors)


def test_missing_proposal_fails(tmp_path):
    change_dir = tmp_path / "CP-153"
    change_dir.mkdir()
    (change_dir / "tasks.md").write_text("x", encoding="utf-8")

    result = change_shape_lint.lint_dir(change_dir)
    assert not result.ok
    assert any("proposal.md" in e for e in result.errors)


def test_missing_dir_fails(tmp_path):
    result = change_shape_lint.lint_dir(tmp_path / "does-not-exist")
    assert not result.ok


def test_dotfile_other_than_gitkeep_fails(tmp_path):
    change_dir = tmp_path / "CP-153"
    change_dir.mkdir()
    (change_dir / "proposal.md").write_text("x", encoding="utf-8")
    (change_dir / ".NOTES.md").write_text("AI 用點開頭檔名繞過白名單", encoding="utf-8")

    result = change_shape_lint.lint_dir(change_dir)
    assert not result.ok
    assert any(".NOTES.md" in e for e in result.errors)


def test_hidden_subdirectory_fails(tmp_path):
    change_dir = tmp_path / "CP-153"
    change_dir.mkdir()
    (change_dir / "proposal.md").write_text("x", encoding="utf-8")
    (change_dir / ".hidden_delta_folder").mkdir()
    (change_dir / ".hidden_delta_folder" / "sneaky.py").write_text("x", encoding="utf-8")

    result = change_shape_lint.lint_dir(change_dir)
    assert not result.ok
    assert any(".hidden_delta_folder" in e for e in result.errors)


def test_gitkeep_is_allowed(tmp_path):
    change_dir = tmp_path / "CP-153"
    change_dir.mkdir()
    (change_dir / "proposal.md").write_text("x", encoding="utf-8")
    (change_dir / ".gitkeep").write_text("", encoding="utf-8")

    result = change_shape_lint.lint_dir(change_dir)
    assert result.ok, result.errors


def test_design_md_is_allowed(tmp_path):
    change_dir = tmp_path / "CP-153"
    change_dir.mkdir()
    (change_dir / "proposal.md").write_text("x", encoding="utf-8")
    (change_dir / "design.md").write_text("x", encoding="utf-8")

    result = change_shape_lint.lint_dir(change_dir)
    assert result.ok, result.errors


def test_review_md_is_allowed(tmp_path):
    change_dir = tmp_path / "CP-153"
    change_dir.mkdir()
    (change_dir / "proposal.md").write_text("x", encoding="utf-8")
    (change_dir / "review.md").write_text("x", encoding="utf-8")

    result = change_shape_lint.lint_dir(change_dir)
    assert result.ok, result.errors
