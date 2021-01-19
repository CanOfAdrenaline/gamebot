from typing import Iterable, Callable

from core.api import Game, Action


class Chess(Game):
    def handle(self, action: Action) -> Iterable[Callable[[], None]]:
        pass
