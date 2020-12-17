import random

from telegram import InlineKeyboardMarkup, InlineKeyboardButton

from core.api import Game, TelegramUpdate, Action, GlobalAPI, Party
from games.resistance.logic import GameInstance, GameState
from games.resistance.exceptions import GameError


class Resistance(Game):
    # TODO: Get rid of raw API calls
    # TODO: Refactor callbacks

    def __init__(self, api: GlobalAPI, party: Party):
        super().__init__(api, party)

        self.game = GameInstance(party.players)
        self.start_game()

    async def handle(self, action: Action) -> None:
        # TODO: Implement command and callback handlers
        raise NotImplementedError()

    def start_game(self) -> None:
        self.game.next_state()

        reply_markup = InlineKeyboardMarkup([
            [InlineKeyboardButton("Tap here", callback_data='resistance_get_role')]
        ])
        self.party.announce_raw(
            "_The game has started!_ 😱\n"
            "\n"
            f"There are {len(self.game.spies)} spies. Tap the button below to find out your role.",
            parse_mode='markdown',
            reply_markup=reply_markup)

        self._show_round_info()
        self._show_proposal_prompt()

    def select(self, update: TelegramUpdate) -> None:
        # TODO: Refactor the party selection logic
        raw_args = [x.strip() for x in update.raw_update.message.text.split()[1:]]

        party = []
        for arg in raw_args:
            if not arg:
                continue
            if arg.startswith('@'):
                username = arg[1:]
                try:
                    party.append(self.api.resolve_username(username))
                except KeyError:
                    raise GameError(f"Can't propose non-registered user @{username}!")
            elif arg.isdigit():
                idx = int(arg)
                if not 1 <= idx <= len(self.game.players):
                    raise GameError(f"There is no player with index {idx}.")
                party.append(self.game.players[idx - 1])
            else:
                raise GameError(f"Invalid argument: {arg}")

        self.game.propose_party(update.sender, party)

        if self.game.state == GameState.PARTY_VOTE_IN_PROGRESS:
            self._show_party_vote_prompt()

    def get_role(self, update: TelegramUpdate) -> None:
        if update.sender in self.game.spies:
            response = "⚫️ Spy"
            if len(self.game.spies) > 1:
                spy_list = ", ".join(spy.name for spy in self.game.spies if spy != update.sender)
                response += f" /w {spy_list}"
        else:
            response = "🔴 Resistance member"

        update.raw_update.callback_query.answer(response)

    def party_vote(self, update: TelegramUpdate) -> None:
        query = update.raw_update.callback_query
        affirmative = query.data == 'resistance_party_vote_affirmative'
        self.game.vote_party(update.sender, affirmative)

        if affirmative:
            query.answer("Voted 👍")
        else:
            query.answer("Voted 👎")

        query.message.edit_text(
            self._get_party_vote_message(),
            parse_mode='markdown',
            reply_markup=self._construct_party_vote_markup())

        if self.game.state != GameState.PARTY_VOTE_RESULTS:
            return

        self._report_party_vote_outcome()
        prev_round_no = len(self.game.rounds)
        self.game.next_state()

        if len(self.game.rounds) != prev_round_no:
            self.party.announce_raw(
                "*Maximum number of failed votes reached. Spies win the round.*",
                parse_mode='markdown')
            self._show_round_info()

        if self.game.state == GameState.PROPOSAL_PENDING:
            self._show_proposal_prompt()
        elif self.game.state == GameState.MISSION_VOTE_IN_PROGRESS:
            self._show_mission_vote_prompt()
        elif self.game.state == GameState.GAME_OVER:
            self._report_game_outcome()

    def mission_vote(self, update: TelegramUpdate) -> None:
        query = update.raw_update.callback_query
        red = query.data == 'resistance_mission_vote_red'
        self.game.vote_mission(update.sender, red)

        if red:
            query.answer("Voted 🔴")
        else:
            query.answer("Voted ⚫️")

        query.message.edit_text(
            self._get_mission_vote_message(),
            parse_mode='markdown',
            reply_markup=self._construct_mission_vote_markup())

        if self.game.state != GameState.MISSION_VOTE_RESULTS:
            return

        self._report_mission_vote_outcome()
        self.game.next_state()
        if self.game.state == GameState.PROPOSAL_PENDING:
            self._show_round_info()
            self._show_proposal_prompt()
        elif self.game.state == GameState.GAME_OVER:
            self._report_game_outcome()

    def _show_round_info(self) -> None:
        self.party.announce_raw(
            f"▪️ *ROUND {len(self.game.rounds)}* ▪️\n"
            f"• The party must consist of *{self.game.current_party_size}* player(s).\n"
            f"• Spies need to play *at least {self.game.current_winning_count}* black card(s) to win.",
            parse_mode='markdown')

    def _show_proposal_prompt(self) -> None:
        player_list = "\n".join(f"{i}. {x.name}" for i, x in enumerate(self.game.players, 1))
        self.party.announce_raw(
            f"{self.game.leader.name}, you are the leader now.\n"
            f"Please select *{self.game.current_party_size}* player(s) from the list:\n"
            "\n"
            f"{player_list}\n"
            "\n"
            "To select a party, send /select followed by space-separated indices (or usernames) of players.",
            parse_mode='markdown'
        )

    def _show_party_vote_prompt(self) -> None:
        self.party.announce_raw(
            self._get_party_vote_message(),
            parse_mode='markdown',
            reply_markup=self._construct_party_vote_markup())

    def _show_mission_vote_prompt(self) -> None:
        self.party.announce_raw(
            self._get_mission_vote_message(),
            parse_mode='markdown',
            reply_markup=self._construct_mission_vote_markup())

    def _report_party_vote_outcome(self) -> None:
        if self.game.current_vote.outcome:
            caption = "Vote succeeded!"
        else:
            caption = "Vote failed."

        vote_list = "\n".join(
            f"{player.name}: {'👍' if ballot else '👎'}"
            for player, ballot in self.game.current_vote.ballots.items())

        self.party.announce_raw(f"*{caption}*\n{vote_list}", parse_mode='markdown')

    def _report_mission_vote_outcome(self) -> None:
        if self.game.current_round.outcome:
            who_won = "Resistance"
        else:
            who_won = "Spies"
        caption = f"{who_won} won the round."

        votes = list(self.game.current_round.ballots.values())
        random.shuffle(votes)
        vote_list = "".join("🔴" if x else "⚫️" for x in votes)

        self.party.announce_raw(f"*{caption}*\n{vote_list}", parse_mode='markdown')

    def _report_game_outcome(self) -> None:
        if self.game.outcome:
            message = "Resistance won the game!"
        else:
            message = "Spies won the game!"
        self.party.announce_raw(f"*{message}*", parse_mode='markdown')

    def _get_party_vote_message(self) -> str:
        party = ", ".join(x.name for x in self.game.current_party)
        return (
            "▪️ *VOTING* ▪️\n"
            f"Please vote for party proposal: {party}\n"
            "\n"
            f"*{len(self.game.current_vote.ballots)}* out of *{len(self.game.players)}* player(s) voted."
        )

    def _get_mission_vote_message(self) -> str:
        return (
            "▪️ *MISSION* ▪️\n"
            "Party members, please vote.\n"
            "Spies can play both colors, resistance members can only play red.\n"
            "\n"
            f"*{len(self.game.current_round.ballots)}* out of *{self.game.current_party_size}* player(s) voted."
        )

    @staticmethod
    def _construct_party_vote_markup() -> InlineKeyboardMarkup:
        return InlineKeyboardMarkup([
            [InlineKeyboardButton("👍", callback_data='party_vote_affirmative'),
             InlineKeyboardButton("👎", callback_data='party_vote_negative')]
        ])

    @staticmethod
    def _construct_mission_vote_markup() -> InlineKeyboardMarkup:
        return InlineKeyboardMarkup([
            [InlineKeyboardButton("🔴", callback_data='mission_vote_red'),
             InlineKeyboardButton("⚫️", callback_data='mission_vote_black')]
        ])
