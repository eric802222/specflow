"""Diff 即 Prompt：給一個 change-id，組出可以直接交給 AI 的完整交付指令。

刻意不落地成任何新檔案——這是純函式 + CLI 輸出，RD 自己複製貼上或接到別的工具。
如果把輸出寫成 changes/<id>/ 底下的第三個檔案，會直接違反 change_shape_lint 的
白名單（那條線是刻意畫的：change 資料夾只能有 proposal.md、tasks.md，不能再多）。

輸出裡必須包含 tasks.md 的完整內容，不能只有 proposal 摘要跟 diff——不然 commit
訊息要求的 `<task-id>` 格式，AI 根本沒拿到 task 清單可以引用，契約不完整。
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(REPO_ROOT))

from lib.analyzers import diff_analyzer  # noqa: E402
from lib.common import frontmatter as fm  # noqa: E402

PROMPT_TEMPLATE = """\
# SpecFlow 交付任務：{change_id}

## Proposal
{proposal_title}

{proposal_body}

## Tasks
{tasks_section}

## Blast Radius
{blast_radius_summary}

## Git Diff（specs/ 相對於 {base_ref}）
{diff}

## 交付要求
{delivery_requirements}
"""

# 只在 diff 真的動到對應層時才加進交付要求——之前這三條是無條件塞進每一次
# `specflow prompt` 輸出，一個完全沒用 DBML/TypeSpec/決策表的專案，AI 讀到
# 會困惑「這個專案哪來的 db/schema.dbml」。跟 #9／cross_spec_lint／render_gen
# 是同一個病根：核心邏輯假設了 db/api/logic 三層 DSL 一定存在。
CONDITIONAL_REQUIREMENTS = {
    "db": "若 diff 修改了 db/schema.dbml，同步更新對應的 migration。",
    "api": "若 diff 修改了 api/main.tsp，重新編譯 OpenAPI 並更新對應的 handler/DTO。",
    "logic": "若 diff 修改了 logic/rules/*.yaml，用該決策表的每一列作為單元測試案例。",
}


def _resolve_base_ref(cwd: Path) -> str:
    """依序嘗試 origin/HEAD → main → master → 目前 HEAD，回傳第一個真的存在的 ref。

    這是真實踩過的坑：新 repo 預設分支是 master，寫死 main 會讓第一個要跑的指令
    直接噴 `fatal: bad revision 'main'`——而且這是流程文件教人下的第一個指令，
    第一步就紅字會讓人懷疑整套工具沒裝好。最後一層 fallback 是 HEAD，
    一定會成功（diff 對自己永遠是空的，但至少不會讓指令崩潰）。
    """
    candidates = []
    try:
        result = subprocess.run(
            ["git", "symbolic-ref", "refs/remotes/origin/HEAD"],
            cwd=str(cwd), capture_output=True, text=True, timeout=10,
        )
        if result.returncode == 0:
            branch = result.stdout.strip().rsplit("/", 1)[-1]
            if branch:
                candidates.append(f"origin/{branch}")
    except (FileNotFoundError, subprocess.TimeoutExpired):
        pass

    candidates += ["main", "master"]

    for ref in candidates:
        try:
            check = subprocess.run(
                ["git", "rev-parse", "--verify", "--quiet", ref],
                cwd=str(cwd), capture_output=True, timeout=10,
            )
        except (FileNotFoundError, subprocess.TimeoutExpired):
            break
        if check.returncode == 0:
            return ref

    return "HEAD"


def get_specs_diff(specs_dir: Path, base_ref: str = "HEAD") -> str:
    cwd = specs_dir if specs_dir.exists() else specs_dir.parent
    try:
        return subprocess.run(
            ["git", "diff", base_ref, "--", str(specs_dir)],
            cwd=str(cwd),
            capture_output=True,
            text=True,
            check=True,
        ).stdout
    except subprocess.CalledProcessError as exc:
        raise RuntimeError(f"git diff 失敗：{exc.stderr}") from exc


def _read_tasks_section(tasks_path: Path) -> str:
    """讀出 tasks.md 的正文（不含 frontmatter），保留原始順序跟每行內容原封不動。"""
    if not tasks_path.exists():
        return "(尚未建立 tasks.md)"

    text = tasks_path.read_text(encoding="utf-8")
    _fm_data, body, error = fm.load_frontmatter_data(text)
    if error:
        # frontmatter 壞掉也不要整個 prompt 產生失敗——這裡只是把原始內容原樣
        # 附上，真正的格式問題應該在 gate_check 那一關就被擋下來，這裡是最後防線。
        return text.strip()
    return body.strip() if body.strip() else "(tasks.md 是空的)"


def _build_delivery_requirements(change_id: str, buckets: dict) -> str:
    """組出交付要求清單：固定項目 + 只在 diff 實際動到對應層時才出現的條件式指示。"""
    items = ["只實作 diff 中涉及的規格變更，不擴大範圍（No Scope Creep）。"]

    for layer, instruction in CONDITIONAL_REQUIREMENTS.items():
        if buckets.get(layer):
            items.append(instruction)

    items.append(
        f"每完成一個 task 就 commit 一次，訊息用 `<verb>({change_id}/<task-id>): <message>` "
        "格式，<task-id> 必須對應上面 Tasks 清單裡的其中一項。"
    )
    items.append("完成後列出你觸碰到的檔案清單，供人工比對 Impact Surface 與各 task 的 touches 是否吻合。")

    return "\n".join(f"{i}. {text}" for i, text in enumerate(items, start=1))


def build_prompt(change_id: str, change_dir: Path, spec_root: Path, base_ref: str = None) -> str:
    proposal_path = change_dir / "proposal.md"
    text = proposal_path.read_text(encoding="utf-8")
    fm_data, body, _error = fm.load_frontmatter_data(text)
    title = fm_data.get("title", "") if isinstance(fm_data, dict) else ""

    tasks_section = _read_tasks_section(change_dir / "tasks.md")

    specs_dir = spec_root / "specs"
    resolved_base_ref = base_ref if base_ref else _resolve_base_ref(specs_dir if specs_dir.exists() else spec_root)
    analysis = diff_analyzer.analyze(specs_dir, resolved_base_ref)
    diff = get_specs_diff(specs_dir, resolved_base_ref)

    return PROMPT_TEMPLATE.format(
        change_id=change_id,
        proposal_title=title,
        proposal_body=body.strip(),
        tasks_section=tasks_section,
        blast_radius_summary=analysis["summary"],
        base_ref=resolved_base_ref,
        diff=diff if diff.strip() else "(specs/ 無變更——如果這不符合預期，檢查一下 --base 是否指對分支)",
        delivery_requirements=_build_delivery_requirements(change_id, analysis["buckets"]),
    )


def main(argv=None) -> int:
    argv = argv if argv is not None else sys.argv[1:]
    if len(argv) < 2:
        print("用法: prompt_gen.py <change-dir> <spec-root> [base_ref]", file=sys.stderr)
        return 2

    change_dir = Path(argv[0])
    spec_root = Path(argv[1])
    base_ref = argv[2] if len(argv) > 2 else None

    prompt = build_prompt(change_dir.name, change_dir, spec_root, base_ref)
    print(prompt)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
