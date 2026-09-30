"""Deterministic rules, immutable snapshots, and private player observations.

Scheduling, elapsed turns, I/O, and policies belong to callers. All stacks are
bottom-to-top. An invalid action returns the original state unchanged.
"""

from dataclasses import dataclass

PLAYERS = ("A", "B")
POLES = ("1a", "2", "3a", "1b", "3b")
VISIBLE = ((0, 1, 2), (3, 1, 4))


@dataclass(frozen=True, slots=True)
class Action:
    """A relative pole number (1, 2, 3); skip takes no pole.

    Values are deliberately checked by step, so illegal attempted actions can
    consume a turn without being confused with state-construction errors.
    """

    kind: str
    pole: int | None = None


@dataclass(frozen=True, slots=True)
class GameState:
    """Privileged full state. Never pass this snapshot to an untrusted player."""

    disk_count: int
    poles: tuple[tuple[int, ...], ...]
    hands: tuple[int | None, int | None]

    def __post_init__(self) -> None:
        if type(self.disk_count) is not int or self.disk_count < 1:
            raise ValueError("disk_count must be a positive integer")
        if type(self.poles) is not tuple or len(self.poles) != 5:
            raise ValueError("poles must be a tuple of five stacks")
        if type(self.hands) is not tuple or len(self.hands) != 2:
            raise ValueError("hands must be a tuple of two disks or None")
        for stack in self.poles:
            if type(stack) is not tuple or any(type(disk) is not int for disk in stack):
                raise ValueError("each stack must be a tuple of integer disks")
            if any(lower <= upper for lower, upper in zip(stack, stack[1:])):
                raise ValueError("stacks must be strictly decreasing bottom-to-top")
        if any(disk is not None and type(disk) is not int for disk in self.hands):
            raise ValueError("each hand must contain an integer disk or None")
        disks = [disk for stack in self.poles for disk in stack]
        disks.extend(disk for disk in self.hands if disk is not None)
        if sorted(disks) != list(range(1, 2 * self.disk_count + 1)):
            raise ValueError("every disk from 1 through 2 * disk_count must occur exactly once")

    @property
    def winners(self) -> tuple[str, ...]:
        """Both players are checked, including when the other player just acted."""
        return tuple(
            player
            for index, player in enumerate(PLAYERS)
            if self.hands[index] is None
            and not self.poles[VISIBLE[index][0]]
            and not self.poles[1]
            and self.poles[VISIBLE[index][2]]
        )

    @property
    def terminal(self) -> bool:
        return bool(self.winners)

    def to_dict(self) -> dict:
        """A detached, JSON-compatible snapshot for trusted persistence/replay."""
        return {
            "disk_count": self.disk_count,
            "poles": {name: list(stack) for name, stack in zip(POLES, self.poles)},
            "hands": dict(zip(PLAYERS, self.hands)),
        }

    @classmethod
    def from_dict(cls, snapshot: dict) -> "GameState":
        """Restore and validate a full snapshot; reject unknown/missing fields."""
        if not isinstance(snapshot, dict) or set(snapshot) != {"disk_count", "poles", "hands"}:
            raise ValueError("snapshot must contain disk_count, poles, and hands")
        if not isinstance(snapshot["poles"], dict) or set(snapshot["poles"]) != set(POLES):
            raise ValueError("snapshot must contain exactly the five named poles")
        if not isinstance(snapshot["hands"], dict) or set(snapshot["hands"]) != set(PLAYERS):
            raise ValueError("snapshot must contain exactly the two named hands")
        if any(not isinstance(snapshot["poles"][name], list) for name in POLES):
            raise ValueError("snapshot stacks must be JSON arrays")
        return cls(
            snapshot["disk_count"],
            tuple(tuple(snapshot["poles"][name]) for name in POLES),
            (snapshot["hands"]["A"], snapshot["hands"]["B"]),
        )


@dataclass(frozen=True, slots=True)
class Observation:
    """Everything a player sees; no opponent private poles or opponent hand.

    The initial disk count and terminal winners are public information.
    """

    player: str
    disk_count: int
    poles: tuple[tuple[int, ...], ...]
    hand: int | None
    winners: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class Transition:
    state: GameState
    accepted: bool
    reason: str | None = None


def new_game(disk_count: int = 3) -> GameState:
    """Start with odd/even disks on each player's pole 1."""
    if type(disk_count) is not int or disk_count < 1:
        raise ValueError("disk_count must be a positive integer")
    return GameState(
        disk_count,
        (
            tuple(range(2 * disk_count - 1, 0, -2)),
            (),
            (),
            tuple(range(2 * disk_count, 0, -2)),
            (),
        ),
        (None, None),
    )


def observe(state: GameState, player: str) -> Observation:
    index = _player_index(player)
    return Observation(
        player,
        state.disk_count,
        tuple(state.poles[pole] for pole in VISIBLE[index]),
        state.hands[index],
        state.winners,
    )


def legal_actions(observation: Observation) -> tuple[Action, ...]:
    """Symbolic action mask source; legal choices depend only on visible state."""
    if observation.winners:
        return ()
    return (Action("skip"),) + tuple(
        Action("lift" if observation.hand is None else "place", pole)
        for pole, stack in enumerate(observation.poles, start=1)
        if (bool(stack) if observation.hand is None else not stack or observation.hand < stack[-1])
    )


def step(state: GameState, player: str, action: Action) -> Transition:
    """Apply exactly one supplied player's action; never infer whose turn is next.

    Illegal/terminal attempts return accepted=False and preserve state identity.
    The scheduler still consumes their turn. Invalid player identifiers and
    non-Action arguments are API errors, not game moves.
    """
    index = _player_index(player)
    if not isinstance(action, Action):
        raise TypeError("action must be an Action")
    if state.terminal:
        return Transition(state, False, "game_over")
    if action.kind not in ("skip", "lift", "place"):
        return Transition(state, False, "unknown_action")
    if action.kind == "skip":
        return Transition(state, action.pole is None, None if action.pole is None else "skip_has_pole")
    if type(action.pole) is not int or action.pole not in (1, 2, 3):
        return Transition(state, False, "invalid_pole")
    pole = VISIBLE[index][action.pole - 1]
    stack = state.poles[pole]
    hand = state.hands[index]
    if action.kind == "lift":
        if hand is not None:
            return Transition(state, False, "hand_full")
        if not stack:
            return Transition(state, False, "empty_pole")
    if action.kind == "place":
        if hand is None:
            return Transition(state, False, "empty_hand")
        if stack and hand >= stack[-1]:
            return Transition(state, False, "larger_on_smaller")
    updated_stack = stack[:-1] if action.kind == "lift" else stack + (hand,)
    updated_hand = stack[-1] if action.kind == "lift" else None
    return Transition(
        GameState(
            state.disk_count,
            tuple(updated_stack if number == pole else current for number, current in enumerate(state.poles)),
            tuple(updated_hand if number == index else current for number, current in enumerate(state.hands)),
        ),
        True,
    )


def _player_index(player: str) -> int:
    if player not in PLAYERS:
        raise ValueError("player must be A or B")
    return PLAYERS.index(player)
