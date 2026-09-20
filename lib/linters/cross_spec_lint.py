"""跨規格一致性檢查：驗證 .spec/ 各檔案中引用的列舉值，都與 glossary.yaml 的定義一致。

檢查涵蓋範圍：
  1. logic/            決策表、狀態機 YAML 中的 `status:` 欄位值
  2. db/schema.dbml     與實體同名的 enum（慣例：`<entity_key>_status`）
  3. api/main.tsp       與實體同名的 enum（慣例：PascalCase(entity_key) + "Status"）
  4. ui/**/*.wf.yaml    `when: {state: ...}` 用到的值
     （wireframe-lofi 語法：https://github.com/eric802222/wireframe-lofi；
      `stage` 代表頁面路由階段、語意不同於實體狀態，此處不查）

命名慣例可能不符合每個專案的實際命名。找不到對應的 enum/檔案時該層會被「略過」而非報錯，
比對到的值只要不在 glossary 允許集合內，一律回報為錯誤——找不到來源是資訊，值不合法是錯誤。

同一個原則也適用在「entity 本身還沒被 glossary.yaml 定義」的情況：接手一個還沒有規格的
既有專案時，大多數實體本來就還沒被記錄，這不該讓 lint 報錯——只有「已經記錄、但記錄彼此
矛盾」才算錯誤。「還沒治理」是資料，不是缺陷。

用法：
    python3 cross_spec_lint.py <glossary.yaml> <entity_key> [spec_root=.spec]
"""

from __future__ import annotations

import re
import sys
from dataclasses import dataclass, field
from pathlib import Path

try:
    import yaml
except ImportError:  # pragma: no cover
    yaml = None


@dataclass
class LayerCheck:
    layer: str
    source: str
    checked: bool
    mismatches: list = field(default_factory=list)


@dataclass
class CrossSpecResult:
    errors: list = field(default_factory=list)
    checks: list = field(default_factory=list)

    @property
    def ok(self) -> bool:
        return not self.errors


def load_glossary_status_map(glossary_path: Path) -> dict:
    """回傳 {term_key: {允許的 status 值...}}。"""
    if yaml is None:
        raise RuntimeError("需要 pyyaml 才能解析 glossary.yaml")

    data = yaml.safe_load(glossary_path.read_text(encoding="utf-8")) or {}
    status_map = {}
    for term in data.get("terms", []) or []:
        key = term.get("key")
        statuses = term.get("status") or []
        if key:
            status_map[key] = set(statuses)
    return status_map


def to_pascal_case(snake: str) -> str:
    """`deal_line_item` -> `DealLineItem`（用於推導 TypeSpec enum 命名慣例）。"""
    return "".join(part[:1].upper() + part[1:] for part in snake.split("_") if part)


# ---------------------------------------------------------------------------
# logic/：決策表、狀態機
# ---------------------------------------------------------------------------

def _iter_status_values(node, path: str = ""):
    """遞迴走訪 YAML 結構，yield (path, status_value)，只找 key 為 'status' 的字串葉子。"""
    if isinstance(node, dict):
        for k, v in node.items():
            new_path = f"{path}.{k}" if path else str(k)
            if k == "status" and isinstance(v, str):
                yield new_path, v
            else:
                yield from _iter_status_values(v, new_path)
    elif isinstance(node, list):
        for i, item in enumerate(node):
            yield from _iter_status_values(item, f"{path}[{i}]")


def check_logic(spec_root: Path, entity_key: str, allowed: set) -> LayerCheck:
    logic_dir = spec_root / "logic"
    if not logic_dir.exists() or yaml is None:
        return LayerCheck("logic", str(logic_dir), checked=False)

    mismatches = []
    any_checked = False
    for yaml_file in sorted(logic_dir.rglob("*.yaml")):
        any_checked = True
        data = yaml.safe_load(yaml_file.read_text(encoding="utf-8")) or {}
        for path, value in _iter_status_values(data):
            if value not in allowed:
                mismatches.append(f"{yaml_file}:{path} = '{value}'")

    if not any_checked:
        return LayerCheck("logic", f"{logic_dir}（無 .yaml 檔案，略過）", checked=False)
    return LayerCheck("logic", f"{logic_dir}/**/*.yaml (status)", checked=True, mismatches=mismatches)


