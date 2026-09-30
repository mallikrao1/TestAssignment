"""JSON frontends; scheduling and stopping rules deliberately live outside the engine."""

import argparse
import json
import random
import sys
from pathlib import Path

from hanoi_crossing.engine import Action, new_game, observe, step
from hanoi_crossing.policy import choose_random


class InputError(ValueError):
    """A malformed CLI argument or replay document."""


class Parser(argparse.ArgumentParser):
    def error(self, message):
        raise InputError(message)


def main(argv=None):
    """Write one JSON result, or one JSON error on stderr with exit code 2."""
    parser = Parser(description="Replay or randomly play Hanoi Crossing.")
    commands = parser.add_subparsers(dest="command", required=True)
    replay = commands.add_parser("replay", help="Replay a JSON file; use - for stdin.")
    replay.add_argument("path", help="Replay JSON file, or - for stdin")
    play = commands.add_parser("random", help="Both players select uniform legal actions.")
    play.add_argument("--disks", type=int, default=3)
    play.add_argument("--seed", type=int, default=0)
    play.add_argument("--max-turns", type=int, default=1000)
    play.add_argument("--turn-order", default="AB", help="Repeated external schedule, e.g. AAB")
    try:
        args = parser.parse_args(argv)
        if args.command == "replay":
            source = (
                sys.stdin.read().lstrip("\ufeff")
                if args.path == "-"
                else Path(args.path).read_text(encoding="utf-8-sig")
            )
            result = run_replay(json.loads(source, object_pairs_hook=unique_object))
        else:
            result = run_random(args.disks, args.seed, args.max_turns, args.turn_order)
        print(json.dumps(result, indent=2))
        return 0
    except (ValueError, OSError, UnicodeError) as error:
        print(json.dumps({"error": {"type": "input_error", "message": str(error)}}), file=sys.stderr)
        return 2


def run_replay(document):
    """Validate the entire document before applying even its first move."""
    actions = validate_replay(document)
    state = new_game(document["disk_count"])
    events = []
    for player, action in zip(document["turn_order"], actions):
        if state.terminal:
            break
        transition = step(state, player, action)
        events.append(
            {
                "turn": len(events) + 1,
                "player": player,
                "move": move_dict(action),
                "accepted": transition.accepted,
                "reason": transition.reason,
            }
        )
        state = transition.state
    return {
        "mode": "replay",
        "status": "finished" if state.terminal else "unfinished",
        "stop_reason": "win" if state.terminal else "turn_order_exhausted",
        "winners": list(state.winners),
        "turns_consumed": len(events),
        "turns_ignored": len(actions) - len(events),
        "final_state": state.to_dict(),
        "events": events,
    }


def run_random(disks, seed, max_turns, turn_order):
    if max_turns < 0:
        raise InputError("--max-turns must be at least 0")
    if not turn_order or any(player not in "AB" for player in turn_order):
        raise InputError("--turn-order must be a nonempty sequence of A and B")
    state = new_game(disks)
    rng = random.Random(seed)
    events = []
    for turn in range(max_turns):
        if state.terminal:
            break
        player = turn_order[turn % len(turn_order)]
        action = choose_random(observe(state, player), rng)
        transition = step(state, player, action)
        events.append(
            {
                "turn": turn + 1,
                "player": player,
                "move": move_dict(action),
                "accepted": transition.accepted,
                "reason": transition.reason,
            }
        )
        state = transition.state
    return {
        "mode": "random",
        "status": "finished" if state.terminal else "unfinished",
        "stop_reason": "win" if state.terminal else "turn_limit",
        "seed": seed,
        "schedule": turn_order,
        "winners": list(state.winners),
        "turns_consumed": len(events),
        "turns_ignored": 0,
        "final_state": state.to_dict(),
        "events": events,
        "replay": {
            "disk_count": disks,
            "turn_order": [event["player"] for event in events],
            "moves": [event["move"] for event in events],
        },
    }


def validate_replay(document):
    if not isinstance(document, dict) or set(document) != {"disk_count", "turn_order", "moves"}:
        raise InputError("Replay must contain exactly disk_count, turn_order, and moves")
    if type(document["disk_count"]) is not int or document["disk_count"] < 1:
        raise InputError("disk_count must be a positive integer")
    if not isinstance(document["turn_order"], list) or any(
        player not in ("A", "B") for player in document["turn_order"]
    ):
        raise InputError("turn_order must be an array of A or B strings")
    if not isinstance(document["moves"], list):
        raise InputError("moves must be an array")
    if len(document["turn_order"]) != len(document["moves"]):
        raise InputError("turn_order and moves must have equal lengths")
    return tuple(parse_move(move, index + 1) for index, move in enumerate(document["moves"]))


def parse_move(move, turn):
    if not isinstance(move, dict) or "action" not in move or set(move) - {"action", "pole"}:
        raise InputError(f"Move {turn} must contain action and optionally pole")
    if not isinstance(move["action"], str):
        raise InputError(f"Move {turn}: action must be a string")
    if "pole" in move and type(move["pole"]) is not int:
        raise InputError(f"Move {turn}: pole must be an integer")
    if move["action"] in ("lift", "place") and "pole" not in move:
        raise InputError(f"Move {turn}: lift and place require pole")
    return Action(move["action"], move.get("pole"))


def move_dict(action):
    return {"action": action.kind, **({"pole": action.pole} if action.pole is not None else {})}


def unique_object(pairs):
    document = {}
    for key, value in pairs:
        if key in document:
            raise InputError(f"Duplicate JSON key: {key}")
        document[key] = value
    return document
