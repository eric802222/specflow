"""Proposal 前導 Markdown（Frontmatter Markdown）Linter。

驗證一份 specflow proposal 檔案是否符合契約：
  1. Frontmatter 必須包含：id, title, impact_surface
  2. 正文有效（非空）行數不得超過 35 行
  3. 嚴禁出現代碼塊標記（```），全文皆不可有
  4. 必須存在 "## 3. 非目標 (Non-Goals)" 區塊

用法：
    python3 proposal_lint.py <path-to-proposal.md> [<path> ...]
"""

from __future__ import annotations

import sys
from dataclasses import dataclass, field
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(REPO_ROOT))

from lib.common import frontmatter as fm  # noqa: E402

MAX_BODY_LINES = 35
REQUIRED_FRONTMATTER_KEYS = ("id", "title", "impact_surface")
REQUIRED_SECTION = "## 3. 非目標 (Non-Goals)"
CODE_FENCE = "```"

# 對外沿用舊名稱，讓其他呼叫端（bin/specflow.py 等）不用改 import
read_frontmatter = fm.read_frontmatter
write_frontmatter_field = fm.write_frontmatter_field


@dataclass
class LintResult:
    path: Path
    errors: list = field(default_factory=list)

    @property
    def ok(self) -> bool:
        return not self.errors


def _effective_line_count(body: str) -> int:
    """計算正文中的有效（非空白）行數。"""
    return sum(1 for line in body.splitlines() if line.strip())


def lint_text(text: str, path: Path = None) -> LintResult:
    result = LintResult(path=path or Path("<memory>"))

    fm_data, body, error = fm.load_frontmatter_data(text)
    if error:
        result.errors.append(error)
        fm_data = fm_data or {}

    if isinstance(fm_data, dict):
        for key in REQUIRED_FRONTMATTER_KEYS:
            if key not in fm_data or fm_data[key] in (None, "", []):
                result.errors.append(f"frontmatter 缺少必要欄位：{key}")
    elif not error:
        result.errors.append("frontmatter 必須是一個 YAML mapping")

    if CODE_FENCE in text:
        result.errors.append(f"嚴禁出現代碼塊標記（{CODE_FENCE}）")

    line_count = _effective_line_count(body)
    if line_count > MAX_BODY_LINES:
        result.errors.append(
            f"正文有效非空行數為 {line_count}，超過上限 {MAX_BODY_LINES} 行"
        )

    if REQUIRED_SECTION not in body:
        result.errors.append(f"必須存在區塊：{REQUIRED_SECTION}")

    return result


def lint_file(path: Path) -> LintResult:
    text = path.read_text(encoding="utf-8")
    return lint_text(text, path=path)


def main(argv=None) -> int:
    argv = argv if argv is not None else sys.argv[1:]
    if not argv:
        print("用法: proposal_lint.py <path-to-proposal.md> [<path> ...]", file=sys.stderr)
        return 2

    exit_code = 0
    for arg in argv:
        path = Path(arg)
        if not path.exists():
            print(f"✗ {path}: 檔案不存在")
            exit_code = 1
            continue
        result = lint_file(path)
        if result.ok:
            print(f"✓ {path}")
        else:
            print(f"✗ {path}")
            for err in result.errors:
                print(f"  - {err}")
            exit_code = 1
    return exit_code


if __name__ == "__main__":
    raise SystemExit(main())
