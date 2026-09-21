"""review.md 的結構檢查——薄層封裝，實際邏輯在 lib/common/structured_decision.py。

review.md 裝的是 code review 發現的問題與結案狀態，跟 design.md 共用同一套
「固定欄位 + checkbox 選項 + 摘要交叉比對」核心機制，只是欄位名稱換成審查情境：

    已結案（✅）：位置 / 問題 / 處置
    待處理（⏳）：位置 / 問題 / 選項(≥2 個 + 其他補充)

specflow 本身不負責把 MR/PR 上的討論串轉寫成這個格式——那需要能存取
GitLab/GitHub 的 agent 去做，怎麼串接屬於各團隊自己的工作流程。specflow 只
提供格式規格跟這支檢查工具，寫出來的 review.md 合不合規，跑這支就知道。

用法：
    python3 review_lint.py <review.md> <expected-change-id>
"""

from __future__ import annotations

import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(REPO_ROOT))

from lib.common import structured_decision  # noqa: E402
from lib.common.structured_decision import StructuredSchema, lint_structured_text  # noqa: E402

SCHEMA = StructuredSchema(
    entity_prefix="F",
    entity_noun="發現項目",
    confirmed_status="✅",
    pending_statuses=("⏳",),
    confirmed_field_order=("位置", "問題", "處置"),
    confirmed_required=("位置", "問題", "處置"),
    pending_field_order=("位置", "問題", "選項"),
    pending_required=("位置", "問題"),
    checkbox_field_label="選項",
    summary_icon="🔴",
    summary_label="待處理",
)


def lint_text(text: str, expected_change_id: str, path: Path = None):
    return lint_structured_text(text, expected_change_id, SCHEMA, path=path)


def find_pending(path: Path) -> list:
    """回傳 review.md 裡目前還沒結案（非 ✅）的發現項目 [(num, title), ...]。
    給 REVIEW_PASS 這個真正的把關用——只驗證格式合法不夠，review 沒有真的
    結案就不該放行，否則就只是把 DEV_DONE 那層的榮譽制搬到 review 這層而已。"""
    text = path.read_text(encoding="utf-8")
    return structured_decision.find_pending(text, SCHEMA)


def lint_file(path: Path, expected_change_id: str):
    text = path.read_text(encoding="utf-8")
    return lint_text(text, expected_change_id, path=path)


def main(argv=None) -> int:
    argv = argv if argv is not None else sys.argv[1:]
    if len(argv) < 2:
        print("用法: review_lint.py <review.md> <expected-change-id>", file=sys.stderr)
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
