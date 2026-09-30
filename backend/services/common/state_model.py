from dataclasses import dataclass


@dataclass(frozen=True)
class StateModel:
    transitions: dict[str, tuple[str, ...]]
    terminal: tuple[str, ...]
    recovery: dict[str, str]

    def permits(self, before: str, after: str) -> bool:
        return before in self.transitions and (before == after or after in self.transitions[before])

    def require(self, before: str, after: str) -> None:
        if not self.permits(before, after):
            raise ValueError(f"不允许状态转换：{before} -> {after}")
