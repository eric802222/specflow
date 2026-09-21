"""design_lint 的單元測試：固定欄位格式、checkbox 選項、摘要交叉比對。"""

import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT))

from lib.linters import design_lint  # noqa: E402

CONFIRMED_OK = """\
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

PENDING_OK = """\
---
change: CP-1
---

## ⏳ 待確認（1）

- **D1** — 上限要多少

## 決策 (Decisions)

### ⏳ D1 — 上限要多少

- **事件**：業務反應理由太長難以快速瀏覽
- **選項**：
  - [ ] 設定最長長度
  - [ ] 禁止使用自定義語法
  - [ ] 其他補充：
"""

CONFIRMED_CANNOT_USE_OPTIONS = """\
---
change: CP-1
---

## ⏳ 待確認（0）

## 決策 (Decisions)

### ✅ D1 — 已定案卻還留著選項

- **事件**：發生了什麼事
- **選項**：
  - [ ] 選項一
  - [ ] 選項二
"""

PENDING_CANNOT_USE_DECISION = """\
---
change: CP-1
---

## ⏳ 待確認（1）

- **D1** — 卡住

## 決策 (Decisions)

### ⏳ D1 — 還沒定案卻寫了決策

- **事件**：發生了什麼事
- **決策**：其實已經想好了
"""

PENDING_TOO_FEW_OPTIONS = """\
---
change: CP-1
---

## ⏳ 待確認（1）

- **D1** — 卡住

## 決策 (Decisions)

### ⏳ D1 — 只有一個選項

- **事件**：發生了什麼事
- **選項**：
  - [ ] 唯一的選項
"""

PENDING_MISSING_SUPPLEMENT = """\
---
change: CP-1
---

## ⏳ 待確認（1）

- **D1** — 卡住

## 決策 (Decisions)

### ⏳ D1 — 沒有其他補充選項

- **事件**：發生了什麼事
- **選項**：
  - [ ] 選項一
  - [ ] 選項二
"""

PENDING_MULTIPLE_CHECKED = """\
---
change: CP-1
---

## ⏳ 待確認（1）

- **D1** — 卡住

## 決策 (Decisions)

### ⏳ D1 — 一次勾兩個

- **事件**：發生了什麼事
- **選項**：
  - [x] 選項一
  - [x] 選項二
  - [ ] 其他補充：
"""

PENDING_CHECKED_BUT_STATUS_UNCHANGED = """\
---
change: CP-1
---

## ⏳ 待確認（1）

- **D1** — 卡住

## 決策 (Decisions)

### ⏳ D1 — 已經勾了但狀態沒改

- **事件**：發生了什麼事
- **選項**：
  - [x] 選項一
  - [ ] 選項二
  - [ ] 其他補充：
"""

PENDING_MISSING_OPTIONS_BLOCK = """\
---
change: CP-1
---

## ⏳ 待確認（1）

- **D1** — 卡住

## 決策 (Decisions)

### ⏳ D1 — 完全沒有選項

- **事件**：發生了什麼事
"""


def test_confirmed_decision_passes():
    result = design_lint.lint_text(CONFIRMED_OK, "CP-1")
    assert result.ok, result.errors


def test_pending_decision_with_options_passes():
    result = design_lint.lint_text(PENDING_OK, "CP-1")
    assert result.ok, result.errors


def test_confirmed_decision_cannot_use_options_field():
    result = design_lint.lint_text(CONFIRMED_CANNOT_USE_OPTIONS, "CP-1")
    assert not result.ok
    assert any("不允許使用欄位 '選項'" in e for e in result.errors)


def test_pending_decision_cannot_use_decision_field():
    """核心規則：還沒定案就不該假裝有答案，決策欄位只留給 ✅ 用。"""
    result = design_lint.lint_text(PENDING_CANNOT_USE_DECISION, "CP-1")
    assert not result.ok
    assert any("不允許使用欄位 '決策'" in e for e in result.errors)


def test_pending_decision_requires_min_options():
    result = design_lint.lint_text(PENDING_TOO_FEW_OPTIONS, "CP-1")
    assert not result.ok
    assert any("至少要有 2 個" in e for e in result.errors)


def test_pending_decision_requires_supplement_option():
    result = design_lint.lint_text(PENDING_MISSING_SUPPLEMENT, "CP-1")
    assert not result.ok
    assert any("其他補充" in e for e in result.errors)


def test_pending_decision_missing_options_block_fails():
    result = design_lint.lint_text(PENDING_MISSING_OPTIONS_BLOCK, "CP-1")
    assert not result.ok
    assert any("必須有 '選項' 清單" in e for e in result.errors)


def test_multiple_checked_options_fails():
    result = design_lint.lint_text(PENDING_MULTIPLE_CHECKED, "CP-1")
    assert not result.ok
    assert any("勾選了 2 個" in e for e in result.errors)


def test_checked_option_but_status_still_pending_fails():
    """回歸測試（使用者明確要求）：勾了一個選項但狀態還是 ⏳/🚫，要被擋下來，
    不能讓檔案同時說「還沒決定」又「已經勾了答案」這種矛盾狀態存在。"""
    result = design_lint.lint_text(PENDING_CHECKED_BUT_STATUS_UNCHANGED, "CP-1")
    assert not result.ok
    assert any("已經勾選了一個選項，但狀態仍是" in e for e in result.errors)


def test_zero_checked_options_is_fine_while_pending():
    result = design_lint.lint_text(PENDING_OK, "CP-1")
    assert result.ok, result.errors


def test_wrong_change_id_fails():
    result = design_lint.lint_text(CONFIRMED_OK.replace("change: CP-1", "change: CP-999"), "CP-1")
    assert not result.ok
    assert any("不一致" in e for e in result.errors)


def test_code_fence_fails():
    text = CONFIRMED_OK + "\n```\n不該出現\n```\n"
    result = design_lint.lint_text(text, "CP-1")
    assert not result.ok
    assert any("代碼塊" in e for e in result.errors)
