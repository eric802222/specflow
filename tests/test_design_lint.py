"""design_lint 的單元測試：決策狀態標記、摘要與內文交叉比對。"""

import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT))

from lib.linters import design_lint  # noqa: E402

OK_NO_PENDING = """\
---
change: CP-1
---

## ⏳ 待確認（0）

## 決策 (Decisions)

### ✅ D1 — 必填，不採 optional

理由：跟 Sales 端 Reject Reason 必填對稱，且審核當下要看得到理由。
"""

OK_WITH_PENDING = """\
---
change: CP-1
---

## ⏳ 待確認（1）

- **D1** — 必填 vs optional（卡在 Q1：需向需求方確認）

## 決策 (Decisions)

### ⏳ D1 — 必填，不採 optional

Jira 寫 optional，但與 Sales 端對稱考量下先採必填，待確認共識。

### ✅ D2 — DB 欄位 nullable

舊 row 無法回填，加 NOT NULL 會讓 migration 跑不動。
"""

MISSING_SUMMARY = """\
---
change: CP-1
---

## 決策 (Decisions)

### ⏳ D1 — 必填，不採 optional

還沒定案。
"""

SUMMARY_COUNT_WRONG = """\
---
change: CP-1
---

## ⏳ 待確認（2）

- **D1** — 卡住

## 決策 (Decisions)

### ⏳ D1 — 必填，不採 optional

還沒定案。
"""

SUMMARY_STALE_EXTRA = """\
---
change: CP-1
---

## ⏳ 待確認（1）

- **D1** — 卡住

## 決策 (Decisions)

### ✅ D1 — 必填，不採 optional

已經定案了，但摘要忘記拿掉。
"""

SUMMARY_MISSING_ENTRY = """\
---
change: CP-1
---

## ⏳ 待確認（1）

- **D1** — 卡住

## 決策 (Decisions)

### ⏳ D1 — 必填，不採 optional

還沒定案。

### ⏳ D2 — 另一個還沒定案的決策

也還沒定案，但摘要沒列出來。
"""

DUPLICATE_ID = """\
---
change: CP-1
---

## ⏳ 待確認（0）

## 決策 (Decisions)

### ✅ D1 — 第一次用 D1

內容。

### ✅ D1 — 又用了一次 D1

編號重複了。
"""

TOO_LONG_DECISION = (
    """\
---
change: CP-1
---

## ⏳ 待確認（0）

## 決策 (Decisions)

### ✅ D1 — 過長的決策

"""
    + "\n".join(f"- 第 {i} 行" for i in range(1, 20))
)

HAS_CODE_FENCE = """\
---
change: CP-1
---

## ⏳ 待確認（0）

## 決策 (Decisions)

### ✅ D1 — 含代碼塊

```
不該出現
```
"""

WRONG_CHANGE_ID = """\
---
change: CP-999-other
---

## ⏳ 待確認（0）

## 決策 (Decisions)

### ✅ D1 — 內容

理由。
"""


def test_no_pending_passes():
    result = design_lint.lint_text(OK_NO_PENDING, "CP-1")
    assert result.ok, result.errors


def test_with_pending_and_matching_summary_passes():
    result = design_lint.lint_text(OK_WITH_PENDING, "CP-1")
    assert result.ok, result.errors


def test_missing_summary_when_pending_exists_fails():
    result = design_lint.lint_text(MISSING_SUMMARY, "CP-1")
    assert not result.ok
    assert any("摘要區塊" in e for e in result.errors)


def test_summary_count_mismatch_fails():
    result = design_lint.lint_text(SUMMARY_COUNT_WRONG, "CP-1")
    assert not result.ok
    assert any("宣告 2 個待確認" in e for e in result.errors)


def test_stale_summary_entry_fails():
    """回歸測試：決策已經 ✅ 了，但摘要忘記拿掉——這正是要防的漂移。"""
    result = design_lint.lint_text(SUMMARY_STALE_EXTRA, "CP-1")
    assert not result.ok
    assert any("摘要過期了" in e for e in result.errors)


def test_missing_summary_entry_fails():
    result = design_lint.lint_text(SUMMARY_MISSING_ENTRY, "CP-1")
    assert not result.ok
    assert any("摘要漏更新了" in e for e in result.errors)


def test_duplicate_decision_id_fails():
    result = design_lint.lint_text(DUPLICATE_ID, "CP-1")
    assert not result.ok
    assert any("編號重複" in e for e in result.errors)


def test_decision_too_long_fails():
    result = design_lint.lint_text(TOO_LONG_DECISION, "CP-1")
    assert not result.ok
    assert any("超過單一決策上限 15 行" in e for e in result.errors)


def test_code_fence_fails():
    result = design_lint.lint_text(HAS_CODE_FENCE, "CP-1")
    assert not result.ok
    assert any("代碼塊" in e for e in result.errors)


def test_wrong_change_id_fails():
    result = design_lint.lint_text(WRONG_CHANGE_ID, "CP-1")
    assert not result.ok
    assert any("不一致" in e for e in result.errors)
