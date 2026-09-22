"""story_lint 的單元測試：Given/When/Then 需求意圖格式的結構檢查。"""

import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT))

from lib.linters import story_lint  # noqa: E402

VALID = """\
---
name: "Trade-In 送審流程"
type: story
status: confirm
external_key: INTCUSSS-700
refs:
  - https://qnap-jira.qnap.com.tw/browse/INTCUSSS-700
goal: 業務主管審核時看不到申請理由，需要補上
stories:
  - id: trade_in_submit_with_reason
    given: 客服在 myRMA 送出 Trade-In 申請
    when: 填寫申請理由並送出
    then: 審核頁面能看到這次申請的理由
    children:
      - id: trade_in_submit_with_reason.reason_too_short
        given: 客服在送出申請時
        when: 理由字數不足 20 字
        then: 系統擋下並提示字數不足
  - id: reviewer_sees_reason
    given: 業務主管在 Sales Portal 審核頁
    when: 打開一筆 Trade-In 申請
    then: 看得到申請理由欄位
---
"""


def test_valid_story_passes():
    result = story_lint.lint_text(VALID)
    assert result.ok, result.errors


def test_missing_required_frontmatter_field_fails():
    text = VALID.replace("goal: 業務主管審核時看不到申請理由，需要補上\n", "")
    result = story_lint.lint_text(text)
    assert not result.ok
    assert any("goal" in e for e in result.errors)


def test_wrong_type_fails():
    text = VALID.replace("type: story", "type: proposal")
    result = story_lint.lint_text(text)
    assert not result.ok
    assert any("type 必須是" in e for e in result.errors)


def test_invalid_status_fails():
    text = VALID.replace("status: confirm", "status: in_progress")
    result = story_lint.lint_text(text)
    assert not result.ok
    assert any("status 必須是" in e for e in result.errors)


def test_valid_statuses_all_pass():
    for status in ("draft", "confirm", "living"):
        text = VALID.replace("status: confirm", f"status: {status}")
        result = story_lint.lint_text(text)
        assert result.ok, (status, result.errors)


def test_missing_story_id_fails():
    text = """\
---
name: test
type: story
status: draft
goal: 測試
stories:
  - given: a
    when: b
    then: c
---
"""
    result = story_lint.lint_text(text)
    assert not result.ok
    assert any("id" in e for e in result.errors)


def test_duplicate_story_id_fails():
    text = """\
---
name: test
type: story
status: draft
goal: 測試
stories:
  - id: dup
    given: a
    when: b
    then: c
  - id: dup
    given: d
    when: e
    then: f
---
"""
    result = story_lint.lint_text(text)
    assert not result.ok
    assert any("重複" in e for e in result.errors)


def test_non_snake_case_id_fails():
    text = """\
---
name: test
type: story
status: draft
goal: 測試
stories:
  - id: NotSnakeCase
    given: a
    when: b
    then: c
---
"""
    result = story_lint.lint_text(text)
    assert not result.ok
    assert any("snake_case" in e for e in result.errors)


def test_child_id_without_dot_notation_fails():
    text = """\
---
name: test
type: story
status: draft
goal: 測試
stories:
  - id: parent_story
    given: a
    when: b
    then: c
    children:
      - id: not_prefixed_correctly
        given: a
        when: b
        then: c
---
"""
    result = story_lint.lint_text(text)
    assert not result.ok
    assert any("dot-notation" in e for e in result.errors)


def test_child_id_with_correct_dot_notation_passes():
    text = """\
---
name: test
type: story
status: draft
goal: 測試
stories:
  - id: parent_story
    given: a
    when: b
    then: c
    children:
      - id: parent_story.edge_case
        given: a
        when: b
        then: c
---
"""
    result = story_lint.lint_text(text)
    assert result.ok, result.errors


def test_static_method_call_syntax_fails():
    text = """\
---
name: test
type: story
status: draft
goal: 測試
stories:
  - id: x
    given: 使用者
    when: 呼叫 SubmitToSalesPortalJob::dispatch() 之後
    then: 收到通知
---
"""
    result = story_lint.lint_text(text)
    assert not result.ok
    assert any("靜態方法呼叫" in e for e in result.errors)
    assert any("函式呼叫" in e for e in result.errors)


def test_function_call_syntax_in_goal_fails():
    text = """\
---
name: test
type: story
status: draft
goal: 呼叫 getCase() 之後應該要通知客服
stories:
  - id: x
    given: a
    when: b
    then: c
---
"""
    result = story_lint.lint_text(text)
    assert not result.ok
    assert any("goal" in e and "函式呼叫" in e for e in result.errors)


def test_missing_given_when_then_fails():
    text = """\
---
name: test
type: story
status: draft
goal: 測試
stories:
  - id: x
    given: a
    then: c
---
"""
    result = story_lint.lint_text(text)
    assert not result.ok
    assert any("when" in e for e in result.errors)


def test_code_fence_fails():
    text = VALID + "\n```\n不該出現\n```\n"
    result = story_lint.lint_text(text)
    assert not result.ok
    assert any("代碼塊" in e for e in result.errors)


def test_empty_stories_list_fails():
    text = """\
---
name: test
type: story
status: draft
goal: 測試
stories: []
---
"""
    result = story_lint.lint_text(text)
    assert not result.ok
    assert any("stories" in e for e in result.errors)


def test_children_only_allowed_on_top_level_story():
    """回歸測試：children 的 children 不支援——巢狀太深會讓 dot-notation
    跟渲染邏輯都變複雜，刻意只開放一層。"""
    text = """\
---
name: test
type: story
status: draft
goal: 測試
stories:
  - id: parent_story
    given: a
    when: b
    then: c
    children:
      - id: parent_story.child_one
        given: a
        when: b
        then: c
        children:
          - id: parent_story.child_one.grandchild
            given: a
            when: b
            then: c
---
"""
    result = story_lint.lint_text(text)
    assert not result.ok
    assert any("不支援巢狀 children 的 children" in e for e in result.errors)


def test_refs_must_be_a_list():
    text = VALID.replace(
        "refs:\n  - https://qnap-jira.qnap.com.tw/browse/INTCUSSS-700\n",
        "refs: https://qnap-jira.qnap.com.tw/browse/INTCUSSS-700\n",
    )
    result = story_lint.lint_text(text)
    assert not result.ok
    assert any("refs" in e for e in result.errors)
