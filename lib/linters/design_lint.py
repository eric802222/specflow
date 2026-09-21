"""design.md 的結構檢查（poka-yoke）。

跟 proposal.md 不同，design.md 裝的是「為什麼」——每個工程決策的觸發情境、
最終選擇（或候選選項）、換來的取捨。這種內容如果寫成自由段落，讀者要自己從
句子裡拆解出「這是觸發原因」還是「這是最終決定」，心智負擔很重；如果是還在
討論中的決策，丟一句「待確認」給讀者，讀者還要自己想答案。所以這裡不是靠
行數上限逼你精簡，是**格式本身不給你寫成段落、也不給你留白問答題的空間**：

已定案（✅）的決策只能用固定欄位：
    - **事件**：<觸發這個決策的情境／問題>          （必填）
    - **決策**：<選了什麼>                          （必填）
    - **取捨**：<放棄了什麼、換來什麼代價>           （可選）

待確認／卡住（⏳／🚫）的決策不能寫「決策」——都還沒定案，不該假裝有答案。
改成列出候選選項，用跟 tasks.md 一樣的 checkbox 語法，讓決策者用「選」的，
不用自己從零想答案：
    - **事件**：<觸發這個決策的情境／問題>          （必填）
    - **選項**：
      - [ ] <候選方案一>
      - [ ] <候選方案二>
      - [ ] 其他補充：<留給決策者自己寫，不想被選項綁死時用>
    - **取捨**：<可選，通常留給定案後才補>

選項清單至少要 2 個（逼你真的想過候選方案，不是隨便丟一句「待討論」），且
必須包含「其他補充」這一項，避免選項清單變成強迫二選一的陷阱。**勾了一個
選項、但狀態還是 ⏳／🚫，會被視為錯誤**——這代表已經決定了，就該把這個決策
改成 ✅、改用「事件／決策／取捨」欄位記錄最終結果，不該讓檔案同時說「還沒
決定」又「已經勾了答案」這種矛盾狀態存在。

檔案最上方的「待確認」摘要清單跟內文的狀態標記互相交叉比對，兩邊對不上就是
錯誤——避免摘要過期卻沒人發現。

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
MIN_OPTIONS = 2
SUPPLEMENT_LABEL = "其他補充"
CODE_FENCE = "```"

STATUS_CONFIRMED = "✅"
STATUS_PENDING = "⏳"
STATUS_BLOCKED = "🚫"

CONFIRMED_FIELD_ORDER = ("事件", "決策", "取捨")
CONFIRMED_REQUIRED = ("事件", "決策")

PENDING_FIELD_ORDER = ("事件", "選項", "取捨")
PENDING_REQUIRED = ("事件",)

DECISION_HEADING_RE = re.compile(
    r"^### (?P<emoji>✅|⏳|🚫) D(?P<num>\d+) — (?P<title>.+?)\s*$", re.MULTILINE
)
FIELD_LINE_RE = re.compile(r"^-\s+\*\*(事件|決策|取捨|選項)\*\*：\s*(.*)$")
OPTION_ITEM_RE = re.compile(r"^-\s+\[( |x|X)\]\s*(.*)$")
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


def _parse_decision_body(decision_body: str, num: str):
    """把決策內文解析成 [{"label": str, "value": str}] 或
    [{"label": "選項", "options": [(checked: bool, text: str), ...]}]。
    回傳 (parsed, errors)。"""
    parsed = []
    errors = []
    lines = decision_body.splitlines()
    i, n = 0, len(lines)

    while i < n:
        raw = lines[i]
        stripped = raw.strip()
        if not stripped:
            i += 1
            continue

        m = FIELD_LINE_RE.match(stripped)
        if not m:
            errors.append(
                f"D{num}：不合法的內容 '{stripped}'"
                "（只能用 '- **事件**：...' / '- **決策**：...' / '- **取捨**：...' / '- **選項**：' 這幾種固定欄位）"
            )
            i += 1
            continue

        label, value = m.group(1), m.group(2)

        if label == "選項":
            options = []
            i += 1
            while i < n:
                sub_raw = lines[i]
                sub_stripped = sub_raw.strip()
                if not sub_stripped:
                    i += 1
                    continue
                is_indented = sub_raw[:1] in (" ", "\t")
                om = OPTION_ITEM_RE.match(sub_stripped)
                if is_indented and om:
                    checked = om.group(1).lower() == "x"
                    options.append((checked, om.group(2).strip()))
                    i += 1
                    continue
                break
            parsed.append({"label": "選項", "options": options})
            continue

        parsed.append({"label": label, "value": value})
        i += 1

    return parsed, errors


def _check_order(labels_seen, allowed_order, num: str) -> list:
    errors = []
    last_idx = -1
    for label in labels_seen:
        if label not in allowed_order:
            continue
        idx = allowed_order.index(label)
        if idx < last_idx:
            errors.append(f"D{num}：欄位順序錯誤，必須依序是 {' → '.join(allowed_order)}（'{label}' 出現在不對的位置）")
        last_idx = idx
    return errors


def _validate_decision(decision_body: str, num: str, status: str) -> list:
    parsed, errors = _parse_decision_body(decision_body, num)
    labels_seen = [p["label"] for p in parsed]

    allowed = CONFIRMED_FIELD_ORDER if status == STATUS_CONFIRMED else PENDING_FIELD_ORDER
    required = CONFIRMED_REQUIRED if status == STATUS_CONFIRMED else PENDING_REQUIRED
    kind = "✅ 已定案" if status == STATUS_CONFIRMED else "⏳／🚫 待確認或卡住"

    for label in labels_seen:
        if label not in allowed:
            errors.append(f"D{num}（{kind}）：不允許使用欄位 '{label}'，這個狀態只能用 {' / '.join(allowed)}")

    for req in required:
        if req not in labels_seen:
            errors.append(f"D{num}：缺少必要欄位 '{req}'")

    # 除了「選項」可以只出現一次區塊（裡面本來就是清單），其他欄位不得重複
    seen_single = set()
    for label in labels_seen:
        if label == "選項":
            continue
        if label in seen_single:
            errors.append(f"D{num}：欄位 '{label}' 重複")
        seen_single.add(label)

    errors.extend(_check_order(labels_seen, allowed, num))

    for p in parsed:
        if p["label"] == "選項":
            continue
        if len(p.get("value", "")) > MAX_FIELD_LENGTH:
            errors.append(f"D{num} 的 '{p['label']}' 欄位長度為 {len(p['value'])} 字元，超過上限 {MAX_FIELD_LENGTH}")

    if status != STATUS_CONFIRMED:
        option_blocks = [p for p in parsed if p["label"] == "選項"]
        if not any(p["label"] == "選項" for p in parsed):
            errors.append(f"D{num}：{kind}的決策必須有 '選項' 清單，供決策者選擇或補充，不能只寫事件就結束")
        else:
            options = option_blocks[0]["options"]

            if len(options) < MIN_OPTIONS:
                errors.append(f"D{num}：選項數量為 {len(options)}，至少要有 {MIN_OPTIONS} 個供選擇")

            if not any(text.startswith(SUPPLEMENT_LABEL) for _checked, text in options):
                errors.append(f"D{num}：選項清單必須包含一項「{SUPPLEMENT_LABEL}：」，避免變成強迫從既有選項裡選")

            for _checked, text in options:
                if len(text) > MAX_FIELD_LENGTH:
                    errors.append(f"D{num} 的選項 '{text[:30]}...' 過長，超過上限 {MAX_FIELD_LENGTH} 字元")

            checked_count = sum(1 for checked, _text in options if checked)
            if checked_count > 1:
                errors.append(f"D{num}：選項勾選了 {checked_count} 個，一個決策應該只挑一個答案")
            elif checked_count == 1:
                errors.append(
                    f"D{num}：已經勾選了一個選項，但狀態仍是 {status}——"
                    "確定要選這個的話，請把這個決策改成 ✅，並改用「事件／決策／取捨」欄位記錄最終結果，"
                    "不要讓檔案同時說『還沒決定』又『已經勾了答案』"
                )

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

        result.errors.extend(_validate_decision(decision_body, num, emoji))

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
