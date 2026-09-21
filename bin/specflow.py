#!/usr/bin/env python3
"""specflow CLI 入口。

specflow 本身（這支 CLI、它的範本、它的 linter 規則）跟它管理的「目標專案」是兩回事：
targets 的 .spec/ 資料夾可以在任何 repo 裡，不需要跟 specflow 自己綁在一起。目標位置的
解析順序：

    1. --spec-root <path>              明確指定
    2. 環境變數 SPECFLOW_SPEC_ROOT
    3. 目前目錄底下的 .spec/（規格嵌在應用程式 repo 裡的 monorepo 模式）
    4. 目前目錄本身（規格自己獨立一個 repo，repo root 就是 spec root）

範本（templates/）永遠跟著 specflow 自己的安裝位置走。change 生命週期定義
（change-lifecycle.yaml）預設也是 specflow 自己內附的那份，但如果 spec root 底下
有一份同名檔案（<spec-root>/change-lifecycle.yaml），會優先採用那份——讓不同專案
可以客製化自己的流程，不用被綁死在同一套五段式狀態機上。

支援：
    specflow init <change-id> <title> [--type ...] [--with-design]  建立 proposal.md（可選 design.md）
    specflow lint [paths]                       對 proposal 執行 lint（預設: <spec-root>/changes/*/proposal.md）
    specflow next <change-id-or-path>           算出這個 change 下一步該做什麼（JSON 輸出）
    specflow transition <change-id-or-path> <event>   套用一次合法的狀態轉移
    specflow prompt <change-id-or-path> [--base main]  印出交付給 AI 的完整指令（純輸出，不落地成檔案）
    specflow coverage                            純資訊：glossary 實體的檢查覆蓋率（不會擋流程）
    specflow render [--out dist]                 把 specs/ 渲染成渲染後的產物（目錄頁 + 各 DSL 內容）
    specflow root                               印出目前解析到的 spec root（除錯用）
"""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent  # specflow 工具自己的安裝位置
sys.path.insert(0, str(REPO_ROOT))

from lib.linters import proposal_lint  # noqa: E402
from lib.linters import cross_spec_lint  # noqa: E402
from lib.common.atomic_write import atomic_write_text  # noqa: E402
from lib.generators import prompt_gen  # noqa: E402
from lib.generators import render_gen  # noqa: E402
from lib.workflow import next_action  # noqa: E402

TEMPLATE_PATHS = {
    "feature": REPO_ROOT / "templates" / "proposal.template.md",
    "bugfix": REPO_ROOT / "templates" / "proposal-bugfix.template.md",
    "hotfix": REPO_ROOT / "templates" / "proposal-hotfix.template.md",
    "baseline": REPO_ROOT / "templates" / "proposal-baseline.template.md",
}
ENV_VAR = "SPECFLOW_SPEC_ROOT"

ID_MARKER = "id: PROP-XXXX"
TITLE_MARKER = 'title: "<一句話描述>"'

# change_id 直接被拼進路徑（spec_root / "changes" / change_id），所以必須限制字元集：
# 不能有路徑分隔符號、不能以非英數字元開頭（擋掉 "."、".."、"-foo" 這類會讓人誤讀的開頭）。
CHANGE_ID_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.-]{0,99}$")


