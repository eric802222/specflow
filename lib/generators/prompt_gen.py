"""Diff 即 Prompt：把 `.spec/` 的 git diff 組合成可直接交給 LLM 的交付 Prompt。

核心哲學：修改只發生在 `.spec/`，審查通過後，Git Diff 本身就是給 AI 的完整上下文——
不需要工程師另外用自然語言重述「我改了什麼」。
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

PROMPT_TEMPLATE = """\
# SpecFlow 交付任務

以下是 `.spec/` 目錄中，經審查通過的規格變更（Git Diff）。
請嚴格依照這份 diff 實作程式碼，禁止對未變更的規格臆測或擴充功能範圍。

## 變更摘要
{summary}

## Git Diff
{diff}

## 交付要求
1. 只實作 diff 中涉及的規格變更，不擴大範圍（No Scope Creep）。
2. 若 diff 修改了 db/schema.dbml，同步更新對應的 migration。
3. 若 diff 修改了 api/main.tsp，重新編譯 OpenAPI 並更新對應的 handler/DTO。
4. 若 diff 修改了 logic/rules/*.yaml，用該決策表的每一列作為單元測試案例。
5. 完成後列出你觸碰到的檔案清單，供人工比對 Impact Surface 是否吻合。
"""


def get_spec_diff(spec_root: Path, base_ref: str = "HEAD") -> str:
    try:
        return subprocess.run(
            ["git", "diff", base_ref, "--", str(spec_root)],
            capture_output=True,
            text=True,
            check=True,
        ).stdout
    except subprocess.CalledProcessError as exc:
        raise RuntimeError(f"git diff 失敗：{exc.stderr}") from exc


def build_prompt(diff: str, summary: str = "(未提供摘要，請直接依 diff 內容判斷)") -> str:
    return PROMPT_TEMPLATE.format(summary=summary, diff=diff if diff.strip() else "(無變更)")


def main(argv=None) -> int:
    argv = argv if argv is not None else sys.argv[1:]
    spec_root = Path(argv[0]) if argv else Path(".spec")
    base_ref = argv[1] if len(argv) > 1 else "HEAD"

    diff = get_spec_diff(spec_root, base_ref)
    prompt = build_prompt(diff)
    print(prompt)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
