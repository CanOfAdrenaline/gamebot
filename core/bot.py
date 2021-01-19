import asyncio
import logging

from telegram import Update, MessageEntity, Chat
from telegram.ext import Updater, CommandHandler, MessageHandler, Filters, CallbackContext, \
    TypeHandler, ConversationHandler

from core.api import TelegramUpdate, Player
from core.gamemanager import GameManager

logger = logging.getLogger(__name__)

DISAMBIGUATION = 0


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

        d.add_handler(CommandHandler('start', self._handle_start))
        d.add_handler(CommandHandler('new_game', self._handle_new_game))

        d.add_handler(ConversationHandler(
            entry_points=[MessageHandler(Filters.all, self._handle_message)],
            states={
                DISAMBIGUATION: [MessageHandler(Filters.text, self._handle_disambiguation)]
            },
            fallbacks=[MessageHandler(Filters.all, self._handle_disambiguation_fallback)]
        ))
        d.add_handler(TypeHandler(Update, self._handle_update))

        d.add_error_handler(self._handle_error)

        self.game_manager = GameManager()
        self.scheduler = Scheduler()

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

    @staticmethod
    def _handle_start(update: Update, context: CallbackContext) -> None:
        # TODO: More meaningful start message
        update.message.reply_text("Hello there!")

    def _handle_new_game(self, update: Update, context: CallbackContext) -> None:
        # TODO: Handle incorrect input
        game_name = update.message.text.split()[1]

        users = set()

        leader = update.effective_user
        users.add(leader)

        for entity in update.message.entities:
            if entity.type != MessageEntity.MENTION:
                pass
            users.add(entity.user)

        if update.effective_chat in [Chat.GROUP, Chat.SUPERGROUP]:
            chat = update.effective_chat
        else:
            chat = None

        game = self.game_manager.new_game(game_name, users, leader, chat)

        if 'games' not in context.user_data:
            context.user_data['games'] = []
        context.user_data['games'].append(game)

    def _handle_message(self, update: Update, context: CallbackContext) -> int:
        sender = Player(update.effective_user)
        tg_update = TelegramUpdate(update, context, sender)

        relevant_games = {}
        for game in context.user_data.get('games', []):
            handlers = game.handle(tg_update)
            if not handlers:
                break
            relevant_games[game] = handlers

        if not relevant_games:
            return ConversationHandler.END

        if len(relevant_games) == 1:
            handlers = next(iter(relevant_games.values()))
            for handler in handlers:
                handler()
            return ConversationHandler.END

        context.user_data['pending_update'] = tg_update

        # TODO: More meaningful disambiguation message
        update.message.reply_text("Disambiguation")

        return DISAMBIGUATION

    def _handle_disambiguation(self, update: Update, context: CallbackContext) -> None:
        update.message.reply_text("Disambiguation implementation")

    def _handle_disambiguation_fallback(self, update: Update, context: CallbackContext) -> None:
        update.message.reply_text("Disambiguation fallback")

    def _handle_update(self, update: Update, context: CallbackContext) -> None:
        update.message.reply_text("Update")

    @staticmethod
    def _handle_error(update: Update, context: CallbackContext) -> None:
        logger.error(msg="Exception while handling an update:", exc_info=context.error)