# ---------------------------------------------------------------------------
# db/schema.dbml
# ---------------------------------------------------------------------------

def extract_dbml_enum(text: str, enum_name: str):
    """從 DBML 文字中找出 `enum <enum_name> { ... }`，回傳成員值集合。找不到回傳 None。"""
    pattern = re.compile(r"enum\s+" + re.escape(enum_name) + r"\s*\{([^}]*)\}", re.IGNORECASE)
    m = pattern.search(text)
    if not m:
        return None
    values = set()
    for line in m.group(1).splitlines():
        line = line.split("//", 1)[0].strip()
        if not line:
            continue
        token = line.split("[", 1)[0].strip().strip(",").strip("'\"")
        if token:
            values.add(token)
    return values


def check_dbml(spec_root: Path, entity_key: str, allowed: set) -> LayerCheck:
    dbml_path = spec_root / "db" / "schema.dbml"
    enum_name = f"{entity_key}_status"

    if not dbml_path.exists():
        return LayerCheck("db", str(dbml_path), checked=False)

    values = extract_dbml_enum(dbml_path.read_text(encoding="utf-8"), enum_name)
    if values is None:
        return LayerCheck("db", f"{dbml_path}（enum {enum_name} 不存在，略過）", checked=False)

    mismatches = [f"{dbml_path}::enum {enum_name} 含 '{v}'" for v in sorted(values) if v not in allowed]
    return LayerCheck("db", f"{dbml_path}::enum {enum_name}", checked=True, mismatches=mismatches)


# ---------------------------------------------------------------------------
# api/main.tsp
# ---------------------------------------------------------------------------

def extract_tsp_enum(text: str, enum_name: str):
    """從 TypeSpec 文字中找出 `enum <enum_name> { ... }`，回傳成員的實際值集合。找不到回傳 None。"""
    pattern = re.compile(r"enum\s+" + re.escape(enum_name) + r"\s*\{([^}]*)\}")
    m = pattern.search(text)
    if not m:
        return None
    values = set()
    for entry in m.group(1).split(","):
        entry = entry.strip()
        if not entry:
            continue
        quoted = re.search(r'"([^"]*)"', entry)
        if quoted:
            values.add(quoted.group(1))
        else:
            ident = entry.split(":", 1)[0].strip()
            if ident:
                values.add(ident)
    return values


def check_tsp(spec_root: Path, entity_key: str, allowed: set) -> LayerCheck:
    tsp_path = spec_root / "api" / "main.tsp"
    enum_name = f"{to_pascal_case(entity_key)}Status"

    if not tsp_path.exists():
        return LayerCheck("api", str(tsp_path), checked=False)

    values = extract_tsp_enum(tsp_path.read_text(encoding="utf-8"), enum_name)
    if values is None:
        return LayerCheck("api", f"{tsp_path}（enum {enum_name} 不存在，略過）", checked=False)

    mismatches = [f"{tsp_path}::enum {enum_name} 含 '{v}'" for v in sorted(values) if v not in allowed]
    return LayerCheck("api", f"{tsp_path}::enum {enum_name}", checked=True, mismatches=mismatches)


# ---------------------------------------------------------------------------
# ui/**/*.wf.yaml（wireframe-lofi）
# ---------------------------------------------------------------------------

def extract_wf_when_values(yaml_text: str, ctx_key: str = "state"):
    """遞迴掃描 .wf.yaml 內容，收集所有 `when: {<ctx_key>: ...}` 用到的值（字串或 list=OR）。"""
    if yaml is None:
        return set()
    data = yaml.safe_load(yaml_text) or {}
    values = set()

    def walk(node):
        if isinstance(node, dict):
            when = node.get("when")
            if isinstance(when, dict) and ctx_key in when:
                v = when[ctx_key]
                if isinstance(v, str):
                    values.add(v)
                elif isinstance(v, list):
                    values.update(str(x) for x in v)
            for v in node.values():
                walk(v)
        elif isinstance(node, list):
            for item in node:
                walk(item)

    walk(data)
    return values


