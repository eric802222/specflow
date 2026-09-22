"""story.md 的結構檢查（Given/When/Then 需求意圖格式）。

跟 design.md／review.md 不一樣，story 不是「固定欄位 + 自由文字段落」的 Markdown
body 格式，是整份內容都活在 YAML frontmatter 裡——name/type/status/goal/stories
一次到位，body 通常留空或只放輔助說明。這裡不重用 structured_decision.py 那套
（heading + field-line 解析器），是因為 story 的形狀根本不同：一份檔案裝多筆
story，每筆自己有巢狀 children，不是「一個檔案 = 一串平鋪的決策清單」。

核心規則：
  1. 頂層必要欄位：name / type（必須是 "story"）/ status（draft|confirm|living）
     / goal / stories（至少 1 筆）
  2. 每筆 story 必要欄位：id（同檔案內唯一，snake_case）/ given / when / then
  3. children（可選）：id 必須是 `<所屬 story 的 id>.<child-id>` 這種 dot-notation，
     且同一份 story 底下的 children id 彼此不重複
  4. given/when/then/goal 裡禁止出現看起來像實作細節的語法：
     - `::`（PHP 靜態呼叫語法，例如 SomeClass::method）
     - `word()`（函式呼叫語法）
     這兩個是語法層面、可以精確判定的信號；「不準提框架 API／DB 欄位名稱」這種
     語意層面的禁止事項太模糊、容易誤判，這裡不做機械檢查，留給撰寫者跟
read-me 說明自己把關——跟 specflow 一路的立場一致：管格式，不管內容。
  5. 嚴禁代碼塊標記（```）

用法：
    python3 story_lint.py <story.md>
"""

from __future__ import annotations

import re
import sys
from dataclasses import dataclass, field
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(REPO_ROOT))

from lib.common import frontmatter as fm  # noqa: E402

CODE_FENCE = "```"
VALID_STATUSES = {"draft", "confirm", "living"}
ID_RE = re.compile(r"^[a-z][a-z0-9_]*$")

# 語法層面、可以精確判定的「看起來像實作細節」信號——不做語意判斷，只抓明確的
# 程式碼語法特徵，降低誤判機率。
_STATIC_CALL_RE = re.compile(r"\w+::\w+")
_FUNCTION_CALL_RE = re.compile(r"\b[a-zA-Z_]\w*\(\)")


@dataclass
class LintResult:
    path: Path
    errors: list = field(default_factory=list)

    @property
    def ok(self) -> bool:
        return not self.errors


def _check_implementation_leak(text: str, where: str) -> list:
    """檢查一段文字裡有沒有明確的程式碼語法信號（不做語意層面的框架/DB 欄位判斷）。"""
    errors = []
    if _STATIC_CALL_RE.search(text):
        errors.append(f"{where}：出現看起來像靜態方法呼叫的語法（Class::method）— {text!r}")
    if _FUNCTION_CALL_RE.search(text):
        errors.append(f"{where}：出現看起來像函式呼叫的語法（word()）— {text!r}")
    return errors


def _validate_story_entry(entry, index: int, seen_ids: set, is_child: bool, parent_id: str = None) -> list:
    errors = []
    label = f"stories[{index}]" if not is_child else f"children of '{parent_id}'[{index}]"

    if not isinstance(entry, dict):
        return [f"{label}：每一筆必須是一個物件（id/given/when/then）"]

    entry_id = entry.get("id")
    if not entry_id:
        errors.append(f"{label}：缺少必要欄位 'id'")
    elif is_child:
        expected_prefix = f"{parent_id}."
        if not str(entry_id).startswith(expected_prefix):
            errors.append(
                f"{label}：id '{entry_id}' 必須是 dot-notation '{expected_prefix}<child-id>' 的形式"
            )
        if entry_id in seen_ids:
            errors.append(f"{label}：id '{entry_id}' 重複")
        seen_ids.add(entry_id)
    else:
        if not ID_RE.match(str(entry_id)):
            errors.append(f"{label}：id '{entry_id}' 必須是 snake_case（小寫字母/數字/底線，字母開頭）")
        if entry_id in seen_ids:
            errors.append(f"{label}：id '{entry_id}' 重複")
        seen_ids.add(entry_id)

    for req in ("given", "when", "then"):
        value = entry.get(req)
        if not value:
            errors.append(f"{label}（id: {entry_id}）：缺少必要欄位 '{req}'")
        elif isinstance(value, str):
            errors.extend(_check_implementation_leak(value, f"{label}.{req}"))

    children = entry.get("children")
    if children is not None:
        if is_child:
            errors.append(f"{label}：children 只能出現在頂層 story，不支援巢狀 children 的 children")
        elif not isinstance(children, list) or not children:
            errors.append(f"{label}：children 存在時必須是非空清單")
        else:
            for i, child in enumerate(children):
                errors.extend(_validate_story_entry(child, i, seen_ids, is_child=True, parent_id=entry_id))

    return errors


def lint_text(text: str, path: Path = None) -> LintResult:
    result = LintResult(path=path or Path("<memory>"))

    if CODE_FENCE in text:
        result.errors.append(f"嚴禁出現代碼塊標記（{CODE_FENCE}）")

    data, _body, error = fm.load_frontmatter_data(text)
    if error:
        result.errors.append(error)
        return result
    if not isinstance(data, dict):
        result.errors.append("frontmatter 必須是一個 YAML mapping")
        return result

    for req in ("name", "type", "status", "goal", "stories"):
        if req not in data or data.get(req) in (None, "", []):
            result.errors.append(f"frontmatter 缺少必要欄位：{req}")

    if data.get("type") not in (None, "story"):
        result.errors.append(f"type 必須是 'story'，目前是 {data.get('type')!r}")

    status = data.get("status")
    if status is not None and status not in VALID_STATUSES:
        result.errors.append(f"status 必須是 {sorted(VALID_STATUSES)} 其中之一，目前是 {status!r}")

    goal = data.get("goal")
    if isinstance(goal, str):
        result.errors.extend(_check_implementation_leak(goal, "goal"))

    stories = data.get("stories")
    if isinstance(stories, list):
        seen_ids = set()
        for i, entry in enumerate(stories):
            result.errors.extend(_validate_story_entry(entry, i, seen_ids, is_child=False))
    elif stories is not None:
        result.errors.append("stories 必須是一個清單")

    refs = data.get("refs")
    if refs is not None and not isinstance(refs, list):
        result.errors.append("refs 存在時必須是一個清單")

    return result


def lint_file(path: Path) -> LintResult:
    text = path.read_text(encoding="utf-8")
    return lint_text(text, path=path)


def main(argv=None) -> int:
    argv = argv if argv is not None else sys.argv[1:]
    if not argv:
        print("用法: story_lint.py <story.md>", file=sys.stderr)
        return 2

    path = Path(argv[0])
    if not path.exists():
        print(f"✗ {path}: 檔案不存在")
        return 1

    result = lint_file(path)
    if result.ok:
        print(f"✓ {path}")
        return 0

    print(f"✗ {path}")
    for err in result.errors:
        print(f"  - {err}")
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