def resolve_spec_root(explicit: str = None) -> Path:
    """算出目標專案的 spec root。

    優先序：--spec-root > SPECFLOW_SPEC_ROOT 環境變數 > 目前目錄底下的 .spec/
    （monorepo 模式）> 目前目錄本身（獨立 spec repo 模式）。最後一層一定成功，
    不會因為找不到而報錯——目錄選錯了會在後續指令操作時給出更具體的錯誤
    （例如「changes/ 底下沒有 proposal.md」），比在這裡就攔下來更有幫助。
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
    change_type = args.type

    if not CHANGE_ID_RE.match(change_id):
        print(
            f"change-id 格式不合法：{change_id!r}（只能是英數字/底線/連字號/句點，"
            "且不能以非英數字元開頭——change-id 會直接被拼進檔案路徑，格式必須嚴格）",
            file=sys.stderr,
        )
        return 1

    template_path = TEMPLATE_PATHS[change_type]
    if not template_path.exists():
        print(f"找不到範本：{template_path}", file=sys.stderr)
        return 1

    change_dir = spec_root / "changes" / change_id
    if change_dir.exists():
        print(f"change 已存在，不覆寫：{change_dir}", file=sys.stderr)
        return 1

    text = template_path.read_text(encoding="utf-8")
    if ID_MARKER not in text or TITLE_MARKER not in text:
        print(
            f"範本格式跟預期不符，找不到佔位標記（{ID_MARKER!r} / {TITLE_MARKER!r}），"
            f"請檢查 {template_path} 是否被改動過",
            file=sys.stderr,
        )
        return 1

    text = text.replace(ID_MARKER, f"id: {change_id}", 1)
    text = text.replace(TITLE_MARKER, f'title: "{title}"', 1)

    change_dir.mkdir(parents=True)
    atomic_write_text(change_dir / "proposal.md", text)

    if args.with_design:
        design_template_path = REPO_ROOT / "templates" / "design.template.md"
        design_text = design_template_path.read_text(encoding="utf-8")
        design_text = design_text.replace("change: CP-XXXX-change-slug", f"change: {change_id}", 1)
        atomic_write_text(change_dir / "design.md", design_text)

    print(f"已建立 change：{change_dir}（type: {change_type}）")
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
    proposal_type = gate["type"]

    t = lc.find_transition(current_status, args.event)
    if t is None:
        legal = [tt.event for tt in lc.transitions(current_status)]
        print(
            f"非法轉移：狀態 '{current_status}' 不接受事件 '{args.event}'（合法事件：{legal}）",
            file=sys.stderr,
        )
        return 1

    if t.requires_type and t.requires_type != proposal_type:
        print(
            f"非法轉移：事件 '{args.event}' 只允許 type: {t.requires_type} 的 change 使用"
            f"（這個 change 的 type 是 '{proposal_type}'）",
            file=sys.stderr,
        )
        return 1

    target = t.target

    # 轉移前先確認「轉移完成後」的狀態本身合法，不是只確認轉移前合法——曾經
    # 真的有過漏洞：draft 沒有 tasks.md 卻能合法轉移到要求 tasks.md 的 delivered，
    # 送進去之後這個 change 立刻違反自身 invariant，而且連修正用的轉移事件都
    # 會被 gate_check 擋住，等於卡死。唯一的例外是標記 skip_target_check 的轉移
    # （目前只有 HOTFIX_LIVE）——它的存在意義就是「先進入、事後才補前提」。
    if not t.skip_target_check:
        ok, action, errors = next_action.check_state_prerequisites(change_dir, lc, target)
        if not ok:
            print(
                f"擋下轉移：完成後的狀態 '{target}' 不符合前提條件（{action}）",
                file=sys.stderr,
            )
            for err in errors:
                print(f"  - {err}", file=sys.stderr)
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


def cmd_coverage(args: argparse.Namespace) -> int:
    """純資訊指令：glossary.yaml 定義了哪些實體、cross_spec_lint 實際檢查到
    哪幾層——讓接手一個沒有既有規格的專案時，能看得到「補文件補到哪了」，
    但不會因為還沒補完就擋住任何流程。exit code 永遠是 0。
    """
    spec_root = resolve_spec_root(args.spec_root)
    specs_dir = spec_root / "specs"
    glossary_path = specs_dir / "glossary.yaml"

    if not glossary_path.exists():
        print(f"{glossary_path} 不存在，還沒有任何 glossary 定義（這是合法的起點，不是錯誤）")
        return 0

    status_map = cross_spec_lint.load_glossary_status_map(glossary_path)
    if not status_map:
        print("glossary.yaml 裡還沒有任何實體")
        return 0

    print(f"glossary.yaml 定義了 {len(status_map)} 個實體：\n")
    for key in sorted(status_map):
        result = cross_spec_lint.lint_entity(glossary_path, key, specs_dir)
        checked = sorted(c.layer for c in result.checks if c.checked)
        skipped = sorted(c.layer for c in result.checks if not c.checked)
        icon = "✓" if checked else "…"
        checked_str = ", ".join(checked) if checked else "(無)"
        skipped_str = ", ".join(skipped) if skipped else "(無)"
        print(f"  {icon} {key}：已檢查 [{checked_str}]　略過 [{skipped_str}]")

    print(
        "\n（這裡只統計 glossary.yaml 裡已經定義的實體；還沒被寫進 glossary 的"
        "既有系統行為，本來就不會出現在這份清單——先動到哪個角落，才需要先補上那個角落。）"
    )
    return 0


def cmd_prompt(args: argparse.Namespace) -> int:
    """給一個 change-id，印出可以直接交給 AI 的交付內容——純輸出，不落地成任何檔案。

    RD 要拿到「交付指令跟資料」，跑這個指令就好；輸出裡已經包含 proposal 摘要、
    tasks.md、Blast Radius 統計、specs/ 的完整 diff，不需要再另外維護一份交付文件。
    """
    spec_root = resolve_spec_root(args.spec_root)
    change_dir = resolve_change_dir(spec_root, args.change)
    lifecycle_path = resolve_lifecycle_path(spec_root)

    gate = next_action.gate_check(change_dir, lifecycle_path=lifecycle_path)
    if not gate["ok"]:
        print(f"無法產生交付內容：change 目前未通過檢查（{gate['next_action']}）", file=sys.stderr)
        for err in gate["blocking_errors"]:
            print(f"  - {err}", file=sys.stderr)
        return 1

    lc = gate["lifecycle"]
    if not lc.allows(gate["status"], "generate_delivery"):
        print(
            f"無法產生交付內容：狀態 '{gate['status']}' 不允許 generate_delivery"
            "（這個狀態還不是可交付狀態，或已經超過交付階段）",
            file=sys.stderr,
        )
        return 1

    try:
        prompt = prompt_gen.build_prompt(change_dir.name, change_dir, spec_root, args.base)
    except RuntimeError as exc:
        print(f"產生失敗：{exc}", file=sys.stderr)
        return 1

    print(prompt)
    return 0


def cmd_render(args: argparse.Namespace) -> int:
    """把 specs/ 渲染成一組靜態 HTML（目錄頁 + 各 DSL 渲染後的產物），方便在瀏覽器
    查看——優先呼叫該生態系公認的既有工具（dbml-renderer / tsp compile+Redoc /
    wireframe-lofi），工具沒裝或渲染失敗時優雅退回顯示原始內容，並在頁面上印出
    安裝指令，不會讓整個指令因為某一層渲染失敗就掛掉。
    """
    spec_root = resolve_spec_root(args.spec_root)
    out_dir = Path(args.out).resolve() if args.out else (spec_root / "dist")

    render_gen.render(spec_root, out_dir)

    fallback_marker = "還沒渲染成產物"
    total, fell_back = 0, 0
    for html_path in out_dir.rglob("*.html"):
        if html_path.name in ("index.html", "glossary.html"):
            continue
        total += 1
        if fallback_marker in html_path.read_text(encoding="utf-8"):
            fell_back += 1

    print(f"已產出：{(out_dir / 'index.html').resolve()}")
    if total:
        rendered = total - fell_back
        print(f"渲染狀態：{rendered}/{total} 頁是真正的渲染產物，{fell_back} 頁因為工具沒裝退回顯示原始內容（頁面上有安裝指令）")
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
    init_parser.add_argument(
        "--type",
        choices=["feature", "bugfix", "hotfix", "baseline"],
        default="feature",
        help="決定套用哪一份範本、哪一組 proposal_lint 規則（預設: feature）",
    )
    init_parser.add_argument(
        "--with-design",
        action="store_true",
        help="同時建立 design.md（裝技術決策與取捨，proposal.md 的行數限制不適用）",
    )
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

    coverage_parser = subparsers.add_parser(
        "coverage", help="純資訊：glossary.yaml 裡每個實體被 cross_spec_lint 檢查到哪幾層（不會擋任何流程）"
    )
    _add_spec_root_arg(coverage_parser)
    coverage_parser.set_defaults(func=cmd_coverage)

    render_parser = subparsers.add_parser(
        "render", help="把 specs/ 渲染成一組渲染後的靜態 HTML（目錄頁 + 各 DSL 產物），方便在瀏覽器查看"
    )
    _add_spec_root_arg(render_parser)
    render_parser.add_argument("--out", default=None, help="輸出目錄（預設：<spec-root>/dist）")
    render_parser.set_defaults(func=cmd_render)

    prompt_parser = subparsers.add_parser(
        "prompt", help="給一個 change-id，印出交付給 AI 的完整指令（純輸出，不落地成檔案）"
    )
    _add_spec_root_arg(prompt_parser)
    prompt_parser.add_argument("change", help="change-id 或實際路徑")
    prompt_parser.add_argument(
        "--base", default="main", help="比較的基準 branch/ref（預設: main）"
    )
    prompt_parser.set_defaults(func=cmd_prompt)

    return parser


def main(argv=None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())
