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

try:
    import yaml
except ImportError:  # pragma: no cover
    yaml = None

MAX_BODY_LINES = 35
REQUIRED_FRONTMATTER_KEYS = ("id", "title", "impact_surface")
REQUIRED_SECTION = "## 3. 非目標 (Non-Goals)"
CODE_FENCE = "```"


@dataclass
class LintResult:
    path: Path
    errors: list = field(default_factory=list)

    @property
    def ok(self) -> bool:
        return not self.errors


def _split_frontmatter(text: str):
    """把檔案切成 (frontmatter_yaml, body)。若找不到合法的 --- 區塊則回傳 (None, text)。"""
    if not text.startswith("---"):
        return None, text
    parts = text.split("---", 2)
    if len(parts) < 3:
        return None, text
    _, fm_text, body = parts
    return fm_text, body


def _effective_line_count(body: str) -> int:
    """計算正文中的有效（非空白）行數。"""
    return sum(1 for line in body.splitlines() if line.strip())


def lint_text(text: str, path: Path = None) -> LintResult:
    result = LintResult(path=path or Path("<memory>"))

    fm_text, body = _split_frontmatter(text)

    if fm_text is None:
        result.errors.append("缺少 frontmatter 區塊（檔案必須以 --- 開頭並包含結尾的 ---）")
        fm_data = {}
    elif yaml is None:
        result.errors.append("缺少 pyyaml 套件，無法解析 frontmatter")
        fm_data = {}
    else:
        try:
            fm_data = yaml.safe_load(fm_text) or {}
        except yaml.YAMLError as exc:
            result.errors.append(f"frontmatter YAML 解析失敗：{exc}")
            fm_data = {}

    if isinstance(fm_data, dict):
        for key in REQUIRED_FRONTMATTER_KEYS:
            if key not in fm_data or fm_data[key] in (None, "", []):
                result.errors.append(f"frontmatter 缺少必要欄位：{key}")
    elif fm_text is not None:
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
