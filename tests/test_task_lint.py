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
