"""design.md 的結構檢查（poka-yoke）。

跟 proposal.md 不同，design.md 裝的是「為什麼」——每個工程決策的觸發情境、
最終選擇、換來的取捨。這種內容如果寫成自由段落，讀者要自己從句子裡拆解出
「這是觸發原因」還是「這是最終決定」，心智負擔很重。所以這裡不是靠行數上限
逼你精簡，是**格式本身不給你寫成段落的空間**：每個決策只能用固定的欄位
（事件／決策／取捨），順序固定，不允許出現欄位以外的任何文字。

檔案最上方的「待確認」摘要清單跟內文的狀態標記互相交叉比對，兩邊對不上就是
錯誤——避免摘要過期卻沒人發現（這正是我們一路在防的：兩份資料各自維護、
彼此漂移）。

規則：
  1. Frontmatter 必須有 `change` 欄位，且值要等於外部傳入的 change_id
  2. 每個決策標題格式：`### <emoji> D<n> — <標題>`，emoji 只能是 ✅／⏳／🚫
  3. D 編號不得重複
  4. 決策內文只能是固定欄位，依序：
       - **事件**：<觸發這個決策的情境／問題>          （必填）
       - **決策**：<選了什麼>                          （必填）
       - **取捨**：<放棄了什麼、換來什麼代價>           （可選）
     順序不能顛倒，不能出現這三個欄位以外的任何文字，每個欄位值限單行、
     不得超過 MAX_FIELD_LENGTH 字元（逼你精簡，不是拿一行硬塞一整段話）
  5. 嚴禁代碼塊標記（狀態圖這類內容該進 specs/logic/，不是塞在這裡）
  6. 只要有非 ✅ 的決策，檔案最上方必須有 `## ⏳ 待確認（N）` 摘要區塊，
     N 要等於非 ✅ 決策的數量，區塊底下列出的 D 編號要跟內文的非 ✅ 決策
     完全對得上（多列、少列、或列出已經是 ✅ 的都算錯誤）

用法：
    python3 design_lint.py <design.md> <expected-change-id>
"""

from __future__ import annotations

import re
import sys
from dataclasses import dataclass, field
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(REPO_ROOT))

from lib.common import frontmatter as fm  # noqa: E402

MAX_FIELD_LENGTH = 200
CODE_FENCE = "```"

STATUS_CONFIRMED = "✅"
STATUS_PENDING = "⏳"
STATUS_BLOCKED = "🚫"

FIELD_ORDER = ("事件", "決策", "取捨")
REQUIRED_FIELDS = ("事件", "決策")

DECISION_HEADING_RE = re.compile(
    r"^### (?P<emoji>✅|⏳|🚫) D(?P<num>\d+) — (?P<title>.+?)\s*$", re.MULTILINE
)
FIELD_LINE_RE = re.compile(r"^-\s+\*\*(事件|決策|取捨)\*\*：\s*(.+)$")
SUMMARY_HEADING_RE = re.compile(r"^## ⏳ 待確認（(?P<count>\d+)）\s*$", re.MULTILINE)
SUMMARY_BULLET_RE = re.compile(r"^-\s+\*\*D(?P<num>\d+)\*\*\s+—", re.MULTILINE)


@dataclass
class LintResult:
    path: Path
    errors: list = field(default_factory=list)

    @property
    def ok(self) -> bool:
        return not self.errors


def _find_decisions(body: str):
    """回傳 [(emoji, num, title, decision_body_text, lineno), ...]，依出現順序。"""
    matches = list(DECISION_HEADING_RE.finditer(body))
    decisions = []
    for i, m in enumerate(matches):
        start = m.end()
        end = matches[i + 1].start() if i + 1 < len(matches) else len(body)
        decision_body = body[start:end]
        lineno = body.count("\n", 0, m.start()) + 1
        decisions.append((m.group("emoji"), m.group("num"), m.group("title"), decision_body, lineno))
    return decisions