def check_ui(spec_root: Path, entity_key: str, allowed: set, ctx_key: str = "state") -> LayerCheck:
    ui_dir = spec_root / "ui"
    if not ui_dir.exists() or yaml is None:
        return LayerCheck("ui", str(ui_dir), checked=False)

    mismatches = []
    any_checked = False
    for wf_file in sorted(ui_dir.rglob("*.wf.yaml")):
        any_checked = True
        values = extract_wf_when_values(wf_file.read_text(encoding="utf-8"), ctx_key=ctx_key)
        for v in values:
            if v not in allowed:
                mismatches.append(f"{wf_file}: when.{ctx_key} = '{v}'")

    if not any_checked:
        return LayerCheck("ui", f"{ui_dir}（無 .wf.yaml 檔案，略過）", checked=False)
    return LayerCheck("ui", f"{ui_dir}/**/*.wf.yaml (when.{ctx_key})", checked=True, mismatches=mismatches)


# ---------------------------------------------------------------------------
# 主流程
# ---------------------------------------------------------------------------

def lint_entity(glossary_path: Path, entity_key: str, spec_root: Path) -> CrossSpecResult:
    result = CrossSpecResult()

    status_map = load_glossary_status_map(glossary_path)
    allowed = status_map.get(entity_key)
    if allowed is None:
        # 這個實體還沒被 glossary.yaml 記錄過——這是「還沒治理」，不是錯誤。
        # 接手一個沒有既有規格的專案時，大多數實體本來就還沒被寫進 glossary，
        # 不該因此擋住整條 lint 流程；只有「已經記錄、但記錄彼此矛盾」才算錯誤。
        # 找不到定義是資訊，值不合法才是錯誤——這條原則跟其他四層一致。
        result.checks = [
            LayerCheck(
                "glossary",
                f"{glossary_path}（實體 '{entity_key}' 尚未定義，略過四層檢查）",
                checked=False,
            )
        ]
        return result

    checks = [
        check_logic(spec_root, entity_key, allowed),
        check_dbml(spec_root, entity_key, allowed),
        check_tsp(spec_root, entity_key, allowed),
        check_ui(spec_root, entity_key, allowed),
    ]
    result.checks = checks
    for c in checks:
        for m in c.mismatches:
            result.errors.append(f"[{c.layer}] {m}")
    return result


def main(argv=None) -> int:
    argv = argv if argv is not None else sys.argv[1:]
    if len(argv) < 2:
        print(
            "用法: cross_spec_lint.py <glossary.yaml> <entity_key> [spec_root=.spec]",
            file=sys.stderr,
        )
        return 2

    glossary_path = Path(argv[0])
    entity_key = argv[1]
    spec_root = Path(argv[2]) if len(argv) > 2 else Path(".spec")

    result = lint_entity(glossary_path, entity_key, spec_root)

    for c in result.checks:
        if not c.checked:
            print(f"… [{c.layer}] 略過（{c.source}）")
        elif c.mismatches:
            print(f"✗ [{c.layer}] {c.source}：發現 {len(c.mismatches)} 處不一致")
        else:
            print(f"✓ [{c.layer}] {c.source}")

    any_checked = any(c.checked for c in result.checks)

    if result.ok and not any_checked:
        print(f"\n… '{entity_key}' 尚未被治理（未在 glossary.yaml 定義），略過所有檢查——這是合法狀態，不是錯誤")
        return 0

    if result.ok:
        print(f"\n✓ status 值全數符合 glossary 定義（{entity_key}）")
        return 0

    print(f"\n✗ 發現 {len(result.errors)} 處 status 不一致：")
    for err in result.errors:
        print(f"  - {err}")
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
