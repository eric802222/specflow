"""proposal_lint 的單元測試：分別驗證合規案例與各類違規案例。"""

import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT))

from lib.linters import proposal_lint  # noqa: E402

COMPLIANT = """\
---
id: PROP-0001
title: "測試用合規提案"
impact_surface:
  - .spec/db/schema.dbml
---

## 1. 為什麼 (Why)

因為要測試 linter。

## 2. 目標 (Goals)

- 讓合規案例通過

## 3. 非目標 (Non-Goals)

- 不處理跟本測試無關的事

## 4. 影響範圍 (Impact Surface)

- db: deals 表
"""

MISSING_FRONTMATTER_KEY = """\
---
id: PROP-0002
title: "缺少 impact_surface"
---

## 3. 非目標 (Non-Goals)

- 無
"""

HAS_CODE_FENCE = """\
---
id: PROP-0003
title: "含代碼塊"
impact_surface:
  - x
---

## 3. 非目標 (Non-Goals)

```
print("不該出現")
```
"""

MISSING_NON_GOALS_SECTION = """\
---
id: PROP-0004
title: "缺少非目標區塊"
impact_surface:
  - x
---

## 1. 為什麼 (Why)

沒有第三節。
"""

TOO_MANY_LINES = (
    """\
---
id: PROP-0005
title: "正文過長"
impact_surface:
  - x
---

## 3. 非目標 (Non-Goals)

"""
    + "\n".join(f"- 第 {i} 行" for i in range(1, 40))
)

NO_FRONTMATTER = """\
## 3. 非目標 (Non-Goals)

沒有 frontmatter。
"""


def test_compliant_passes():
    result = proposal_lint.lint_text(COMPLIANT)
    assert result.ok, result.errors


def test_missing_frontmatter_key_fails():
    result = proposal_lint.lint_text(MISSING_FRONTMATTER_KEY)
    assert not result.ok
    assert any("impact_surface" in e for e in result.errors)


def test_code_fence_fails():
    result = proposal_lint.lint_text(HAS_CODE_FENCE)
    assert not result.ok
    assert any("代碼塊" in e for e in result.errors)


def test_missing_non_goals_section_fails():
    result = proposal_lint.lint_text(MISSING_NON_GOALS_SECTION)
    assert not result.ok
    assert any("非目標" in e for e in result.errors)


def test_too_many_lines_fails():
    result = proposal_lint.lint_text(TOO_MANY_LINES)
    assert not result.ok
    assert any("超過上限" in e for e in result.errors)


def test_no_frontmatter_fails():
    result = proposal_lint.lint_text(NO_FRONTMATTER)
    assert not result.ok
    assert any("frontmatter" in e for e in result.errors)


BUGFIX_OK = """\
---
id: PROP-0006
title: "驗證邊界漏判"
impact_surface:
  - x
type: bugfix
---

## 壞在哪 (Symptom)

輸入剛好 100 字元時驗證沒擋下來。

## 怎麼修 (Fix)

邊界判斷用 > 改成 >=。
"""

HOTFIX_OK = """\
---
id: PROP-0007
title: "資料庫連線池爆掉"
impact_surface:
  - x
type: hotfix
---

## 症狀 (Symptom)

連線數衝到上限，API 全部逾時。
"""

BUGFIX_TOO_LONG = (
    """\
---
id: PROP-0008
title: "過長的 bugfix"
impact_surface:
  - x
type: bugfix
---

## 壞在哪 (Symptom)

"""
    + "\n".join(f"- 第 {i} 行" for i in range(1, 20))
)

INVALID_TYPE = """\
---
id: PROP-0009
title: "type 打錯字"
impact_surface:
  - x
type: not_a_real_type
---

## 3. 非目標 (Non-Goals)

- x
"""


def test_bugfix_type_uses_relaxed_rules():
    result = proposal_lint.lint_text(BUGFIX_OK)
    assert result.ok, result.errors  # 不要求非目標區塊，行數上限也不是 35


def test_hotfix_type_uses_leanest_rules():
    result = proposal_lint.lint_text(HOTFIX_OK)
    assert result.ok, result.errors


def test_bugfix_still_has_its_own_line_limit():
    result = proposal_lint.lint_text(BUGFIX_TOO_LONG)
    assert not result.ok
    assert any("超過上限 15 行" in e for e in result.errors)


def test_invalid_type_value_is_flagged():
    result = proposal_lint.lint_text(INVALID_TYPE)
    assert not result.ok
    assert any("type 值不合法" in e for e in result.errors)
