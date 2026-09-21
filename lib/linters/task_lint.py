"""tasks.md 的結構檢查（poka-yoke）。

規則：
  1. Frontmatter 必須有 `change` 欄位，且值要等於外部傳入的 change_id
     （change_id 通常就是 changes/<id>/ 的資料夾名稱）
  2. 正文每一個非空行都必須符合：
         - [ ] <task-id>: <一句話描述> (touches: <file1>, <file2>, ...)
     <task-id> 只能是 kebab-case（小寫字母、數字、連字號）
  3. 不允許縮排的子項目（禁止巢狀清單，逼每個 task 攤平成一行）
  4. 嚴禁代碼塊標記（```）
  5. task 數量不得超過 MAX_TASKS（超過代表這個 change 該拆了）

用法：
    python3 task_lint.py <tasks.md> <expected-change-id>
"""

from __future__ import annotations

import re
import sys
from dataclasses import dataclass, field
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(REPO_ROOT))

from lib.common import frontmatter as fm  # noqa: E402

MAX_TASKS = 15
CODE_FENCE = "```"

# desc 用 '.+?'（非貪婪）而不是 '[^(]+?'：舊版排除所有括號，導致 exists()、
# logCase() 這類再自然不過的呼叫寫法直接被判定格式不符，而且錯誤訊息完全
# 沒點名是括號害的，是真的有人試跑時卡最久的一關。改成靠 ' (touches: ...)'
# 這個字面字串當分界，desc 本身可以含括號，靠正則的 backtracking 正確處理。
TASK_LINE_RE = re.compile(
    r"^- \[( |x|X)\] "
    r"(?P<task_id>[a-z0-9]+(?:-[a-z0-9]+)*): "
    r"(?P<desc>.+?)"
    r"(?: \(touches: (?P<touches>[^)]*)\))?$"
)


@dataclass
class LintResult:
    path: Path
    errors: list = field(default_factory=list)
    task_ids: list = field(default_factory=list)

    @property
    def ok(self) -> bool:
        return not self.errors


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
        result.errors.append(f"嚴禁出現代碼塊標記（{CODE_FENCE}）")

    task_ids = []
    for lineno, raw_line in enumerate(body.splitlines(), start=1):
        line = raw_line.rstrip()
        if not line.strip():
            continue

        if line.startswith((" ", "\t")):
            result.errors.append(f"第 {lineno} 行：不允許縮排/巢狀子項目 -> '{line.strip()}'")
            continue

        m = TASK_LINE_RE.match(line)
        if not m:
            result.errors.append(
                f"第 {lineno} 行：格式不符 '- [ ] <task-id>: <描述> (touches: ...)' -> '{line}'"
            )
            continue

        task_id = m.group("task_id")
        if task_id in task_ids:
            result.errors.append(f"第 {lineno} 行：task-id 重複 '{task_id}'")
        task_ids.append(task_id)

    if len(task_ids) > MAX_TASKS:
        result.errors.append(f"task 數量為 {len(task_ids)}，超過上限 {MAX_TASKS}（這個 change 該拆了）")

    result.task_ids = task_ids
    return result


def lint_file(path: Path, expected_change_id: str) -> LintResult:
    text = path.read_text(encoding="utf-8")
    return lint_text(text, expected_change_id, path=path)


def main(argv=None) -> int:
    argv = argv if argv is not None else sys.argv[1:]
    if len(argv) < 2:
        print("用法: task_lint.py <tasks.md> <expected-change-id>", file=sys.stderr)
        return 2

    path = Path(argv[0])
    expected_change_id = argv[1]

    if not path.exists():
        print(f"✗ {path}: 檔案不存在")
        return 1

    result = lint_file(path, expected_change_id)
    if result.ok:
        print(f"✓ {path}（{len(result.task_ids)} 個 task）")
        return 0

    print(f"✗ {path}")
    for err in result.errors:
        print(f"  - {err}")
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
