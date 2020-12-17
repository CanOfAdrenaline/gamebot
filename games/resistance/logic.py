import logging
import random
from enum import Enum
from typing import Optional

from core.api import Player
from games.resistance.exceptions import GameError

MIN_PLAYERS, MAX_PLAYERS = 5, 10

# Party size per round for every possible player count
PARTY_SIZES = {
    5: [2, 3, 2, 3, 3],
    6: [2, 3, 4, 3, 4],
    7: [2, 3, 3, 4, 4],
    8: [3, 4, 4, 5, 5],
    9: [3, 4, 4, 5, 5],
    10: [3, 4, 4, 5, 5]
}

# Number of rounds the side needs to win to win the game
WIN_LIMIT = 3

# Maximum number of failed votes per round. When reached, spies win the round
VOTE_LIMIT = 5

# Minimum number of players that enables the rule which states that the spies must play
# at least 2 black cards in the 4th round to win it
MIN_2IN4TH = 7

logger = logging.getLogger(__name__)


class GameState(Enum):
    NOT_STARTED = 0
    PROPOSAL_PENDING = 1
    PARTY_VOTE_IN_PROGRESS = 2
    PARTY_VOTE_RESULTS = 3
    MISSION_VOTE_IN_PROGRESS = 4
    MISSION_VOTE_RESULTS = 5
    GAME_OVER = 6


class Vote:
    def __init__(self, party: list[Player]):
        self.party = party
        self.ballots: dict[Player, bool] = {}

    @property
    def outcome(self) -> bool:
        # Party is appointed if the majority of players voted affirmative
        values = list(self.ballots.values())
        return values.count(True) > values.count(False)


class Round:
    def __init__(self, winning_count: int):
        self.winning_count = winning_count
        self.votes: list[Vote] = []
        self.ballots: dict[Player, bool] = {}

    @property
    def last_vote(self) -> Optional[Vote]:
        if self.votes:
            return self.votes[-1]
        return None

    @property
    def can_vote(self) -> bool:
        return len(self.votes) < VOTE_LIMIT

    @property
    def outcome(self) -> bool:
        # Spies win if vote limit is exceeded
        if not self.can_vote:
            return False

        # Spies win if they deal a needed number of black cards
        return list(self.ballots.values()).count(False) < self.winning_count


