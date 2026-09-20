"""Diff 即 Prompt：給一個 change-id，組出可以直接交給 AI 的完整交付指令。

刻意不落地成任何新檔案——這是純函式 + CLI 輸出，RD 自己複製貼上或接到別的工具。
如果把輸出寫成 changes/<id>/ 底下的第三個檔案，會直接違反 change_shape_lint 的
白名單（那條線是刻意畫的：change 資料夾只能有 proposal.md、tasks.md，不能再多）。
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

## Blast Radius
{blast_radius_summary}

## Git Diff（specs/ 相對於 {base_ref}）
{diff}

## 交付要求
1. 只實作 diff 中涉及的規格變更，不擴大範圍（No Scope Creep）。
2. 若 diff 修改了 db/schema.dbml，同步更新對應的 migration。
3. 若 diff 修改了 api/main.tsp，重新編譯 OpenAPI 並更新對應的 handler/DTO。
4. 若 diff 修改了 logic/rules/*.yaml，用該決策表的每一列作為單元測試案例。
5. commit 訊息使用 `<verb>({change_id}/<task-id>): <message>` 格式。
6. 完成後列出你觸碰到的檔案清單，供人工比對 Impact Surface 是否吻合。
"""


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


def build_prompt(change_id: str, change_dir: Path, spec_root: Path, base_ref: str = "main") -> str:
    proposal_path = change_dir / "proposal.md"
    text = proposal_path.read_text(encoding="utf-8")
    fm_data, body, _error = fm.load_frontmatter_data(text)
    title = fm_data.get("title", "") if isinstance(fm_data, dict) else ""

    specs_dir = spec_root / "specs"
    analysis = diff_analyzer.analyze(specs_dir, base_ref)
    diff = get_specs_diff(specs_dir, base_ref)

    return PROMPT_TEMPLATE.format(
        change_id=change_id,
        proposal_title=title,
        proposal_body=body.strip(),
        blast_radius_summary=analysis["summary"],
        base_ref=base_ref,
        diff=diff if diff.strip() else "(specs/ 無變更——如果這不符合預期，檢查一下 --base 是否指對分支）",
    )


def main(argv=None) -> int:
    argv = argv if argv is not None else sys.argv[1:]
    if len(argv) < 2:
        print("用法: prompt_gen.py <change-dir> <spec-root> [base_ref=main]", file=sys.stderr)
        return 2

    change_dir = Path(argv[0])
    spec_root = Path(argv[1])
    base_ref = argv[2] if len(argv) > 2 else "main"

    prompt = build_prompt(change_dir.name, change_dir, spec_root, base_ref)
    print(prompt)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
