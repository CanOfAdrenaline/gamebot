from typing import Callable, Optional, Iterable

from telegram import Chat, User

from core.api import Game, Party, Player
from core.exceptions import GameBotException


class GameManager:
    def __init__(self):
        self._game_ctors = {}
        self._games = {}
        self._next_game_id = 0

    def add_game(self, game_name: str, ctor: Callable[[], Game]) -> None:
        # TODO: Find a way to manage global commands and settings
        self._game_ctors[game_name] = ctor

    def new_game(self, game_name: str, users: Iterable[User], leader: Optional[User] = None, chat: Optional[Chat] = None) -> Game:
        if game_name not in self._game_ctors:
            raise GameBotException(f"No such game: {game_name}")

        players = [Player(u) for u in users]
        party = Party(players, Player(leader), chat)

        game_id = self._generate_game_id()
        game_ctor = self._game_ctors[game_name]

        # TODO: Pass API object to game constructor
        # TODO: Pass Game ID to game constructor
        game = game_ctor(None, party)
        self._games[game_id] = game

        # TODO: Initialize game and player state
        
        return game

    def _generate_game_id(self) -> int:
        # TODO: More sophisticated game ID generation logic
        game_id = self._next_game_id
        self._next_game_id += 1
        return game_id
