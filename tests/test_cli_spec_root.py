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


def test_explicit_nonexistent_path_gets_created(tmp_path):
    """回歸測試（issue #12）：--spec-root 明確指定的路徑不存在時，之前是直接
    SystemExit 報錯——這逼使用者第一次匯入專案時要先手動 mkdir 才能跑第一個
    指令，跟 `git init <dir>` 目錄不存在就自己建的慣例不一致。現在應該直接
    建立，不用使用者自己先準備好。"""
    target = tmp_path / "does-not-exist" / "nested"
    result = cli.resolve_spec_root(str(target))
    assert result == target.resolve()
    assert target.is_dir()


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
    monkeypatch.setitem(cli.TEMPLATE_PATHS, "feature", broken_template)

    spec_root = tmp_path / ".spec"
    spec_root.mkdir()

    parser = cli.build_parser()
    args = parser.parse_args(["init", "--spec-root", str(spec_root), "CP-1", "測試標題"])
    exit_code = args.func(args)

    assert exit_code == 1
    assert not (spec_root / "changes" / "CP-1").exists()


def test_init_rejects_change_id_with_path_separator(tmp_path):
    spec_root = tmp_path / ".spec"
    spec_root.mkdir()

    parser = cli.build_parser()
    args = parser.parse_args(["init", "--spec-root", str(spec_root), "../evil", "標題"])
    exit_code = args.func(args)

    assert exit_code == 1
    assert not (spec_root / "changes").exists()  # 連 changes/ 都不該被建出來


def test_init_rejects_change_id_starting_with_dot(tmp_path):
    spec_root = tmp_path / ".spec"
    spec_root.mkdir()

    parser = cli.build_parser()
    args = parser.parse_args(["init", "--spec-root", str(spec_root), ".hidden", "標題"])
    exit_code = args.func(args)

    assert exit_code == 1


def test_init_accepts_realistic_jira_style_change_id(tmp_path):
    spec_root = tmp_path / ".spec"
    spec_root.mkdir()

    parser = cli.build_parser()
    args = parser.parse_args(
        ["init", "--spec-root", str(spec_root), "CP-153-discount-reason-visibility", "標題"]
    )
    exit_code = args.func(args)

    assert exit_code == 0
    assert (spec_root / "changes" / "CP-153-discount-reason-visibility" / "proposal.md").exists()


def test_init_with_baseline_type_uses_lean_template(tmp_path):
    spec_root = tmp_path / ".spec"
    spec_root.mkdir()

    parser = cli.build_parser()
    args = parser.parse_args(
        ["init", "--spec-root", str(spec_root), "CP-3", "既有核準流程現況", "--type", "baseline"]
    )
    exit_code = args.func(args)

    text = (spec_root / "changes" / "CP-3" / "proposal.md").read_text(encoding="utf-8")
    assert exit_code == 0
    assert "type: baseline" in text
    assert "## 現況 (What it actually does today)" in text
    assert "## 1. 為什麼 (Why)" not in text  # 不該混到 feature 範本的區塊


def test_init_defaults_to_feature_type(tmp_path):
    spec_root = tmp_path / ".spec"
    spec_root.mkdir()

    parser = cli.build_parser()
    args = parser.parse_args(["init", "--spec-root", str(spec_root), "CP-1", "標題"])
    args.func(args)

    text = (spec_root / "changes" / "CP-1" / "proposal.md").read_text(encoding="utf-8")
    assert "type: feature" in text


def test_init_with_hotfix_type_uses_lean_template(tmp_path):
    spec_root = tmp_path / ".spec"
    spec_root.mkdir()

    parser = cli.build_parser()
    args = parser.parse_args(
        ["init", "--spec-root", str(spec_root), "CP-1", "資料庫連線爆掉緊急處置", "--type", "hotfix"]
    )
    exit_code = args.func(args)

    text = (spec_root / "changes" / "CP-1" / "proposal.md").read_text(encoding="utf-8")
    assert exit_code == 0
    assert "type: hotfix" in text
    assert "## 症狀 (Symptom)" in text
    assert "## 1. 為什麼 (Why)" not in text  # 不該混到 feature 範本的區塊


def test_init_with_bugfix_type_uses_lean_template(tmp_path):
    spec_root = tmp_path / ".spec"
    spec_root.mkdir()

    parser = cli.build_parser()
    args = parser.parse_args(
        ["init", "--spec-root", str(spec_root), "CP-2", "驗證邊界漏判", "--type", "bugfix"]
    )
    exit_code = args.func(args)

    text = (spec_root / "changes" / "CP-2" / "proposal.md").read_text(encoding="utf-8")
    assert exit_code == 0
    assert "type: bugfix" in text
    assert "## 壞在哪 (Symptom)" in text


# ---------------------------------------------------------------------------
# --with-design 事後幫既有 change 補 design.md（issue #15）
# ---------------------------------------------------------------------------

def test_with_design_adds_design_md_to_existing_change(tmp_path):
    spec_root = tmp_path / ".spec"
    spec_root.mkdir()
    parser = cli.build_parser()

    args1 = parser.parse_args(["init", "--spec-root", str(spec_root), "CP-1", "標題", "--type", "bugfix"])
    assert args1.func(args1) == 0
    assert not (spec_root / "changes" / "CP-1" / "design.md").exists()

    # 事後才發現這個決策該記下來，補一份 design.md 進去
    args2 = parser.parse_args(
        ["init", "--spec-root", str(spec_root), "CP-1", "隨便填", "--with-design"]
    )
    exit_code = args2.func(args2)

    design_path = spec_root / "changes" / "CP-1" / "design.md"
    assert exit_code == 0
    assert design_path.exists()
    assert "change: CP-1" in design_path.read_text(encoding="utf-8")
    # 原本的 proposal.md 不該被動到
    assert "type: bugfix" in (spec_root / "changes" / "CP-1" / "proposal.md").read_text(encoding="utf-8")


def test_with_design_refuses_to_overwrite_existing_design_md(tmp_path):
    spec_root = tmp_path / ".spec"
    spec_root.mkdir()
    parser = cli.build_parser()

    args1 = parser.parse_args(
        ["init", "--spec-root", str(spec_root), "CP-1", "標題", "--type", "bugfix", "--with-design"]
    )
    assert args1.func(args1) == 0
    design_path = spec_root / "changes" / "CP-1" / "design.md"
    design_path.write_text("change: CP-1\n---\n有內容了", encoding="utf-8")

    args2 = parser.parse_args(["init", "--spec-root", str(spec_root), "CP-1", "隨便", "--with-design"])
    exit_code = args2.func(args2)

    assert exit_code == 1
    assert design_path.read_text(encoding="utf-8") == "change: CP-1\n---\n有內容了"  # 沒被蓋掉


def test_init_without_with_design_still_refuses_existing_change(tmp_path):
    """回歸測試：確認這次的改動沒有意外放寬「change 已存在不覆寫」這條保護——
    只有明確傳 --with-design 才走補件路徑，其他情況維持原本行為。"""
    spec_root = tmp_path / ".spec"
    spec_root.mkdir()
    parser = cli.build_parser()

    args1 = parser.parse_args(["init", "--spec-root", str(spec_root), "CP-1", "標題"])
    assert args1.func(args1) == 0

    args2 = parser.parse_args(["init", "--spec-root", str(spec_root), "CP-1", "又建一次"])
    exit_code = args2.func(args2)

    assert exit_code == 1
    assert not (spec_root / "changes" / "CP-1" / "design.md").exists()
