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


def test_resolve_change_dir_prefers_spec_root_over_coincidental_cwd_dir(tmp_path):
    """回歸測試：曾經因為優先信任「字面路徑存在」，導致 cwd 底下剛好有個跟
    change-id 同名、完全無關的資料夾時，會意外撿到錯的東西。現在應該優先找
    <spec-root>/changes/<id>，只有那裡真的沒有才退回字面路徑。"""
    spec_root = tmp_path / ".spec"
    real_change_dir = spec_root / "changes" / "CP-1"
    real_change_dir.mkdir(parents=True)

    unrelated_dir = tmp_path / "CP-1"
    unrelated_dir.mkdir()
    (unrelated_dir / "unrelated.txt").write_text("不相干", encoding="utf-8")

    result = cli.resolve_change_dir(spec_root, "CP-1")
    assert result == real_change_dir
    assert result != unrelated_dir


def test_resolve_lifecycle_path_none_when_no_override(tmp_path):
    spec_root = tmp_path / ".spec"
    spec_root.mkdir()
    assert cli.resolve_lifecycle_path(spec_root) is None


def test_resolve_lifecycle_path_uses_project_override(tmp_path):
    spec_root = tmp_path / ".spec"
    spec_root.mkdir()
    custom = spec_root / "change-lifecycle.yaml"
    custom.write_text("id: custom\ninitial: a\nstates:\n  a: {}\n", encoding="utf-8")

    result = cli.resolve_lifecycle_path(spec_root)
    assert result == custom


def test_init_refuses_when_template_markers_missing(tmp_path, monkeypatch):
    """回歸測試：之前 cmd_init 用 str.replace() 比對範本裡的佔位字串，範本文字
    一旦被改到不再逐字相符，replace() 不會報錯只會靜默不替換，結果寫出一份帶著
    假 id/title 的 proposal 卻回報成功。現在要能主動擋下這種情況。"""
    broken_template = tmp_path / "broken.template.md"
    broken_template.write_text("這份範本已經被改到沒有任何佔位標記了\n", encoding="utf-8")
    monkeypatch.setattr(cli, "TEMPLATE_PATH", broken_template)

    spec_root = tmp_path / ".spec"
    spec_root.mkdir()

    parser = cli.build_parser()
    args = parser.parse_args(["init", "--spec-root", str(spec_root), "CP-1", "測試標題"])
    exit_code = args.func(args)

    assert exit_code == 1
    assert not (spec_root / "changes" / "CP-1").exists()
