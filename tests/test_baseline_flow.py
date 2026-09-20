"""baseline 生命周期的端到端測試：draft --BASELINE_CAPTURED--> baseline_recorded（直達終點）。
以及 specflow coverage 的端到端測試。
"""

import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT))

from bin import specflow as cli  # noqa: E402

BASELINE_PROPOSAL = """\
---
id: CP-1
title: "既有折扣核準流程現況"
impact_surface:
  - x
type: baseline
status: draft
---

## 現況 (What it actually does today)

業務主管手動在後台核準，沒有系統輔助。

## 依據 (Source of Truth)

讀了 approval_controller.rb，並跟業務主管確認過。
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


def test_baseline_captured_reaches_dedicated_terminal_state_without_tasks(tmp_path):
    """baseline type 不需要 tasks.md 就能直接走到終點——它純粹描述現況，
    沒有開發工作可以分解成 task。"""
    spec_root = tmp_path / ".spec"
    change_dir = spec_root / "changes" / "CP-1"
    change_dir.mkdir(parents=True)
    (change_dir / "proposal.md").write_text(BASELINE_PROPOSAL, encoding="utf-8")

    exit_code = _run(["transition", "--spec-root", str(spec_root), "CP-1", "BASELINE_CAPTURED"])

    assert exit_code == 0
    status_text = (change_dir / "proposal.md").read_text(encoding="utf-8")
    assert "status: baseline_recorded" in status_text


def test_feature_type_cannot_use_baseline_captured(tmp_path):
    spec_root = tmp_path / ".spec"
    change_dir = spec_root / "changes" / "CP-2"
    change_dir.mkdir(parents=True)
    (change_dir / "proposal.md").write_text(FEATURE_PROPOSAL, encoding="utf-8")

    exit_code = _run(["transition", "--spec-root", str(spec_root), "CP-2", "BASELINE_CAPTURED"])
    assert exit_code == 1

    status_text = (change_dir / "proposal.md").read_text(encoding="utf-8")
    assert "status: draft" in status_text  # 沒有被改動


def test_coverage_reports_undefined_entities_without_error(tmp_path):
    """glossary.yaml 不存在時，coverage 要能正常運作、exit code 是 0——
    這正是接手一個還沒有規格的既有專案時最常見的起點狀態。"""
    spec_root = tmp_path / ".spec"
    spec_root.mkdir()

    exit_code = _run(["coverage", "--spec-root", str(spec_root)])
    assert exit_code == 0


def test_coverage_lists_defined_entities_and_their_checked_layers(tmp_path):
    spec_root = tmp_path / ".spec"
    specs_dir = spec_root / "specs"
    (specs_dir / "db").mkdir(parents=True)
    (specs_dir / "db" / "schema.dbml").write_text(
        "enum deal_status {\n  draft\n  approved\n}\n", encoding="utf-8"
    )
    (specs_dir / "glossary.yaml").write_text(
        "version: 1\nterms:\n  - key: deal\n    status: [draft, approved]\n",
        encoding="utf-8",
    )

    exit_code = _run(["coverage", "--spec-root", str(spec_root)])
    assert exit_code == 0
