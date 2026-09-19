#!/usr/bin/env python3
"""specflow CLI 入口。

支援：
    specflow init <name>   在當前目錄的 proposals/ 底下生成填空用 Proposal
    specflow lint [paths]  對 Proposal 檔案執行 proposal_lint（預設: proposals/*.md）
"""

from __future__ import annotations

import argparse
import sys
from datetime import date
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT))

from lib.linters import proposal_lint  # noqa: E402

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


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="specflow")
    subparsers = parser.add_subparsers(dest="command", required=True)

    init_parser = subparsers.add_parser("init", help="在當前目錄生成填空用 Proposal")
    init_parser.add_argument("name", help="Proposal 名稱（會用來產生 id 與檔名）")
    init_parser.set_defaults(func=cmd_init)

    lint_parser = subparsers.add_parser("lint", help="對 Proposal 檔案執行 lint")
    lint_parser.add_argument("paths", nargs="*", help="要檢查的檔案路徑（預設: proposals/*.md）")
    lint_parser.set_defaults(func=cmd_lint)

    return parser


def main(argv=None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())
