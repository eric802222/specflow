"""hotfix 生命周期的端到端測試：draft --HOTFIX_LIVE--> live_pending_review --POSTREVIEW_DONE--> applied。"""

import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT))

from bin import specflow as cli  # noqa: E402

HOTFIX_PROPOSAL = """\
---
id: CP-1
title: "資料庫連線池爆掉"
impact_surface:
  - .spec/db/schema.dbml
type: hotfix
status: draft
---

## 症狀 (Symptom)

連線數衝到上限，API 全部逗時。
"""

FEATURE_PROPOSAL = """\
---
id: CP-2
title: "一般功能"
impact_surface:
  - x
type: feature
status: draft
---

## 1. 為什麼 (Why)

示範用。

## 2. 目標 (Goals)

- 示範

## 3. 非目標 (Non-Goals)

- 無
"""


def _run(argv):
    parser = cli.build_parser()
    args = parser.parse_args(argv)
    return args.func(args)


def test_hotfix_full_flow_reaches_applied(tmp_path):
    spec_root = tmp_path / ".spec"
    change_dir = spec_root / "changes" / "CP-1"
    change_dir.mkdir(parents=True)
    (change_dir / "proposal.md").write_text(HOTFIX_PROPOSAL, encoding="utf-8")

    root_args = ["--spec-root", str(spec_root)]

    assert _run(["transition", *root_args, "CP-1", "HOTFIX_LIVE"]) == 0
    status = (change_dir / "proposal.md").read_text(encoding="utf-8")
    assert "status: live_pending_review" in status

    # live_pending_review 要求 tasks.md 才能再往前走（事後審查的驗屩報告）
    assert _run(["next", *root_args, "CP-1"]) == 1  # write_tasks_md 擋住

    (change_dir / "tasks.md").write_text(
        "---\nchange: CP-1\n---\n\n"
        "- [ ] postmortem: 補上事後審查記錄 (touches: db/schema.dbml)\n",
        encoding="utf-8",
    )

    assert _run(["transition", *root_args, "CP-1", "POSTREVIEW_DONE"]) == 0
    status = (change_dir / "proposal.md").read_text(encoding="utf-8")
    assert "status: applied" in status


def test_feature_type_cannot_use_hotfix_live(tmp_path):
    spec_root = tmp_path / ".spec"
    change_dir = spec_root / "changes" / "CP-2"
    change_dir.mkdir(parents=True)
    (change_dir / "proposal.md").write_text(FEATURE_PROPOSAL, encoding="utf-8")

    exit_code = _run(["transition", "--spec-root", str(spec_root), "CP-2", "HOTFIX_LIVE"])
    assert exit_code == 1

    status = (change_dir / "proposal.md").read_text(encoding="utf-8")
    assert "status: draft" in status  # 沒有被改動
