"""bin.specflow 的路徑解析邏輯測試：--spec-root / 環境變數 / .spec 子目錄 / cwd 本身。"""

import os
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT))

from bin import specflow as cli  # noqa: E402


def test_explicit_spec_root_wins(tmp_path, monkeypatch):
    explicit_dir = tmp_path / "explicit"
    explicit_dir.mkdir()
    monkeypatch.setenv(cli.ENV_VAR, str(tmp_path / "from-env"))

    result = cli.resolve_spec_root(str(explicit_dir))
    assert result == explicit_dir.resolve()


def test_explicit_nonexistent_path_errors(tmp_path):
    try:
        cli.resolve_spec_root(str(tmp_path / "does-not-exist"))
        assert False, "應該要 raise SystemExit"
    except SystemExit as e:
        assert e.code == 2


def test_env_var_used_when_no_explicit(tmp_path, monkeypatch):
    env_dir = tmp_path / "from-env"
    env_dir.mkdir()
    monkeypatch.setenv(cli.ENV_VAR, str(env_dir))
    monkeypatch.chdir(tmp_path)

    result = cli.resolve_spec_root(None)
    assert result == env_dir.resolve()


def test_nested_dot_spec_preferred_over_cwd(tmp_path, monkeypatch):
    monkeypatch.delenv(cli.ENV_VAR, raising=False)
    (tmp_path / ".spec").mkdir()
    monkeypatch.chdir(tmp_path)

    result = cli.resolve_spec_root(None)
    assert result == (tmp_path / ".spec").resolve()


def test_defaults_to_cwd_when_nothing_else_matches(tmp_path, monkeypatch):
    monkeypatch.delenv(cli.ENV_VAR, raising=False)
    monkeypatch.chdir(tmp_path)  # 沒有 .spec/ 子目錄，也沒有 env var

    result = cli.resolve_spec_root(None)
    assert result == tmp_path.resolve()


def test_resolve_change_dir_bare_id(tmp_path):
    spec_root = tmp_path / ".spec"
    (spec_root / "changes" / "CP-1").mkdir(parents=True)

    result = cli.resolve_change_dir(spec_root, "CP-1")
    assert result == spec_root / "changes" / "CP-1"


def test_resolve_change_dir_actual_path(tmp_path):
    actual_dir = tmp_path / "somewhere" / "CP-1"
    actual_dir.mkdir(parents=True)

    result = cli.resolve_change_dir(tmp_path / ".spec", str(actual_dir))
    assert result == actual_dir
