"""change 資料夾的檔案白名單檢查（default-deny）。

changes/<id>/ 底下只允許存在固定的檔案清單，出現任何其他檔案（不管內容多好、
是不是 AI 自己覺得有幫助而多寫的說明文件）一律判定失敗——不審查內容，只審查
「這個東西有沒有資格存在」。

用法：
    python3 change_shape_lint.py <change-dir>
"""

from __future__ import annotations

import sys
from dataclasses import dataclass, field
from pathlib import Path

ALLOWED_FILES = {"proposal.md", "tasks.md"}
ALLOWED_HIDDEN_FILES = {".gitkeep"}  # 唯一放行的點開頭檔案；其他一律不放過（含隱藏子目錄）


@dataclass
class LintResult:
    path: Path
    errors: list = field(default_factory=list)

    @property
    def ok(self) -> bool:
        return not self.errors


def lint_dir(change_dir: Path) -> LintResult:
    result = LintResult(path=change_dir)

    if not change_dir.exists():
        result.errors.append(f"找不到目錄：{change_dir}")
        return result
    if not change_dir.is_dir():
        result.errors.append(f"不是目錄：{change_dir}")
        return result

    for entry in sorted(change_dir.iterdir()):
        if entry.name in ALLOWED_HIDDEN_FILES and entry.is_file():
            continue  # 只有明確列在白名單裡的點開頭「檔案」才放行，隱藏子目錄一律不放過
        if entry.is_dir():
            result.errors.append(f"不允許子目錄：{entry.name}/（changes/<id>/ 必須是平的）")
            continue
        if entry.name not in ALLOWED_FILES:
            result.errors.append(
                f"不允許的檔案：{entry.name}（changes/<id>/ 只能有 {sorted(ALLOWED_FILES)}）"
            )

    if not (change_dir / "proposal.md").exists():
        result.errors.append("缺少必要檔案：proposal.md")

    return result


def main(argv=None) -> int:
    argv = argv if argv is not None else sys.argv[1:]
    if not argv:
        print("用法: change_shape_lint.py <change-dir>", file=sys.stderr)
        return 2

    change_dir = Path(argv[0])
    result = lint_dir(change_dir)

    if result.ok:
        print(f"✓ {change_dir}")
        return 0

    print(f"✗ {change_dir}")
    for err in result.errors:
        print(f"  - {err}")
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