class GameInstance:
    def __init__(self, players: list[Player]):
        self.state = GameState.NOT_STARTED
        self.players: list[Player] = players
        self.spies: list[Player] = []
        self.rounds: list[Round] = []
        self._leader_idx = -1

    def next_state(self) -> None:
        if self.state == GameState.NOT_STARTED:
            if not MIN_PLAYERS <= len(self.players) <= MAX_PLAYERS:
                raise GameError(f"The number of players must be between {MIN_PLAYERS} and {MAX_PLAYERS}!")
            self._assign_spies()
            self._next_round_or_game_over()

        elif self.state == GameState.PARTY_VOTE_RESULTS:
            if self.current_vote.outcome:
                self.state = GameState.MISSION_VOTE_IN_PROGRESS
            else:
                self._next_leader()
                if self.current_round.can_vote:
                    self.state = GameState.PROPOSAL_PENDING
                else:
                    self._next_round_or_game_over()

        elif self.state == GameState.MISSION_VOTE_RESULTS:
            self._next_leader()
            self._next_round_or_game_over()

        else:
            raise GameError(f"Current game state ({self.state}) is changed automatically.")

    def propose_party(self, player: Player, players: list[Player]) -> None:
        self._assert_registered(player)

        if self.state != GameState.PROPOSAL_PENDING:
            raise GameError("Party proposal not pending!")
        if player != self.leader:
            raise GameError("Only leader can propose a party!")
        if len(players) != self.current_party_size:
            raise GameError(f"Party must have {self.current_party_size} members!")

        for player in players:
            if player not in self.players:
                raise GameError(f"Can't propose non-registered player {player.name}!")

        self.current_round.votes.append(Vote(players))
        self.state = GameState.PARTY_VOTE_IN_PROGRESS

    def vote_party(self, player: Player, outcome: bool) -> None:
        self._assert_registered(player)

        if self.state != GameState.PARTY_VOTE_IN_PROGRESS:
            raise GameError("Party vote not in progress!")
        if player in self.current_vote.ballots:
            raise GameError("Can't vote twice!")

        self.current_vote.ballots[player] = outcome
        self._log("Player %s votes %s", player.name, "affirmative" if outcome else "negative")

        # Proceed to the next state when all players voted
        if len(self.current_vote.ballots) >= len(self.players):
            self.state = GameState.PARTY_VOTE_RESULTS
            self._log("Vote over: party is %s", "appointed" if self.current_vote.outcome else "rejected")

    def vote_mission(self, player: Player, outcome: bool) -> None:
        self._assert_registered(player)

        if self.state != GameState.MISSION_VOTE_IN_PROGRESS:
            raise GameError("Mission vote not in progress!")
        if player in self.current_round.ballots:
            raise GameError("Can't vote twice!")

        if player not in self.current_party:
            raise GameError("Only party members can vote!")
        if not outcome and player not in self.spies:
            raise GameError("Only spies can vote black!")

        self.current_round.ballots[player] = outcome
        self._log("Player %s votes %s", player.name, "red" if outcome else "black")

        if len(self.current_round.ballots) >= self.current_party_size:
            self.state = GameState.MISSION_VOTE_RESULTS
            self._log("Round over: mission %s", "successful" if self.current_round.outcome else "failed")

    @property
    def state(self) -> GameState:
        return self._state

    @state.setter
    def state(self, value: GameState) -> None:
        self._state = value
        self._log("State is now %s", value)

    @property
    def current_round(self) -> Optional[Round]:
        if self.state not in [GameState.NOT_STARTED, GameState.GAME_OVER]:
            return self.rounds[-1]
        return None

    @property
    def current_vote(self) -> Optional[Vote]:
        if self.state in [GameState.PARTY_VOTE_IN_PROGRESS, GameState.PARTY_VOTE_RESULTS]:
            return self.current_round.last_vote
        return None

    @property
    def current_party(self) -> Optional[list[Player]]:
        if self.state in [GameState.PARTY_VOTE_IN_PROGRESS, GameState.PARTY_VOTE_RESULTS,
                          GameState.MISSION_VOTE_IN_PROGRESS, GameState.MISSION_VOTE_RESULTS]:
            return self.current_round.last_vote.party
        return None

    @property
    def current_party_size(self) -> Optional[int]:
        if self.state not in [GameState.NOT_STARTED, GameState.GAME_OVER]:
            round_idx = len(self.rounds) - 1
            return PARTY_SIZES[len(self.players)][round_idx]
        return None

    @property
    def current_winning_count(self) -> Optional[int]:
        if self.state not in [GameState.NOT_STARTED, GameState.GAME_OVER]:
            return self.current_round.winning_count
        return None

    @property
    def leader(self) -> Optional[Player]:
        if self.state not in [GameState.NOT_STARTED, GameState.GAME_OVER]:
            return self.players[self._leader_idx]
        return None

    @property
    def outcome(self) -> Optional[bool]:
        outcomes = [x.outcome for x in self.rounds]
        resistance_wins = outcomes.count(True)
        spy_wins = outcomes.count(False)

        if resistance_wins >= WIN_LIMIT:
            return True
        elif spy_wins >= WIN_LIMIT:
            return False
        return None

    def _assert_registered(self, player: Player) -> None:
        if player not in self.players:
            raise GameError("You are not registered!")

    def _assign_spies(self) -> None:
        # According to the official rules, one third of players (rounded up) are spies
        spy_count = (len(self.players) + 2) // 3

        self.spies = random.sample(self.players, spy_count)
        self._log("Spies appointed: %s", list(x.name for x in self.spies))

    def _next_leader(self) -> None:
        self._leader_idx = (self._leader_idx + 1) % len(self.players)

    def _next_round_or_game_over(self) -> None:
        if self.outcome is None:
            winning_count = 1
            if len(self.players) >= MIN_2IN4TH and len(self.rounds) == 3:
                winning_count = 2
            self.rounds.append(Round(winning_count))

            self.state = GameState.PROPOSAL_PENDING
            self._log("Round %s begins", len(self.rounds))

        else:
            self.state = GameState.GAME_OVER
            self._log("The game is over: %s", "resistance wins" if self.outcome else "spies win")

    def _log(self, message: str, *args) -> None:
        # TODO: Log game ID
        logger.info(message, *args)
