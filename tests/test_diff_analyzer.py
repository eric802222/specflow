"""diff_analyzer 的單元測試：用臨時 git repo 驗證 Blast Radius 統計。"""

import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT))

from lib.analyzers import diff_analyzer  # noqa: E402


def _git(repo_dir, *args):
    subprocess.run(["git", *args], cwd=repo_dir, check=True, capture_output=True)


def _init_repo(tmp_path):
    repo_dir = tmp_path / "repo"
    repo_dir.mkdir()
    _git(repo_dir, "init", "-q")
    _git(repo_dir, "config", "user.email", "test@example.com")
    _git(repo_dir, "config", "user.name", "test")

    specs_dir = repo_dir / "specs"
    (specs_dir / "db").mkdir(parents=True)
    (specs_dir / "api").mkdir()
    (specs_dir / "glossary.yaml").write_text("version: 1\nterms: []\n", encoding="utf-8")
    (specs_dir / "db" / "schema.dbml").write_text("Table x {}\n", encoding="utf-8")
    (specs_dir / "api" / "main.tsp").write_text("model X {}\n", encoding="utf-8")

    _git(repo_dir, "add", ".")
    _git(repo_dir, "commit", "-q", "-m", "init")
    _git(repo_dir, "branch", "-q", "-m", "main")

    return repo_dir, specs_dir


def test_no_changes_reports_zero(tmp_path):
    repo_dir, specs_dir = _init_repo(tmp_path)
    result = diff_analyzer.analyze(specs_dir, base_ref="main")
    assert result["changed_files"] == []
    assert all(len(files) == 0 for files in result["buckets"].values())


def test_detects_changes_by_category(tmp_path):
    repo_dir, specs_dir = _init_repo(tmp_path)

    _git(repo_dir, "checkout", "-q", "-b", "change/CP-1")
    (specs_dir / "db" / "schema.dbml").write_text("Table x { id int }\n", encoding="utf-8")
    (specs_dir / "ui").mkdir()
    (specs_dir / "ui" / "page.wf.yaml").write_text("body: []\n", encoding="utf-8")
    _git(repo_dir, "add", ".")
    _git(repo_dir, "commit", "-q", "-m", "change db and ui")

    result = diff_analyzer.analyze(specs_dir, base_ref="main")
    assert len(result["buckets"]["db"]) == 1
    assert len(result["buckets"]["ui"]) == 1
    assert len(result["buckets"]["api"]) == 0
    assert "db: 1 個檔案" in result["summary"]
