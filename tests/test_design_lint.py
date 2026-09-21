"""design_lint 的單元測試：固定欄位格式（事件/決策/取捨）+ 摘要交叉比對。"""

import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT))

from lib.linters import design_lint  # noqa: E402

OK_WITH_ALL_FIELDS = """\
---
change: CP-1
---

## ⏳ 待確認（0）

## 決策 (Decisions)

### ✅ D1 — 必填，不採 optional

- **事件**：Jira 寫 optional，但需求方訴求審核當下要看得到理由
- **決策**：採必填，與 Sales 端 Reject Reason 必填對稱
- **取捨**：與 Jira 原文不一致，待需求方確認
"""

OK_WITHOUT_OPTIONAL_TRADEOFF = """\
---
change: CP-1
---

## ⏳ 待確認（0）

## 決策 (Decisions)

### ✅ D1 — DB 欄位 nullable

- **事件**：舊 row 無法回填理由
- **決策**：欄位設為 nullable，不加 NOT NULL
"""

FREE_PROSE_NOT_ALLOWED = """\
---
change: CP-1
---

## ⏳ 待確認（0）

## 決策 (Decisions)

### ✅ D1 — 用段落寫的決策

這是一段自由文字，沒有用固定欄位格式，應該要被擋下來。
"""

MISSING_DECISION_FIELD = """\
---
change: CP-1
---

## ⏳ 待確認（0）

## 決策 (Decisions)

### ✅ D1 — 只有事件沒有決策

- **事件**：發生了什麼事
"""

WRONG_ORDER = """\
---
change: CP-1
---

## ⏳ 待確認（0）

## 決策 (Decisions)

### ✅ D1 — 順序顫倒

- **決策**：先寫決策
- **事件**：後寫事件，順序錯了
"""

DUPLICATE_FIELD = """\
---
change: CP-1
---

## ⏳ 待確認（0）

## 決策 (Decisions)

### ✅ D1 — 欄位重複

- **事件**：第一次
- **事件**：又寫了一次
- **決策**：決策內容
"""

FIELD_TOO_LONG = """\
---
change: CP-1
---

## ⏳ 待確認（0）

## 決策 (Decisions)

### ✅ D1 — 欄位過長

- **事件**：""" + ("很長的內容 " * 40) + """
- **決策**：正常長度
"""

TAKEAWAY_OPTIONAL_OK_MISSING = """\
---
change: CP-1
---

## ⏳ 待確認（1）

- **D1** — 待確認

## 決策 (Decisions)

### ⏳ D1 — 取捨可以省略

- **事件**：發生了什麼事
- **決策**：選了什麼
"""


def test_all_fields_present_passes():
    result = design_lint.lint_text(OK_WITH_ALL_FIELDS, "CP-1")
    assert result.ok, result.errors


def test_optional_tradeoff_can_be_omitted():
    result = design_lint.lint_text(OK_WITHOUT_OPTIONAL_TRADEOFF, "CP-1")
    assert result.ok, result.errors


def test_pending_decision_without_tradeoff_still_passes():
    result = design_lint.lint_text(TAKEAWAY_OPTIONAL_OK_MISSING, "CP-1")
    assert result.ok, result.errors


def test_free_prose_is_rejected():
    """核心規則：決策內文不能是自由段落，只能用固定欄位。"""
    result = design_lint.lint_text(FREE_PROSE_NOT_ALLOWED, "CP-1")
    assert not result.ok
    assert any("不合法的內容" in e for e in result.errors)


def test_missing_required_field_fails():
    result = design_lint.lint_text(MISSING_DECISION_FIELD, "CP-1")
    assert not result.ok
    assert any("缺少必要欄位 '決策'" in e for e in result.errors)


def test_wrong_field_order_fails():
    result = design_lint.lint_text(WRONG_ORDER, "CP-1")
    assert not result.ok
    assert any("順序錯誤" in e for e in result.errors)


def test_duplicate_field_fails():
    result = design_lint.lint_text(DUPLICATE_FIELD, "CP-1")
    assert not result.ok
    assert any("重複" in e for e in result.errors)


def test_field_too_long_fails():
    result = design_lint.lint_text(FIELD_TOO_LONG, "CP-1")
    assert not result.ok
    assert any("超過上限" in e for e in result.errors)


def test_code_fence_fails():
    text = OK_WITH_ALL_FIELDS.replace(
        "- **取捨**：與 Jira 原文不一致，待需求方確認",
        "```\n不該出現\n```",
    )
    result = design_lint.lint_text(text, "CP-1")
    assert not result.ok
    assert any("代碼塊" in e for e in result.errors)


def test_wrong_change_id_fails():
    result = design_lint.lint_text(OK_WITH_ALL_FIELDS.replace("change: CP-1", "change: CP-999"), "CP-1")
    assert not result.ok
    assert any("不一致" in e for e in result.errors)
