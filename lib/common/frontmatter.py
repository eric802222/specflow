"""共用的 Frontmatter Markdown 解析／寫入工具。

被 proposal_lint.py、task_lint.py 共用，避免同一套邏輯在兩個檔案各自維護一份、
修 bug 要修兩次（曾經真的踩過：兩份各自用 text.split("---", 2) 切分，遇到欄位
值本身含有連續三個減號就會切錯——例如 title 用了長破折號、路徑帶 "---"）。

分隔線的判定：只認「單獨一行、去除頭尾空白後剛好是 --- 」的那一行，不是在整份
文字裡任意找 --- 子字串。這樣即使欄位值裡真的出現 "---"，也不會被誤判成分隔線。
"""

from __future__ import annotations

import re
from pathlib import Path

try:
    import yaml
except ImportError:  # pragma: no cover
    yaml = None

from lib.common.atomic_write import atomic_write_text

_DELIM_RE = re.compile(r"^---[ \t]*\r?$", re.MULTILINE)


def split_frontmatter(text: str):
    """把檔案切成 (frontmatter_yaml, body)。

    找不到合法的頭尾兩條 --- 分隔線就回傳 (None, text)。合法定義：文字必須從
    第一行就是單獨的 ---，且後面還能找到第二個單獨一行的 ---。
    """
    matches = list(_DELIM_RE.finditer(text))
    if len(matches) < 2 or matches[0].start() != 0:
        return None, text

    first, second = matches[0], matches[1]
    fm_text = text[first.end():second.start()]
    body = text[second.end():]
    return fm_text, body


def load_frontmatter_data(text: str):
    """回傳 (fm_data, body, error)。fm_data 解析失敗時為 None，error 說明原因。"""
    fm_text, body = split_frontmatter(text)
    if fm_text is None:
        return None, body, "缺少 frontmatter 區塊（檔案必須以單獨一行 --- 開頭，並包含單獨一行的 --- 結尾）"
    if yaml is None:
        return None, body, "缺少 pyyaml 套件，無法解析 frontmatter"
    try:
        data = yaml.safe_load(fm_text) or {}
    except yaml.YAMLError as exc:
        return None, body, f"frontmatter YAML 解析失敗：{exc}"
    return data, body, None


def read_frontmatter(path: Path) -> dict:
    """讀出一份檔案的 frontmatter，解析失敗回傳 {}（不拋例外，給只想讀欄位的呼叫端用）。"""
    text = path.read_text(encoding="utf-8")
    data, _, _ = load_frontmatter_data(text)
    return data if isinstance(data, dict) else {}


def write_frontmatter_field(path: Path, key: str, value) -> None:
    """就地替換 frontmatter 裡「單一個」純量欄位的值，其他任何一行都不動。

    刻意只支援替換形如 `key: value` 的單行純量欄位；key 必須已經存在於
    frontmatter 裡，否則拋例外。不對整份 frontmatter 重新序列化——那樣會連
    引號、縮排風格都被 YAML dumper 重新排版，讓 git diff 在只改一個欄位時
    卻顯示整段 frontmatter 都變了，違背「Diff 即交付」希望 diff 保持乾淨的初衷。
    """
    text = path.read_text(encoding="utf-8")
    fm_text, _ = split_frontmatter(text)
    if fm_text is None:
        raise ValueError(f"{path} 找不到 frontmatter 區塊")

    field_re = re.compile(rf"^({re.escape(key)}:)([ \t]*)(.*)$", re.MULTILINE)
    m = field_re.search(fm_text)
    if not m:
        raise ValueError(f"{path} 的 frontmatter 找不到欄位：{key}")

    new_value_str = _format_scalar(value)
    new_fm_text = fm_text[: m.start()] + f"{key}: {new_value_str}" + fm_text[m.end():]

    matches = list(_DELIM_RE.finditer(text))
    first, second = matches[0], matches[1]
    new_text = text[: first.end()] + new_fm_text + text[second.start():]
    atomic_write_text(path, new_text)


def _format_scalar(value) -> str:
    """把一個純量值格式化成可以直接接在 `key: ` 後面的字串。"""
    if isinstance(value, str) and re.match(r"^[A-Za-z0-9_\-./]+$", value):
        return value  # 純英數/連字號/底線/斜線的簡單字串不需要加引號
    if yaml is None:
        return str(value)
    return yaml.safe_dump(value, allow_unicode=True).strip()
