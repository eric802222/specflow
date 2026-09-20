#!/usr/bin/env python3
"""specflow CLI 入口。

specflow 本身（這支 CLI、它的範本、它的 linter 規則）跟它管理的「目標專案」是兩回事：
targets 的 .spec/ 資料夾可以在任何 repo 裡，不需要跟 specflow 自己綁在一起，也不需要
在同一個目錄下執行。目標位置的解析順序：

    1. --spec-root <path>              明確指定
    2. 環境變數 SPECFLOW_SPEC_ROOT
    3. 從目前目錄往上找 .spec/（跟 git 找 .git 同樣的邏輯）

範本（templates/）、狀態機定義（change-lifecycle.yaml）則永遠跟著 specflow 自己的安裝
位置走，不受 --spec-root 影響——那是「工具的規則」，不是「某個專案的資料」。

支援：
    specflow init <change-id> <title>          在 <spec-root>/changes/<change-id>/ 建立 proposal.md
    specflow lint [paths]                       對 proposal 執行 lint（預設: <spec-root>/changes/*/proposal.md）
    specflow next <change-id-or-path>           算出這個 change 下一步該做什麼（JSON 輸出）
    specflow transition <change-id-or-path> <event>   套用一次合法的狀態轉移
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent  # specflow 工具自己的安裝位置
sys.path.insert(0, str(REPO_ROOT))

from lib.linters import proposal_lint  # noqa: E402
from lib.workflow import lifecycle as lifecycle_mod  # noqa: E402
from lib.workflow import next_action  # noqa: E402

TEMPLATE_PATH = REPO_ROOT / "templates" / "proposal.template.md"
ENV_VAR = "SPECFLOW_SPEC_ROOT"


def resolve_spec_root(explicit: str = None) -> Path:
    """算出目標專案的 .spec/ 路徑，找不到就直接中止並說明怎麼指定。"""
    if explicit:
        p = Path(explicit).expanduser().resolve()
        if not p.exists():
            print(f"--spec-root 指定的路徑不存在：{p}", file=sys.stderr)
            raise SystemExit(2)
        return p

    env = os.environ.get(ENV_VAR)
    if env:
        return Path(env).expanduser().resolve()

    cur = Path.cwd().resolve()
    for candidate in [cur, *cur.parents]:
        maybe = candidate / ".spec"
        if maybe.is_dir():
            return maybe

    print(
        "找不到 .spec/ 目錄。請用 --spec-root 指定，或設定環境變數 "
        f"{ENV_VAR}，或在專案某層目錄底下建立 .spec/。",
        file=sys.stderr,
    )
    raise SystemExit(2)


def resolve_change_dir(spec_root: Path, ref: str) -> Path:
    """ref 可以是純 change-id（相對 <spec-root>/changes/ 解析），也可以是一個實際路徑。"""
    as_path = Path(ref)
    if as_path.exists() and as_path.is_dir():
        return as_path
    return spec_root / "changes" / ref


def cmd_init(args: argparse.Namespace) -> int:
    spec_root = resolve_spec_root(args.spec_root)
    change_id = args.change_id
    title = args.title

    if not TEMPLATE_PATH.exists():
        print(f"找不到範本：{TEMPLATE_PATH}", file=sys.stderr)
        return 1

    change_dir = spec_root / "changes" / change_id
    if change_dir.exists():
        print(f"change 已存在，不覆寫：{change_dir}", file=sys.stderr)
        return 1

    text = TEMPLATE_PATH.read_text(encoding="utf-8")
    text = text.replace("id: PROP-XXXX", f"id: {change_id}", 1)
    text = text.replace('title: "<一句話描述本次變更>"', f'title: "{title}"', 1)

    change_dir.mkdir(parents=True)
    (change_dir / "proposal.md").write_text(text, encoding="utf-8")
    print(f"已建立 change：{change_dir}")
    return 0


def cmd_lint(args: argparse.Namespace) -> int:
    paths = args.paths
    if not paths:
        spec_root = resolve_spec_root(args.spec_root)
        changes_dir = spec_root / "changes"
        paths = [str(p) for p in sorted(changes_dir.glob("*/proposal.md"))]
        if not paths:
            print(f"{changes_dir} 底下沒有任何 proposal.md")
            return 0

    return proposal_lint.main(paths)


def cmd_next(args: argparse.Namespace) -> int:
    spec_root = resolve_spec_root(args.spec_root)
    change_dir = resolve_change_dir(spec_root, args.change)
    result = next_action.compute_next(change_dir)
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0 if not result.get("blocking_errors") else 1


def cmd_transition(args: argparse.Namespace) -> int:
    spec_root = resolve_spec_root(args.spec_root)
    change_dir = resolve_change_dir(spec_root, args.change)
    change_id = change_dir.name
    proposal_path = change_dir / "proposal.md"

    if not proposal_path.exists():
        print(f"找不到 {proposal_path}", file=sys.stderr)
        return 1

    lc = lifecycle_mod.load_lifecycle()
    fm = proposal_lint.read_frontmatter(proposal_path)
    current_status = (fm.get("status") if isinstance(fm, dict) else None) or lc.initial

    target = lc.target_for(current_status, args.event)
    if target is None:
        legal = [t.event for t in lc.transitions(current_status)]
        print(
            f"非法轉移：狀態 '{current_status}' 不接受事件 '{args.event}'（合法事件：{legal}）",
            file=sys.stderr,
        )
        return 1

    # auto 轉移在套用前重新驗證一次 lint，避免繞過 `next` 直接呼叫 transition
    auto_events = {t.event for t in lc.auto_transitions(current_status)}
    if args.event in auto_events:
        p_result = proposal_lint.lint_file(proposal_path)
        if not p_result.ok:
            print("proposal_lint 未通過，無法轉移：", file=sys.stderr)
            for err in p_result.errors:
                print(f"  - {err}", file=sys.stderr)
            return 1

    proposal_lint.write_frontmatter_field(proposal_path, "status", target)
    print(f"{change_id}: {current_status} --{args.event}--> {target}")
    return 0


def cmd_root(args: argparse.Namespace) -> int:
    """除錯用：印出目前會解析到的 spec-root，不做任何檢查以外的事。"""
    spec_root = resolve_spec_root(args.spec_root)
    print(spec_root)
    return 0


def _add_spec_root_arg(parser: argparse.ArgumentParser) -> None:
    parser.add_argument(
        "--spec-root",
        dest="spec_root",
        default=None,
        help=f"目標專案的 .spec/ 路徑（預設：{ENV_VAR} 環境變數，或從目前目錄往上找 .spec/）",
    )


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="specflow")
    subparsers = parser.add_subparsers(dest="command", required=True)

    init_parser = subparsers.add_parser("init", help="建立填空用 Proposal")
    _add_spec_root_arg(init_parser)
    init_parser.add_argument("change_id", help="change 的唯一識別碼，同時是資料夾名稱，例如 CP-153-discount-reason")
    init_parser.add_argument("title", help="Proposal 標題")
    init_parser.set_defaults(func=cmd_init)

    lint_parser = subparsers.add_parser("lint", help="對 Proposal 檔案執行 lint")
    _add_spec_root_arg(lint_parser)
    lint_parser.add_argument("paths", nargs="*", help="要檢查的檔案路徑（預設: <spec-root>/changes/*/proposal.md）")
    lint_parser.set_defaults(func=cmd_lint)

    next_parser = subparsers.add_parser("next", help="算出這個 change 下一步該做什麼（JSON 輸出）")
    _add_spec_root_arg(next_parser)
    next_parser.add_argument("change", help="change-id（相對 <spec-root>/changes/ 解析）或實際路徑")
    next_parser.set_defaults(func=cmd_next)

    transition_parser = subparsers.add_parser("transition", help="套用一次合法的狀態轉移")
    _add_spec_root_arg(transition_parser)
    transition_parser.add_argument("change", help="change-id 或實際路徑")
    transition_parser.add_argument("event", help="要觸發的事件，例如 LINT_PASS、DEV_DONE")
    transition_parser.set_defaults(func=cmd_transition)

    root_parser = subparsers.add_parser("root", help="印出目前解析到的 --spec-root（除錯用）")
    _add_spec_root_arg(root_parser)
    root_parser.set_defaults(func=cmd_root)

    return parser


def main(argv=None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())
