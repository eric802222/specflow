"""design.md 的結構檢查——薯層封裝，實際邏輯在 lib/common/structured_decision.py。

design.md 裝的是「為什麼」——每個工程決策的觸發情境、最終選擇（或候選選項）、
換來的取捨。跟 review.md（審查發現）共用同一套「固定欄位 + checkbox 選項 +
摘要交叉比對」核心機制，這裡只定義 design.md 專屬的欄位名稱與狀態集合：

    已定案（✅）：事件 / 決策 / 取捨(可選)
    待確認／卡住（⏳／🚫）：事件 / 選項(≥2 個 + 其他補充) / 取捨(可選)

用法：
    python3 design_lint.py <design.md> <expected-change-id>
"""

from __future__ import annotations

import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(REPO_ROOT))

from lib.common.structured_decision import StructuredSchema, lint_structured_text  # noqa: E402

SCHEMA = StructuredSchema(
    entity_prefix="D",
    entity_noun="決策",
    confirmed_status="✅",
    pending_statuses=("⏳", "🚫"),
    confirmed_field_order=("事件", "決策", "取捨"),
    confirmed_required=("事件", "決策"),
    pending_field_order=("事件", "選項", "取捨"),
    pending_required=("事件",),
    checkbox_field_label="選項",
    summary_icon="⏳",
    summary_label="待確認",
)


def lint_text(text: str, expected_change_id: str, path: Path = None):
    return lint_structured_text(text, expected_change_id, SCHEMA, path=path)


def lint_file(path: Path, expected_change_id: str):
    text = path.read_text(encoding="utf-8")
    return lint_text(text, expected_change_id, path=path)


def main(argv=None) -> int:
    argv = argv if argv is not None else sys.argv[1:]
    if len(argv) < 2:
        print("用法: design_lint.py <design.md> <expected-change-id>", file=sys.stderr)
        return 2

    path = Path(argv[0])
    expected_change_id = argv[1]

    if not path.exists():
        print(f"✗ {path}: 檔案不存在")
        return 1

    result = lint_file(path, expected_change_id)
    if result.ok:
        print(f"✓ {path}")
        return 0

    print(f"✗ {path}")
    for err in result.errors:
        print(f"  - {err}")
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
