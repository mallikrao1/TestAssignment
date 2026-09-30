"""Observation-only policies with a symbolic legality boundary.

The optional score adapter is neural-ready, not a trained neural model. A caller
may supply neural-network logits or any other real scores; the engine remains
the authority on legal actions. Masking guarantees legality, not strong play.
"""

from collections.abc import Iterable
from dataclasses import dataclass
from math import inf
from numbers import Real
from random import Random

from .engine import Action, Observation, legal_actions


ACTIONS = (
    Action("skip"),
    Action("lift", 1),
    Action("lift", 2),
    Action("lift", 3),
    Action("place", 1),
    Action("place", 2),
    Action("place", 3),
)


@dataclass(frozen=True, slots=True)
class PolicyInput:
    """Immutable agent features and mask in the public ``ACTIONS`` order.

    Features contain relative poles 1, 2, 3, each bottom-to-top and padded to
    2N entries, followed by the held disk. Disk sizes are divided by 2N; zeros
    represent empty slots or an empty hand. The width is 6N + 1, fixed for a
    chosen N. Player identity and all hidden opponent information are omitted.
    """

    features: tuple[float, ...]
    action_mask: tuple[bool, ...]


def encode(observation: Observation) -> PolicyInput:
    """Encode a private observation; terminal observations have an all-false mask."""
    scale = 2 * observation.disk_count
    legal = legal_actions(observation)
    return PolicyInput(
        tuple(
            disk / scale
            for pole in observation.poles
            for disk in pole + (0,) * (scale - len(pole))
        )
        + ((observation.hand or 0) / scale,),
        tuple(action in legal for action in ACTIONS),
    )


def choose_random(observation: Observation, rng: Random) -> Action:
    """Sample uniformly from all legal actions, including skip, using caller RNG."""
    legal = legal_actions(observation)
    if not legal:
        raise ValueError("cannot choose an action for a terminal observation")
    return rng.choice(legal)


def choose_scored(observation: Observation, scores: Iterable[float]) -> Action:
    """Select the highest-scored legal action, breaking ties by ACTIONS order.

    Supply seven finite real scores, including for illegal actions. Booleans,
    NaN, and infinities are rejected. This adapter performs no model inference
    or training and accepts no full game state or opponent-private information.
    """
    legal = legal_actions(observation)
    if not legal:
        raise ValueError("cannot choose an action for a terminal observation")
    values = tuple(scores)
    if len(values) != len(ACTIONS):
        raise ValueError(f"expected {len(ACTIONS)} action scores")
    if any(
        isinstance(value, bool)
        or not isinstance(value, Real)
        or value != value
        or value in (inf, -inf)
        for value in values
    ):
        raise ValueError("action scores must all be finite real numbers")
    return ACTIONS[
        max(
            (index for index, action in enumerate(ACTIONS) if action in legal),
            key=values.__getitem__,
        )
    ]
