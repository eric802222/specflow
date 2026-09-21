"""共用的「固定欄位 + checkbox 選項 + 摘要交叉比對」解析核心。

design.md（工程決策）跟 review.md（審查發現）用的是同一套機制，只是欄位名稱、
狀態集合、摘要標題不同——這套邏輯不是巧合地長得像，是刻意設計成可以被多種
「需要結構化記錄＋追蹤結案狀態」的場景共用。重複實作兩份很容易改 bug 只改到
一邊，之前這個檔案不存在時，design_lint.py 自己內含了一套；這裡抽出來共用。

核心規則（跟使用哪個 schema 無關）：
  1. Frontmatter 必須有 `change` 欄位，且值要等於外部傳入的 change_id
  2. 每個項目標題格式：`### <emoji> <prefix><n> — <標題>`
  3. 編號不得重複
  4. 「已定案」狀態只能用固定的自由文字欄位；「待確認」狀態的其中一個欄位
     改用 checkbox 選項清單（跟 tasks.md 同語法），不能假裝已經有答案
  5. 選項清單至少 MIN_OPTIONS 個，且必須包含「其他補充」，避免變成強迫選擇
  6. 勾了一個選項、但狀態還是「待確認」，視為錯誤——代表已經決定了，
     該把這個項目改成「已定案」狀態
  7. 嚴禁代碼塊標記
  8. 檔案最上方的摘要清單跟內文的待確認項目互相交叉比對，兩邊對不上就是錯誤
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path

from lib.common import frontmatter as fm

CODE_FENCE = "```"
MAX_FIELD_LENGTH = 200
MIN_OPTIONS = 2
SUPPLEMENT_LABEL = "其他補充"


@dataclass
class StructuredSchema:
    """定義一種「固定欄位＋checkbox」文件的完整規則。"""

    entity_prefix: str  # 標題裡的項目前綴，例如 "D"（決策）或 "F"（發現）
    entity_noun: str  # 錯誤訊息用的名詞，例如 "決策" 或 "發現項目"
    confirmed_status: str  # 例如 "✅"
    pending_statuses: tuple  # 例如 ("⏳", "🚫") 或 ("⏳",)
    confirmed_field_order: tuple  # 例如 ("事件", "決策", "取捨")
    confirmed_required: tuple
    pending_field_order: tuple  # 例如 ("事件", "選項", "取捨")
    pending_required: tuple
    checkbox_field_label: str  # 待確認狀態裡，哪個欄位名稱允許展開成 checkbox
    summary_icon: str  # 摘要標題用的 emoji，例如 "⏳" 或 "🔴"
    summary_label: str  # 摘要標題文字，例如 "待確認" 或 "待處理"

    @property
    def all_field_labels(self) -> tuple:
        return tuple(sorted(set(self.confirmed_field_order) | set(self.pending_field_order)))

    @property
    def all_statuses(self) -> tuple:
        return (self.confirmed_status,) + tuple(self.pending_statuses)


@dataclass
class LintResult:
    path: Path
    errors: list = field(default_factory=list)

    @property
    def ok(self) -> bool:
        return not self.errors


def _build_regexes(schema: StructuredSchema):
    status_alt = "|".join(re.escape(s) for s in schema.all_statuses)
    heading_re = re.compile(
        rf"^### (?P<emoji>{status_alt}) {re.escape(schema.entity_prefix)}(?P<num>\d+) — (?P<title>.+?)\s*$",
        re.MULTILINE,
    )
    field_alt = "|".join(re.escape(f) for f in schema.all_field_labels)
    field_line_re = re.compile(rf"^-\s+\*\*({field_alt})\*\*：\s*(.*)$")
    summary_heading_re = re.compile(
        rf"^## {re.escape(schema.summary_icon)} {re.escape(schema.summary_label)}（(?P<count>\d+)）\s*$",
        re.MULTILINE,
    )
    summary_bullet_re = re.compile(
        rf"^-\s+\*\*{re.escape(schema.entity_prefix)}(?P<num>\d+)\*\*\s+—", re.MULTILINE
    )
    option_item_re = re.compile(r"^-\s+\[( |x|X)\]\s*(.*)$")
    return heading_re, field_line_re, summary_heading_re, summary_bullet_re, option_item_re


def _find_entities(body: str, heading_re):
    matches = list(heading_re.finditer(body))
    entities = []
    for i, m in enumerate(matches):
        start = m.end()
        end = matches[i + 1].start() if i + 1 < len(matches) else len(body)
        entity_body = body[start:end]
        lineno = body.count("\n", 0, m.start()) + 1
        entities.append((m.group("emoji"), m.group("num"), m.group("title"), entity_body, lineno))
    return entities


def _parse_entity_body(entity_body: str, num: str, entity_noun: str, field_line_re, option_item_re):
    parsed = []
    errors = []
    lines = entity_body.splitlines()
    i, n = 0, len(lines)

    while i < n:
        raw = lines[i]
        stripped = raw.strip()
        if not stripped:
            i += 1
            continue

        m = field_line_re.match(stripped)
        if not m:
            errors.append(
                f"{entity_noun} {num}：不合法的內容 '{stripped}'（只能用固定欄位，不允許自由段落文字）"
            )
            i += 1
            continue

        label, value = m.group(1), m.group(2)

        # 如果這個欄位緊接著就是縮排的 checkbox 清單，視為 checkbox 展開欄位
        i += 1
        options = []
        while i < n:
            sub_raw = lines[i]
            sub_stripped = sub_raw.strip()
            if not sub_stripped:
                i += 1
                continue
            is_indented = sub_raw[:1] in (" ", "\t")
            om = option_item_re.match(sub_stripped)
            if is_indented and om:
                options.append((om.group(1).lower() == "x", om.group(2).strip()))
                i += 1
                continue
            break

        if options:
            parsed.append({"label": label, "options": options})
        else:
            parsed.append({"label": label, "value": value})

    return parsed, errors


def _check_order(labels_seen, allowed_order, num, entity_noun) -> list:
    errors = []
    last_idx = -1
    for label in labels_seen:
        if label not in allowed_order:
            continue
        idx = allowed_order.index(label)
        if idx < last_idx:
            errors.append(
                f"{entity_noun} {num}：欄位順序錯誤，必須依序是 {' → '.join(allowed_order)}（'{label}' 出現在不對的位置）"
            )
        last_idx = idx
    return errors


def _validate_entity(entity_body: str, num: str, status: str, schema: StructuredSchema, field_line_re, option_item_re) -> list:
    parsed, errors = _parse_entity_body(entity_body, num, schema.entity_noun, field_line_re, option_item_re)
    labels_seen = [p["label"] for p in parsed]

    is_confirmed = status == schema.confirmed_status
    allowed = schema.confirmed_field_order if is_confirmed else schema.pending_field_order
    required = schema.confirmed_required if is_confirmed else schema.pending_required
    kind = f"{schema.confirmed_status} 已定案" if is_confirmed else f"{'/'.join(schema.pending_statuses)} 待確認"

    for label in labels_seen:
        if label not in allowed:
            errors.append(f"{schema.entity_noun} {num}（{kind}）：不允許使用欄位 '{label}'，這個狀態只能用 {' / '.join(allowed)}")

    for req in required:
        if req not in labels_seen:
            errors.append(f"{schema.entity_noun} {num}：缺少必要欄位 '{req}'")

    seen_single = set()
    for label in labels_seen:
        if label == schema.checkbox_field_label and not is_confirmed:
            continue  # checkbox 欄位本來就是一個清單區塊，只出現一次
        if label in seen_single:
            errors.append(f"{schema.entity_noun} {num}：欄位 '{label}' 重複")
        seen_single.add(label)

    errors.extend(_check_order(labels_seen, allowed, num, schema.entity_noun))

    for p in parsed:
        if "options" in p:
            continue
        if len(p.get("value", "")) > MAX_FIELD_LENGTH:
            errors.append(f"{schema.entity_noun} {num} 的 '{p['label']}' 欄位長度為 {len(p['value'])} 字元，超過上限 {MAX_FIELD_LENGTH}")

    if not is_confirmed:
        option_blocks = [p for p in parsed if p["label"] == schema.checkbox_field_label and "options" in p]
        if not any(p["label"] == schema.checkbox_field_label for p in parsed):
            errors.append(f"{schema.entity_noun} {num}：{kind}必須有 '{schema.checkbox_field_label}' 清單，供選擇或補充，不能只寫完就結束")
        else:
            options = option_blocks[0]["options"] if option_blocks else []

            if len(options) < MIN_OPTIONS:
                errors.append(f"{schema.entity_noun} {num}：選項數量為 {len(options)}，至少要有 {MIN_OPTIONS} 個供選擇")

            if not any(text.startswith(SUPPLEMENT_LABEL) for _checked, text in options):
                errors.append(f"{schema.entity_noun} {num}：選項清單必須包含一項「{SUPPLEMENT_LABEL}：」，避免變成強迫從既有選項裡選")

            for _checked, text in options:
                if len(text) > MAX_FIELD_LENGTH:
                    errors.append(f"{schema.entity_noun} {num} 的選項 '{text[:30]}...' 過長，超過上限 {MAX_FIELD_LENGTH} 字元")

            checked_count = sum(1 for checked, _text in options if checked)
            if checked_count > 1:
                errors.append(f"{schema.entity_noun} {num}：選項勾選了 {checked_count} 個，應該只挑一個答案")
            elif checked_count == 1:
                errors.append(
                    f"{schema.entity_noun} {num}：已經勾選了一個選項，但狀態仍是 {status}——"
                    f"確定的話，請把這個項目改成 {schema.confirmed_status}，並改用「{' / '.join(schema.confirmed_field_order)}」欄位記錄最終結果，"
                    "不要讓檔案同時說『還沒決定』又『已經勾了答案』"
                )

    return errors


def lint_structured_text(text: str, expected_change_id: str, schema: StructuredSchema, path: Path = None) -> LintResult:
    result = LintResult(path=path or Path("<memory>"))
    heading_re, field_line_re, summary_heading_re, summary_bullet_re, option_item_re = _build_regexes(schema)

    fm_data, body, error = fm.load_frontmatter_data(text)
    if error:
        result.errors.append(error)
        fm_data = fm_data or {}

    if isinstance(fm_data, dict):
        change_ref = fm_data.get("change")
        if not change_ref:
            result.errors.append("frontmatter 缺少必要欄位：change")
        elif change_ref != expected_change_id:
            result.errors.append(f"frontmatter 的 change ('{change_ref}') 與所在資料夾 ('{expected_change_id}') 不一致")
    elif not error:
        result.errors.append("frontmatter 必須是一個 YAML mapping")

    if CODE_FENCE in text:
        result.errors.append(f"嚴禁出現代碼塊標記（{CODE_FENCE}）")

    entities = _find_entities(body, heading_re)
    seen_nums = set()
    for emoji, num, title, entity_body, lineno in entities:
        if num in seen_nums:
            result.errors.append(f"第 {lineno} 行：{schema.entity_prefix}{num} 編號重複")
        seen_nums.add(num)
        result.errors.extend(_validate_entity(entity_body, num, emoji, schema, field_line_re, option_item_re))

    pending_nums = {num for emoji, num, *_ in entities if emoji != schema.confirmed_status}

    m = summary_heading_re.search(body)
    if pending_nums and not m:
        result.errors.append(
            f"有 {len(pending_nums)} 個{schema.summary_label}項目（{sorted(pending_nums)}），"
            f"但檔案最上方缺少 '## {schema.summary_icon} {schema.summary_label}（N）' 摘要區塊"
        )
    elif m:
        declared_count = int(m.group("count"))
        start = m.end()
        next_heading = re.search(r"^## ", body[start:], re.MULTILINE)
        end = start + next_heading.start() if next_heading else len(body)
        section = body[start:end]
        listed_nums = {bm.group("num") for bm in summary_bullet_re.finditer(section)}

        if declared_count != len(pending_nums):
            result.errors.append(f"摘要區塊宣告 {declared_count} 個{schema.summary_label}，但內文實際有 {len(pending_nums)} 個")

        extra = listed_nums - pending_nums
        missing = pending_nums - listed_nums
        if extra:
            result.errors.append(f"摘要區塊列出了 {sorted(extra)}，但這些項目在內文已經是 {schema.confirmed_status} 或不存在——摘要過期了")
        if missing:
            result.errors.append(f"內文有{schema.summary_label}項目 {sorted(missing)}，但摘要區塊沒有列出——摘要漏更新了")

    return result
