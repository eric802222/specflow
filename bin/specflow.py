#!/usr/bin/env python3
"""specflow CLI 入口。

specflow 本身（這支 CLI、它的範本、它的 linter 規則）跟它管理的「目標專案」是兩回事：
targets 的 .spec/ 資料夾可以在任何 repo 裡，不需要跟 specflow 自己綁在一起。目標位置的
解析順序：

    1. --spec-root <path>              明確指定
    2. 環境變數 SPECFLOW_SPEC_ROOT
    3. 目前目錄底下的 .spec/（規格嘅在應用程式 repo 裡的 monorepo 模式）
    4. 目前目錄本身（規格自己獨立一個 repo，repo root 就是 spec root）

範本（templates/）永遠跟著 specflow 自己的安裝位置走。change 生命周期定義
（change-lifecycle.yaml）預設也是 specflow 自己內附的那份，但如果 spec root 底下
有一份同名檔案（<spec-root>/change-lifecycle.yaml），會優先採用那份——讓不同專案
可以客製化自己的流程，不用被綢死在同一套五段式狀態機上。

支援：
    specflow init <change-id> <title>          在 <spec-root>/changes/<change-id>/ 建立 proposal.md
    specflow lint [paths]                       對 proposal 執行 lint（預設: <spec-root>/changes/*/proposal.md）
    specflow next <change-id-or-path>           算出這個 change 下一步該做什麼（JSON 輸出）
    specflow transition <change-id-or-path> <event>   套用一次合法的狀態轉移
    specflow root                               印出目前解析到的 spec root（除錯用）
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
from lib.workflow import next_action  # noqa: E402

TEMPLATE_PATH = REPO_ROOT / "templates" / "proposal.template.md"
ENV_VAR = "SPECFLOW_SPEC_ROOT"

ID_MARKER = "id: PROP-XXXX"
TITLE_MARKER = 'title: "<一句話描述本次變更>"'


def resolve_spec_root(explicit: str = None) -> Path:
    """算出目標專案的 spec root。

    優先序：--spec-root > SPECFLOW_SPEC_ROOT 環境變數 > 目前目錄底下的 .spec/
    （monorepo 模式）> 目前目錄本身（独立 spec repo 模式）。最後一層一定成功，
    不會因為找不到而報錯——目錄選錯了會在後續指令操作時給出更具體的錯誤
    （例如「changes/ 底下沒有 proposal.md」），比在這裡就攞下來更有幫助。
    """
    if explicit:
        p = Path(explicit).expanduser().resolve()
        if not p.exists():
            print(f"--spec-root 指定的路徑不存在：{p}", file=sys.stderr)
            raise SystemExit(2)
        return p

    env = os.environ.get(ENV_VAR)
    if env:
        return Path(env).expanduser().resolve()

    cwd = Path.cwd().resolve()
    nested = cwd / ".spec"
    if nested.is_dir():
        return nested

    return cwd


def resolve_change_dir(spec_root: Path, ref: str) -> Path:
    """優先把 ref 當成 <spec-root>/changes/ 底下的 change-id 解析；只有在那裡不存在、
    且 ref 本身剛好是一個存在的目錄時，才退回當成字面路徑使用。

    這個順序很重要：如果反過來優先信任字面路徑，遇到 cwd 底下剛好有個跟
    change-id 同名、但完全無關的資料夾時，會意外撿到錯的東西，還不會有任何警告。
    """
    under_spec_root = spec_root / "changes" / ref
    if under_spec_root.is_dir():
        return under_spec_root

    as_path = Path(ref)
    if as_path.is_dir():
        return as_path

    return under_spec_root


def resolve_lifecycle_path(spec_root: Path) -> Path:
    """<spec-root>/change-lifecycle.yaml 存在就優先用它（專案自訂流程），
    否則回傳 None，讓 lifecycle 模組退回 specflow 內附的預設版本。"""
    custom = spec_root / "change-lifecycle.yaml"
    return custom if custom.is_file() else None


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
    if ID_MARKER not in text or TITLE_MARKER not in text:
        print(
            f"範本格式跟預期不符，找不到佔位標記（{ID_MARKER!r} / {TITLE_MARKER!r}），"
            f"請檢查 {TEMPLATE_PATH} 是否被改動過",
            file=sys.stderr,
        )
        return 1

    text = text.replace(ID_MARKER, f"id: {change_id}", 1)
    text = text.replace(TITLE_MARKER, f'title: "{title}"', 1)

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
    lifecycle_path = resolve_lifecycle_path(spec_root)
    result = next_action.compute_next(change_dir, lifecycle_path=lifecycle_path)
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0 if not result.get("blocking_errors") else 1


def cmd_transition(args: argparse.Namespace) -> int:
    spec_root = resolve_spec_root(args.spec_root)
    change_dir = resolve_change_dir(spec_root, args.change)
    lifecycle_path = resolve_lifecycle_path(spec_root)
    change_id = change_dir.name

    # 任何轉移（不管 auto 還是手動事件）都必須先整組過 gate_check，不能只挑
    # auto 事件才重驗——這是之前真的存在過的漏洞：手動事件（DEV_DONE/MERGED/
    # ISSUE_FOUND）完全沒被驗證，等於 `specflow next` 擋得住的東西，直接呼叫
    # `specflow transition` 卻能全部繞過去。
    gate = next_action.gate_check(change_dir, lifecycle_path=lifecycle_path)
    if not gate["ok"]:
        print(f"擋下轉移：change 目前未通過檢查（{gate['next_action']}）", file=sys.stderr)
        for err in gate["blocking_errors"]:
            print(f"  - {err}", file=sys.stderr)
        return 1

    lc = gate["lifecycle"]
    current_status = gate["status"]

    target = lc.target_for(current_status, args.event)
    if target is None:
        legal = [t.event for t in lc.transitions(current_status)]
        print(
            f"非法轉移：狀態 '{current_status}' 不接受事件 '{args.event}'（合法事件：{legal}）",
            file=sys.stderr,
        )
        return 1

    proposal_path = change_dir / "proposal.md"
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
        help=f"目標專案的 spec root（預設：{ENV_VAR} 環境變數，或目前目錄的 .spec/，或目前目錄本身）",
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
