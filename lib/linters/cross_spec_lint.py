"""跨規格一致性檢查：驗證 .spec/ 各檔案中引用的 status 值都存在於 glossary.yaml。

MVP 範圍：
  - 讀取 glossary.yaml 中每個 term 的 status 列舉。
  - 掃描指定的 logic 目錄（決策表、狀態機 YAML），找出所有 `status:` 欄位的值。
  - 若掃描到的 status 值不在對應 term 的允許列舉中，回報為錯誤。

之後可擴充：db/schema.dbml 的 enum 對照、api/main.tsp 的 enum 對照、
ui/pages/*.wf.yaml 的 when:{stage,state} 對照。
"""

from __future__ import annotations

import sys
from dataclasses import dataclass, field
from pathlib import Path

try:
    import yaml
except ImportError:  # pragma: no cover
    yaml = None


@dataclass
class CrossSpecResult:
    errors: list = field(default_factory=list)

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


def lint_logic_dir(logic_dir: Path, status_map: dict, entity_key: str) -> CrossSpecResult:
    result = CrossSpecResult()
    allowed = status_map.get(entity_key)
    if allowed is None:
        result.errors.append(f"glossary.yaml 未定義實體 '{entity_key}'，無法檢查其 status")
        return result

    if not logic_dir.exists():
        result.errors.append(f"找不到目錄：{logic_dir}")
        return result

    for yaml_file in sorted(logic_dir.rglob("*.yaml")):
        if yaml is None:
            break
        data = yaml.safe_load(yaml_file.read_text(encoding="utf-8")) or {}
        for path, value in _iter_status_values(data):
            if value not in allowed:
                result.errors.append(
                    f"{yaml_file}:{path} 使用了未在 glossary 定義的 status 值 '{value}'"
                    f"（{entity_key} 允許：{sorted(allowed)}）"
                )
    return result


def main(argv=None) -> int:
    argv = argv if argv is not None else sys.argv[1:]
    if len(argv) < 2:
        print(
            "用法: cross_spec_lint.py <glossary.yaml> <entity_key> [logic_dir=.spec/logic]",
            file=sys.stderr,
        )
        return 2

    glossary_path = Path(argv[0])
    entity_key = argv[1]
    logic_dir = Path(argv[2]) if len(argv) > 2 else Path(".spec/logic")

    status_map = load_glossary_status_map(glossary_path)
    result = lint_logic_dir(logic_dir, status_map, entity_key)

    if result.ok:
        print(f"✓ status 值全數符合 glossary 定義（{entity_key}）")
        return 0

    print(f"✗ 發現 {len(result.errors)} 處 status 不一致：")
    for err in result.errors:
        print(f"  - {err}")
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
