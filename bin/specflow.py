#!/usr/bin/env python3
"""specflow CLI 入口。

支援：
    specflow init <name>   在當前目錄的 proposals/ 底下生成填空用 Proposal
    specflow lint [paths]  對 Proposal 檔案執行 proposal_lint（預設: proposals/*.md）
    specflow next <change_dir>          算出這個 change 下一步該做什麼（JSON 輸出）
    specflow transition <change_dir> <event>  套用一次合法的狀態轉移
"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import date
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT))

from lib.linters import proposal_lint  # noqa: E402
from lib.workflow import lifecycle as lifecycle_mod  # noqa: E402
from lib.workflow import next_action  # noqa: E402

TEMPLATE_PATH = REPO_ROOT / "templates" / "proposal.template.md"


def cmd_init(args: argparse.Namespace) -> int:
    name = args.name
    slug = name.strip().lower().replace(" ", "-")
    today = date.today().isoformat()
    proposal_id = f"PROP-{today.replace('-', '')}-{slug}"

    if not TEMPLATE_PATH.exists():
        print(f"找不到範本：{TEMPLATE_PATH}", file=sys.stderr)
        return 1

    text = TEMPLATE_PATH.read_text(encoding="utf-8")
    text = text.replace("id: PROP-XXXX", f"id: {proposal_id}", 1)
    text = text.replace('title: "<一句話描述本次變更>"', f'title: "{name}"', 1)

    proposals_dir = Path.cwd() / "proposals"
    proposals_dir.mkdir(parents=True, exist_ok=True)
    out_path = proposals_dir / f"{today}-{slug}.md"

    if out_path.exists():
        print(f"檔案已存在，不覆寫：{out_path}", file=sys.stderr)
        return 1

    out_path.write_text(text, encoding="utf-8")
    print(f"已建立 proposal：{out_path}")
    return 0


def cmd_lint(args: argparse.Namespace) -> int:
    paths = args.paths
    if not paths:
        default_dir = Path.cwd() / "proposals"
        if not default_dir.exists():
            print(f"找不到 {default_dir}，且未指定路徑", file=sys.stderr)
            return 2
        paths = [str(p) for p in sorted(default_dir.glob("*.md"))]
        if not paths:
            print(f"{default_dir} 底下沒有任何 .md 檔案")
            return 0

    return proposal_lint.main(paths)


def cmd_next(args: argparse.Namespace) -> int:
    change_dir = Path(args.change_dir)
    result = next_action.compute_next(change_dir)
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0 if not result.get("blocking_errors") else 1


def cmd_transition(args: argparse.Namespace) -> int:
    change_dir = Path(args.change_dir)
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


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="specflow")
    subparsers = parser.add_subparsers(dest="command", required=True)

    init_parser = subparsers.add_parser("init", help="在當前目錄生成填空用 Proposal")
    init_parser.add_argument("name", help="Proposal 名稱（會用來產生 id 與檔名）")
    init_parser.set_defaults(func=cmd_init)

    lint_parser = subparsers.add_parser("lint", help="對 Proposal 檔案執行 lint")
    lint_parser.add_argument("paths", nargs="*", help="要檢查的檔案路徑（預設: proposals/*.md）")
    lint_parser.set_defaults(func=cmd_lint)

    next_parser = subparsers.add_parser("next", help="算出這個 change 下一步該做什麼（JSON 輸出）")
    next_parser.add_argument("change_dir", help="change 資料夾路徑，例如 .spec/changes/CP-153-xxx")
    next_parser.set_defaults(func=cmd_next)

    transition_parser = subparsers.add_parser("transition", help="套用一次合法的狀態轉移")
    transition_parser.add_argument("change_dir", help="change 資料夾路徑")
    transition_parser.add_argument("event", help="要觸發的事件，例如 LINT_PASS、DEV_DONE")
    transition_parser.set_defaults(func=cmd_transition)

    return parser


def main(argv=None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())
