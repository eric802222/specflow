"""review_lint 的單元測試：固定欄位格式（位置/問題/處置）、checkbox 選項、摘要交叉比對。

跟 design_lint 共用同一套核心（lib/common/structured_decision.py），這裡的測試
結構刻意跟 test_design_lint.py 對稱，用來驗證同一套機制在不同 schema 下行為一致。
"""

import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT))

from lib.linters import review_lint  # noqa: E402

CONFIRMED_OK = """\
---
change: CP-1055
---

## 🔴 待處理（0）

## Review 發現 (Findings)

### ✅ F1 — 測試 11 沒測到宣稱的邊界

- **位置**：tests/.../FileServiceMimeTest.php:199-205
- **問題**：fixture 實際產生 28 bytes，不是宣稱的 31 bytes，真正邊界沒測到
- **處置**：用 11a/11b 兩條取代，反向驗證確認真的 load-bearing
"""

PENDING_OK = """\
---
change: CP-1055
---

## 🔴 待處理（1）

- **F1** — N3 32-bit 相容性

## Review 發現 (Findings)

### ⏳ F1 — 32-bit PHP 上 unpack 行為不同

- **位置**：app/Services/FileService.php:190
- **問題**：32-bit 環境對 0xFFFFFFFF 會回負數，跟 64-bit 不同
- **選項**：
  - [ ] 補上型別轉換防呆
  - [ ] 不修，只記錄（prod 是 64-bit）
  - [ ] 其他補充：
"""

CONFIRMED_CANNOT_USE_OPTIONS = """\
---
change: CP-1055
---

## 🔴 待處理（0）

## Review 發現 (Findings)

### ✅ F1 — 已結案卻還留著選項

- **位置**：x
- **問題**：x
- **選項**：
  - [ ] 選項一
  - [ ] 選項二
"""

PENDING_CANNOT_USE_DISPOSITION = """\
---
change: CP-1055
---

## 🔴 待處理（1）

- **F1** — 卡住

## Review 發現 (Findings)

### ⏳ F1 — 還沒結案卻寫了處置

- **位置**：x
- **問題**：x
- **處置**：其實已經處理好了
"""

MISSING_LOCATION = """\
---
change: CP-1055
---

## 🔴 待處理（0）

## Review 發現 (Findings)

### ✅ F1 — 缺少位置欄位

- **問題**：x
- **處置**：x
"""

CHECKED_BUT_STATUS_UNCHANGED = """\
---
change: CP-1055
---

## 🔴 待處理（1）

- **F1** — 卡住

## Review 發現 (Findings)

### ⏳ F1 — 已經勾了但狀態沒改

- **位置**：x
- **問題**：x
- **選項**：
  - [x] 補上型別轉換防呆
  - [ ] 不修，只記錄
  - [ ] 其他補充：
"""


def test_confirmed_finding_passes():
    result = review_lint.lint_text(CONFIRMED_OK, "CP-1055")
    assert result.ok, result.errors


def test_pending_finding_with_options_passes():
    result = review_lint.lint_text(PENDING_OK, "CP-1055")
    assert result.ok, result.errors


def test_confirmed_finding_cannot_use_options_field():
    result = review_lint.lint_text(CONFIRMED_CANNOT_USE_OPTIONS, "CP-1055")
    assert not result.ok
    assert any("不允許使用欄位 '選項'" in e for e in result.errors)


def test_pending_finding_cannot_use_disposition_field():
    """核心規則：還沒結案就不該假裝已經處理好，處置欄位（自由文字版）只留給 ✅ 用。"""
    result = review_lint.lint_text(PENDING_CANNOT_USE_DISPOSITION, "CP-1055")
    assert not result.ok
    assert any("不允許使用欄位 '處置'" in e for e in result.errors)


def test_confirmed_finding_requires_location():
    result = review_lint.lint_text(MISSING_LOCATION, "CP-1055")
    assert not result.ok
    assert any("缺少必要欄位 '位置'" in e for e in result.errors)


def test_checked_option_but_status_still_pending_fails():
    """回歸測試：勾了一個選項但狀態還是 ⏳，要被擋下來——這是這次設計的核心訴求，
    避免 MR review 討論串「看起來已經處理但狀態沒更新」的問題重演在 review.md 裡。"""
    result = review_lint.lint_text(CHECKED_BUT_STATUS_UNCHANGED, "CP-1055")
    assert not result.ok
    assert any("已經勾選了一個選項，但狀態仍是" in e for e in result.errors)


def test_wrong_change_id_fails():
    result = review_lint.lint_text(CONFIRMED_OK.replace("change: CP-1055", "change: CP-999"), "CP-1055")
    assert not result.ok
    assert any("不一致" in e for e in result.errors)


def test_code_fence_fails():
    text = CONFIRMED_OK + "\n```\n不該出現\n```\n"
    result = review_lint.lint_text(text, "CP-1055")
    assert not result.ok
    assert any("代碼塊" in e for e in result.errors)


def test_design_and_review_share_same_core_module():
    """確認兩個 linter 真的走同一套核心，不是各自複製貼上一份——如果之後改共用
    模組的行為，兩邊要同步跟著變，不能只改到一邊。"""
    from lib.linters import design_lint
    from lib.common import structured_decision

    assert design_lint.lint_structured_text is structured_decision.lint_structured_text
    assert review_lint.lint_structured_text is structured_decision.lint_structured_text
