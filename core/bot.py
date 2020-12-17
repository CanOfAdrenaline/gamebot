import asyncio
import logging
from collections import Callable

from telegram import Update, Chat
from telegram.ext import Updater, CommandHandler, MessageHandler, Filters, CallbackContext, CallbackQueryHandler

from core.api import TelegramUpdate, Game
from core.gamemanager import GameManager

logger = logging.getLogger(__name__)


class Scheduler:
    def __init__(self):
        self.loop = asyncio.get_event_loop()

    def run(self) -> None:
        try:
            self.loop.run_forever()
        finally:
            self.loop.run_until_complete(self.loop.shutdown_asyncgens())
            self.loop.close()

    def schedule(self, coro, *args, **kwargs) -> None:
        asyncio.run_coroutine_threadsafe(coro(*args, **kwargs), self.loop)


class Bot:
    def __init__(self, token: str):
        self.token = token
        self.updater = Updater(token=self.token)

        d = self.updater.dispatcher

        # Group -1 - utility handlers
        d.add_handler(MessageHandler(Filters.all, self._update_user), group=-1)

        # Default group (0) - main handlers
        d.add_handler(CommandHandler('start', self._handle_start))
        d.add_handler(CommandHandler('new_game', self._handle_new_game))

        # TODO: Smarter command handling
        d.add_handler(MessageHandler(Filters.all, self._handle_update))

        # TODO: Smarter callback handling
        d.add_handler(CallbackQueryHandler(self._handle_update))

        # TODO: Register handlers specified by games

        d.add_error_handler(self._handle_error)

        self.gm = GameManager()
        self.scheduler = Scheduler()

    def add_game(self, game_name: str, ctor: Callable[[], Game]) -> None:
        self.gm.add_game(game_name, ctor)

    def run(self) -> None:
        # Start updater in separate thread
        self.updater.start_polling()

        # Run scheduler in the main thread
        try:
            self.scheduler.run()
        finally:
            self.updater.stop()

    def run_webhook(self, fqdn: str, ip: str, port: int = 80) -> None:
        self.updater.start_webhook(ip, port, url_path=self.token)
        self.updater.bot.set_webhook(f'https://{fqdn}/{self.token}')

        try:
            self.scheduler.run()
        finally:
            self.updater.bot.delete_webhook()
            self.updater.stop()

    def _update_user(self, update: Update, context: CallbackContext) -> None:
        user = update.effective_user
        if user is not None:
            self.gm.update_user_info(user)

    def _handle_new_game(self, update: Update, context: CallbackContext) -> None:
        # TODO: Replace with more sophisticated logic (ConversationHandler maybe?)
        args = update.message.text.split()

        game_name = args[1]
        leader_username = update.effective_user.username
        if update.effective_chat.type in [Chat.GROUP, Chat.SUPERGROUP]:
            chat = update.effective_chat
        else:
            chat = None

        # TODO: Support users that do not have usernames
        member_usernames = [s.removeprefix("@") for s in args[2:]]
        if leader_username not in member_usernames:
            member_usernames.append(leader_username)

        members = [self.gm.resolve_username(s) for s in member_usernames]
        leader = self.gm.resolve_username(leader_username)

        self.gm.new_game(game_name, members, leader, chat)

    def _handle_update(self, update: Update, context: CallbackContext) -> None:
        user = update.effective_user
        player = self.gm.resolve_username(user.username)

        relevant_games = []
        for game in self.gm.get_player_games(player):
            # TODO: Check if game can handle update
            relevant_games.append(game)

        # TODO: Ask user which game should be chosen
        relevant_game = relevant_games[0]

        action = TelegramUpdate(update, context, player)

        # TODO: Find a way to redirect exceptions to player
        self.scheduler.schedule(relevant_game.handle, action)

    @staticmethod
    def _handle_start(update: Update, context: CallbackContext) -> None:
        # TODO: More meaningful start message
        update.message.reply_text("Hello there!")

    @staticmethod
    def _handle_error(update: Update, context: CallbackContext) -> None:
        logger.error(msg="Exception while handling an update:", exc_info=context.error)
