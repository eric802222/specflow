"""影響範圍分析器（Blast Radius）。

MVP 範圍：對 `.spec/` 底下的 git diff 做「按目錄分類計數」的粗粒度統計——
不做跨檔案引用追蹤（那是下一階段），先回答「這次變更動到了哪些層」。

輸出範例：
    Blast Radius 統計：
      proposals: 1 個檔案
      glossary: 1 個檔案
      db: 0 個檔案
      api: 1 個檔案
      ui: 1 個檔案
      logic: 0 個檔案
      合計: 4 個檔案
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

CATEGORY_PREFIXES = {
    "proposals": "proposals/",
    "glossary": "glossary.yaml",
    "db": "db/",
    "api": "api/",
    "ui": "ui/",
    "logic": "logic/",
}


def get_changed_spec_files(spec_root: Path, base_ref: str = "HEAD") -> list:
    """回傳與 base_ref 相比、`.spec/` 底下有變動的檔案路徑清單（repo-relative）。"""
    try:
        output = subprocess.run(
            ["git", "diff", "--name-only", base_ref, "--", str(spec_root)],
            capture_output=True,
            text=True,
            check=True,
        ).stdout
    except subprocess.CalledProcessError as exc:
        raise RuntimeError(f"git diff 失敗：{exc.stderr}") from exc
    return [line for line in output.splitlines() if line.strip()]


def categorize(changed_files: list, spec_root_name: str = ".spec") -> dict:
    buckets = {cat: [] for cat in CATEGORY_PREFIXES}
    marker = f"{spec_root_name}/"
    for f in changed_files:
        idx = f.find(marker)
        if idx == -1:
            continue
        rel = f[idx + len(marker):]
        for cat, prefix in CATEGORY_PREFIXES.items():
            if rel.startswith(prefix):
                buckets[cat].append(rel)
                break
    return buckets


def summarize(buckets: dict) -> str:
    lines = ["Blast Radius 統計："]
    total = 0
    for cat, files in buckets.items():
        lines.append(f"  {cat}: {len(files)} 個檔案")
        total += len(files)
    lines.append(f"  合計: {total} 個檔案")
    return "\n".join(lines)


def main(argv=None) -> int:
    argv = argv if argv is not None else sys.argv[1:]
    spec_root = Path(argv[0]) if argv else Path(".spec")
    base_ref = argv[1] if len(argv) > 1 else "HEAD"

    changed = get_changed_spec_files(spec_root, base_ref)
    buckets = categorize(changed, spec_root_name=spec_root.name)
    print(summarize(buckets))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
