"""task_lint 的單元測試。"""

import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT))

from lib.linters import task_lint  # noqa: E402

OK_TASKS = """\
---
change: CP-153-discount-reason-visibility
---

- [ ] add-reason-field: discount_requests 表與 DTO 加上 reason_note 欄位 (touches: db/schema.dbml, api/main.tsp)
- [x] approval-ui-reason-display: 核准頁面顯示理由全文 (touches: ui/pages/discount-approval.wf.yaml)
"""

WRONG_CHANGE_ID = """\
---
change: CP-999-other
---

- [ ] task-a: 描述 (touches: x)
"""

MISSING_FRONTMATTER = """\
- [ ] task-a: 描述 (touches: x)
"""

BAD_LINE_FORMAT = """\
---
change: CP-153-discount-reason-visibility
---

- task-a 沒有 checkbox 格式
"""

NESTED_SUBITEM = """\
---
change: CP-153-discount-reason-visibility
---

- [ ] task-a: 描述 (touches: x)
  - [ ] 巢狀子項目不允許
"""

HAS_CODE_FENCE = """\
---
change: CP-153-discount-reason-visibility
---

- [ ] task-a: 描述 (touches: x)

```
code
```
"""

DUPLICATE_ID = """\
---
change: CP-153-discount-reason-visibility
---

- [ ] task-a: 描述一 (touches: x)
- [ ] task-a: 描述二 (touches: y)
"""

TOO_MANY_TASKS = (
    """\
---
change: CP-153-discount-reason-visibility
---

"""
    + "\n".join(f"- [ ] task-{i}: 描述 (touches: x)" for i in range(1, 20))
)


def test_ok_passes():
    result = task_lint.lint_text(OK_TASKS, "CP-153-discount-reason-visibility")
    assert result.ok, result.errors
    assert result.task_ids == ["add-reason-field", "approval-ui-reason-display"]


def test_wrong_change_id_fails():
    result = task_lint.lint_text(WRONG_CHANGE_ID, "CP-153-discount-reason-visibility")
    assert not result.ok
    assert any("不一致" in e for e in result.errors)


def test_missing_frontmatter_fails():
    result = task_lint.lint_text(MISSING_FRONTMATTER, "CP-153-discount-reason-visibility")
    assert not result.ok


def test_bad_line_format_fails():
    result = task_lint.lint_text(BAD_LINE_FORMAT, "CP-153-discount-reason-visibility")
    assert not result.ok
    assert any("格式不符" in e for e in result.errors)


def test_nested_subitem_fails():
    result = task_lint.lint_text(NESTED_SUBITEM, "CP-153-discount-reason-visibility")
    assert not result.ok
    assert any("巢狀" in e for e in result.errors)


def test_code_fence_fails():
    result = task_lint.lint_text(HAS_CODE_FENCE, "CP-153-discount-reason-visibility")
    assert not result.ok
    assert any("代碼塊" in e for e in result.errors)


def test_duplicate_id_fails():
    result = task_lint.lint_text(DUPLICATE_ID, "CP-153-discount-reason-visibility")
    assert not result.ok
    assert any("重複" in e for e in result.errors)


def test_too_many_tasks_fails():
    result = task_lint.lint_text(TOO_MANY_TASKS, "CP-153-discount-reason-visibility")
    assert not result.ok
    assert any("超過上限" in e for e in result.errors)


def test_description_can_contain_parentheses():
    """回歸測試：desc 欄位原本用 [^(]+? 排除所有括號，導致 exists()/logCase()
    這類自然的 PHP 呼叫寫法直接被判定格式不符，而且錯誤訊息完全沒點名是括號
    害的。改成用 '(touches: ...)' 這個字面字串當分界，desc 本身可以含括號。"""
    text = (
        "---\nchange: CP-1\n---\n\n"
        "- [ ] verify-guard: 以 exists() 守衛 (touches: x)\n"
        "- [x] log-case: 呼叫 logCase() 記錄\n"
    )
    result = task_lint.lint_text(text, "CP-1")
    assert result.ok, result.errors
    assert "verify-guard" in result.task_ids
    assert "log-case" in result.task_ids


def test_sentinel_placeholder_task_id_is_rejected():
    """回歸測試（issue #13）：init 自動產生的 tasks.md 有一行範本佔位範例，
    格式上完全合法，之前會悄悄通過整條生命週期而沒人發現根本沒編輯過。
    現在這個特定 task-id（範本產生的 sentinel）要被明確擋下。"""
    text = (
        "---\nchange: CP-1\n---\n\n"
        "- [ ] replace-me: 刪掉這行，換成真正的第一個 task (touches: 實際會改到的檔案路徑)\n"
    )
    result = task_lint.lint_text(text, "CP-1")
    assert not result.ok
    assert any("未編輯的佔位內容" in e for e in result.errors)


def test_task_id_similar_to_sentinel_but_not_exact_is_fine():
    """只擋精確符合 sentinel 的 task-id，不要誤傷剛好取名相近的真實 task。"""
    text = (
        "---\nchange: CP-1\n---\n\n"
        "- [ ] replace-me-config-value: 把設定檔裡的預留值換成真值 (touches: config.yaml)\n"
    )
    result = task_lint.lint_text(text, "CP-1")
    assert result.ok, result.errors