def _validate_decision_fields(decision_body: str, num: str) -> list:
    """驗證決策內文只用固定欄位、依序、無多餘文字。回傳錯誤訊息清單。"""
    errors = []
    seen_labels = []

    for raw_line in decision_body.splitlines():
        line = raw_line.strip()
        if not line:
            continue

        m = FIELD_LINE_RE.match(line)
        if not m:
            errors.append(
                f"D{num}：不合法的內容 '{line}'"
                "（只能用 '- **事件**：...' / '- **決策**：...' / '- **取捨**：...' 三種欄位，不允許自由段落文字）"
            )
            continue

        label, value = m.group(1), m.group(2)
        if label in seen_labels:
            errors.append(f"D{num}：欄位 '{label}' 重複")
        seen_labels.append(label)

        if len(value) > MAX_FIELD_LENGTH:
            errors.append(f"D{num} 的 '{label}' 欄位長度為 {len(value)} 字元，超過上限 {MAX_FIELD_LENGTH}")

    for required in REQUIRED_FIELDS:
        if required not in seen_labels:
            errors.append(f"D{num}：缺少必要欄位 '{required}'")

    last_idx = -1
    for label in seen_labels:
        idx = FIELD_ORDER.index(label)
        if idx < last_idx:
            errors.append(f"D{num}：欄位順序錯誤，必須依序是 {' → '.join(FIELD_ORDER)}（'{label}' 出現在不對的位置）")
        last_idx = idx

    return errors


def _find_summary(body: str):
    """回傳 (count_declared, {列出的 D 編號}) 或 None（找不到摘要區塊）。"""
    m = SUMMARY_HEADING_RE.search(body)
    if not m:
        return None
    start = m.end()
    next_heading = re.search(r"^## ", body[start:], re.MULTILINE)
    end = start + next_heading.start() if next_heading else len(body)
    section = body[start:end]
    listed = {bm.group("num") for bm in SUMMARY_BULLET_RE.finditer(section)}
    return int(m.group("count")), listed


def lint_text(text: str, expected_change_id: str, path: Path = None) -> LintResult:
    result = LintResult(path=path or Path("<memory>"))

    fm_data, body, error = fm.load_frontmatter_data(text)
    if error:
        result.errors.append(error)
        fm_data = fm_data or {}

    if isinstance(fm_data, dict):
        change_ref = fm_data.get("change")
        if not change_ref:
            result.errors.append("frontmatter 缺少必要欄位：change")
        elif change_ref != expected_change_id:
            result.errors.append(
                f"frontmatter 的 change ('{change_ref}') 與所在資料夾 ('{expected_change_id}') 不一致"
            )
    elif not error:
        result.errors.append("frontmatter 必須是一個 YAML mapping")

    if CODE_FENCE in text:
        result.errors.append(f"嚴禁出現代碼塊標記（{CODE_FENCE}）——狀態圖等內容應該進 specs/logic/，不是塞在 design.md")

    decisions = _find_decisions(body)
    seen_nums = set()
    for emoji, num, title, decision_body, lineno in decisions:
        if num in seen_nums:
            result.errors.append(f"第 {lineno} 行：D{num} 編號重複")
        seen_nums.add(num)

        result.errors.extend(_validate_decision_fields(decision_body, num))

    pending_nums = {num for emoji, num, *_ in decisions if emoji != STATUS_CONFIRMED}
    summary = _find_summary(body)

    if pending_nums and summary is None:
        result.errors.append(
            f"有 {len(pending_nums)} 個待確認決策（{sorted(pending_nums)}），"
            "但檔案最上方缺少 '## ⏳ 待確認（N）' 摘要區塊"
        )
    elif summary is not None:
        declared_count, listed_nums = summary
        if declared_count != len(pending_nums):
            result.errors.append(
                f"摘要區塊宣告 {declared_count} 個待確認，但內文實際有 {len(pending_nums)} 個"
            )

        extra_in_summary = listed_nums - pending_nums
        missing_from_summary = pending_nums - listed_nums
        if extra_in_summary:
            result.errors.append(
                f"摘要區塊列出了 {sorted(extra_in_summary)}，但這些決策在內文已經是 ✅ 或不存在——摘要過期了"
            )
        if missing_from_summary:
            result.errors.append(
                f"內文有待確認決策 {sorted(missing_from_summary)}，但摘要區塊沒有列出——摘要漏更新了"
            )

    return result


def lint_file(path: Path, expected_change_id: str) -> LintResult:
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
