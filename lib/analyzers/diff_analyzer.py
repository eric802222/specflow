"""影響範圍分析器（Blast Radius）。

對 `<spec-root>/specs/` 底下的 git diff 做「按目錄分類計數」的粗粒度統計——
不做跨檔案引用追蹤，先回答「這次變更動到了哪些層」。統計對象是 specs/（目前
正式生效的規格），不是 changes/<id>/（那只是流程文件，proposal.md 改了幾行
不算「動到系統的哪個部分」。
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

CATEGORY_PREFIXES = {
    "glossary": "glossary.yaml",
    "db": "db/",
    "api": "api/",
    "ui": "ui/",
    "logic": "logic/",
}


def get_changed_files(specs_dir: Path, base_ref: str = "HEAD") -> list:
    """回傳與 base_ref 相比、specs_dir 底下有變動的檔案路徑清單（repo-relative）。"""
    cwd = specs_dir if specs_dir.exists() else specs_dir.parent
    try:
        output = subprocess.run(
            ["git", "diff", "--name-only", base_ref, "--", str(specs_dir)],
            cwd=str(cwd),
            capture_output=True,
            text=True,
            check=True,
        ).stdout
    except subprocess.CalledProcessError as exc:
        raise RuntimeError(f"git diff 失敗：{exc.stderr}") from exc
    return [line for line in output.splitlines() if line.strip()]


def categorize(changed_files: list, specs_dir_name: str = "specs") -> dict:
    buckets = {cat: [] for cat in CATEGORY_PREFIXES}
    marker = f"{specs_dir_name}/"
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


def analyze(specs_dir: Path, base_ref: str = "HEAD") -> dict:
    """回傳 {"changed_files": [...], "buckets": {...}, "summary": "..."}，方便其他模組呼叫。"""
    changed = get_changed_files(specs_dir, base_ref)
    buckets = categorize(changed, specs_dir_name=specs_dir.name)
    return {
        "changed_files": changed,
        "buckets": buckets,
        "summary": summarize(buckets),
    }


def main(argv=None) -> int:
    argv = argv if argv is not None else sys.argv[1:]
    specs_dir = Path(argv[0]) if argv else Path(".spec/specs")
    base_ref = argv[1] if len(argv) > 1 else "HEAD"

    result = analyze(specs_dir, base_ref)
    print(result["summary"])
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
