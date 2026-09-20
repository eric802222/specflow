"""lib.workflow.lifecycle 的單元測試。"""

import sys
import tempfile
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT))

from lib.workflow import lifecycle as lifecycle_mod  # noqa: E402


def test_bundled_default_requires_tasks_matches_design():
    lc = lifecycle_mod.load_lifecycle()
    assert lc.requires_tasks("draft") is False
    assert lc.requires_tasks("delivered") is True
    assert lc.requires_tasks("respec") is True
    assert lc.requires_tasks("ready") is True


def test_requires_tasks_defaults_false_for_unknown_state():
    lc = lifecycle_mod.load_lifecycle()
    assert lc.requires_tasks("not_a_real_state") is False


def test_unquoted_on_key_still_parsed_correctly():
    """回歸測試：YAML 1.1 會把沒加引號的 on: 解析成布林值 True 當 key，
    這裡故意寫一份沒加引號的版本，確認 transitions() 還是找得到。"""
    yaml_text = """\
id: test
initial: a
states:
  a:
    on:
      GO:
        target: b
        auto: true
  b:
    final: true
"""
    with tempfile.TemporaryDirectory() as d:
        p = Path(d) / "lifecycle.yaml"
        p.write_text(yaml_text, encoding="utf-8")
        lc = lifecycle_mod.load_lifecycle(p)

    transitions = lc.transitions("a")
    assert len(transitions) == 1
    assert transitions[0].event == "GO"
    assert transitions[0].target == "b"
    assert transitions[0].auto is True


def test_custom_lifecycle_can_override_bundled_default():
    yaml_text = """\
id: minimal
initial: only
states:
  only:
    final: true
"""
    with tempfile.TemporaryDirectory() as d:
        p = Path(d) / "lifecycle.yaml"
        p.write_text(yaml_text, encoding="utf-8")
        lc = lifecycle_mod.load_lifecycle(p)

    assert lc.id == "minimal"
    assert lc.is_final("only") is True
    assert lc.has_state("draft") is False  # 不是預設那五個狀態了
