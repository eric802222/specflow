"""解析 change-lifecycle.yaml 這類狀態機定義檔（跟 logic/lifecycle.yaml 同語法）。

只提供查詢用途：目前狀態的合法轉移有哪些、哪些是自動（lint 通過即可）、
哪些是人工事件。不做通用的 XState 直譯器，範圍只到 specflow 自己需要的查詢。
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

try:
    import yaml
except ImportError:  # pragma: no cover
    yaml = None

REPO_ROOT = Path(__file__).resolve().parent.parent.parent
DEFAULT_LIFECYCLE_PATH = REPO_ROOT / "templates" / "change-lifecycle.yaml"


@dataclass
class Transition:
    event: str
    target: str
    auto: bool
    requires_type: str = None
    skip_target_check: bool = False


class Lifecycle:
    def __init__(self, data: dict):
        self._data = data
        self.id = data.get("id", "")
        self.initial = data.get("initial")
        self.states = data.get("states", {}) or {}

    def has_state(self, name: str) -> bool:
        return name in self.states

    def is_final(self, name: str) -> bool:
        state = self.states.get(name, {})
        return bool(state.get("final"))

    def requires_tasks(self, name: str) -> bool:
        """這個狀態是否要求 tasks.md 存在——直接宣告在 YAML 裡，不是另外用一份
        Python 常數維護；不然 YAML 加了新狀態，Python 那份常數不會自動知道。"""
        state = self.states.get(name, {})
        return bool(state.get("requires_tasks"))

    def allows(self, name: str, capability: str) -> bool:
        """這個狀態是否允許某個 command capability（例如 generate_delivery）。
        capability 清單直接宣告在 YAML 的 `allows:` 底下，CLI 指令查這裡決定能不能跑，
        不要自己 hard-code「delivered 才能產生交付內容」這種規則散在程式碼各處——
        不然 lifecycle 定義的規則跟 CLI 自己認定的規則會漸漸分岔。"""
        state = self.states.get(name, {})
        return capability in (state.get("allows") or [])

    def transitions(self, name: str) -> list:
        """回傳某狀態底下所有合法轉移（Transition 物件的清單），不篩選 requires_type。"""
        state = self.states.get(name, {})
        # 防呆：YAML 1.1 會把沒加引號的 `on:` 解析成布林值 True 當 key，
        # 這裡兩種都接受，避免因為忘了加引號就整組轉移規則悄悄消失。
        on = state.get("on") or state.get(True) or {}
        result = []
        for event, spec in on.items():
            if isinstance(spec, dict):
                result.append(
                    Transition(
                        event=event,
                        target=spec.get("target"),
                        auto=bool(spec.get("auto")),
                        requires_type=spec.get("requires_type"),
                        skip_target_check=bool(spec.get("skip_target_check")),
                    )
                )
            else:
                # 允許簡寫：EVENT: target_state（視為非自動、無 type 限制）
                result.append(Transition(event=event, target=spec, auto=False))
        return result

    def available_transitions(self, name: str, proposal_type: str = None) -> list:
        """回傳某狀態底下，這個 proposal 的 type 有資格使用的轉移——
        requires_type 沒設定的轉移永遠可用；有設定的，只有 type 對得上才算可用。
        """
        return [
            t for t in self.transitions(name)
            if t.requires_type is None or t.requires_type == proposal_type
        ]

    def find_transition(self, name: str, event: str):
        """回傳某狀態底下、事件名稱相符的 Transition（不篩選 requires_type），找不到回 None。"""
        for t in self.transitions(name):
            if t.event == event:
                return t
        return None

    def auto_transitions(self, name: str) -> list:
        return [t for t in self.transitions(name) if t.auto]

    def manual_transitions(self, name: str) -> list:
        return [t for t in self.transitions(name) if not t.auto]

    def target_for(self, name: str, event: str):
        for t in self.transitions(name):
            if t.event == event:
                return t.target
        return None


def load_lifecycle(path: Path = None) -> Lifecycle:
    if yaml is None:
        raise RuntimeError("需要 pyyaml 才能解析 lifecycle 定義")
    path = path or DEFAULT_LIFECYCLE_PATH
    data = yaml.safe_load(Path(path).read_text(encoding="utf-8")) or {}
    return Lifecycle(data)
