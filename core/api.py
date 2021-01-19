from abc import ABC, abstractmethod
from collections import defaultdict
from functools import wraps, partial
from typing import Callable, Optional, Iterable

from telegram import Chat, User, Update
from telegram.ext import CallbackContext, Handler


class Player:
    def __init__(self, user: User):
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

    def __init__(self, players: Iterable[Player], leader: Optional[Player] = None, chat: Optional[Chat] = None):
        self.players = list(players)
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
    def handle(self, action: Action) -> Iterable[Callable[[], None]]:
        return []


class PTBHandlerGame(Game):
    def __init__(self, api: GlobalAPI, party: Party):
        super().__init__(api, party)

        self.groups = defaultdict(list)

    def add_handler(self, handler: Handler, group: int = 0):
        self.groups[group].append(handler)

    def handle(self, action: Action) -> Iterable[Callable[[], None]]:
        if not isinstance(action, TelegramUpdate):
            raise NotImplementedError()

        callables = []

        for _, handlers in sorted(self.groups.items()):
            for handler in handlers:
                check = handler.check_update(action.raw_update)
                if check is not None and check is not False:
                    bound_handler = partial(
                        handler.handle_update,
                        action.raw_update, action.raw_context.dispatcher, check, action.raw_context)
                    callables.append(bound_handler)

        return callables


def ptb_handler(handler):
    @wraps(handler)
    def wrapped_handler(update: Update, context: CallbackContext):
        return handler(TelegramUpdate(update, context, Player(update.effective_user)))

    return wrapped_handler


def ptb_handler_method(handler):
    @wraps(handler)
    def wrapped_handler(self, update: Update, context: CallbackContext):
        return handler(self, TelegramUpdate(update, context, Player(update.effective_user)))

    return wrapped_handler