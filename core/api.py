from abc import ABC, abstractmethod
from typing import Optional

from telegram import Chat, User, Update
from telegram.ext import CallbackContext

from core.exceptions import GameBotException


class Player:
    def __init__(self, user: User):
        self._raw_user = user

    def update_user_info(self, user: User) -> None:
        if user.id == self._raw_user.id:
            raise GameBotException("Users aren't the same")

        self._raw_user = user

    def tell_raw(self, *args, **kwargs) -> None:
        self._raw_user.send_message(*args, **kwargs)

    @property
    def name(self) -> str:
        return self._raw_user.name


class Action:
    pass


class TelegramUpdate(Action):
    def __init__(self, update: Update, context: CallbackContext, sender: Player):
        super().__init__()

        self.sender = sender
        self.raw_update = update
        self.raw_context = context


class Party:
    """
    A party is a group of players.

    They can be seen as a generalization of Telegram chats: each chat can have multiple
    (even overlapping) parties, and parties can have no associated chat (the so-called
    private parties).
    """

    def __init__(self, players: list[Player], leader: Optional[Player] = None, chat: Optional[Chat] = None):
        self.players = players
        self.leader = leader

        self._raw_chat = chat

    def tell_everyone_raw(self, *args, **kwargs) -> None:
        for player in self.players:
            player.tell_raw(*args, **kwargs)

    def announce_raw(self, *args, **kwargs) -> None:
        if self._raw_chat is not None:
            self._raw_chat.send_message(*args, **kwargs)
        else:
            self.tell_everyone_raw(*args, **kwargs)


class GlobalAPI:
    def resolve_username(self, username: str) -> Player:
        raise NotImplementedError()


class Game(ABC):
    def __init__(self, api: GlobalAPI, party: Party):
        self.api = api
        self.party = party
    
    @abstractmethod
    async def handle(self, update: TelegramUpdate) -> None:
        pass
