from collections import defaultdict
from typing import Callable, Optional, Iterable

from telegram import User, Chat

from core.api import Game, Party, Player
from core.exceptions import GameBotException


class GameManager:
    def __init__(self):
        self._game_ctors = {}
        self._games = {}
        self._next_game_id = 0
        self._usernames = {}
        self._player_games = defaultdict(set)

    def add_game(self, game_name: str, ctor: Callable[[], Game]) -> None:
        # TODO: Find a way to manage global commands and settings
        self._game_ctors[game_name] = ctor

    def update_user_info(self, user: User) -> None:
        if user.username is None:
            raise GameBotException("Users without usernames not supported yet")

        if user.username not in self._usernames:
            self._usernames[user.username] = Player(user)
        else:
            self._usernames[user.username].update_user_info(user)

    def new_game(self, game_name: str, players: list[Player], leader: Optional[Player] = None, chat: Optional[Chat] = None) -> Game:
        if game_name not in self._game_ctors:
            raise GameBotException(f"No such game: {game_name}")

        party = Party(players, leader, chat)

        game_id = self._generate_game_id()
        game_ctor = self._game_ctors[game_name]

        # TODO: Pass API object to game constructor
        game = game_ctor(None, party)
        self._games[game_id] = game

        for player in players:
            self._player_games[player].add(game)

        # TODO: Initialize game and player state
        
        return game
    
    def get_player_games(self, player: Player) -> Iterable[Game]:
        return self._player_games[player]

    def resolve_username(self, username: str) -> Player:
        if username not in self._usernames:
            raise GameBotException(f"No such user known: @{username}")

        return self._usernames[username]

    def _generate_game_id(self) -> int:
        # TODO: More sophisticated game ID generation logic
        game_id = self._next_game_id
        self._next_game_id += 1
        return game_id
