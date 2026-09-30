# Hanoi Crossing

A reusable Python implementation of Hanoi Crossing v1.1, with JSON replay and
seeded random play. The deterministic symbolic engine is **201 physical Python
lines**, including docstrings and blank lines, below the 500-line limit.
There are no runtime or test dependencies outside the standard library.

## Run

Requires Python 3.11+ and [uv](https://docs.astral.sh/uv/). The project pins Python
3.14 for the default development environment; the code also supports 3.11.

```sh
uv sync --locked
uv run hanoi-crossing replay examples/example-win.json
uv run hanoi-crossing random --disks 3 --seed 42 --max-turns 1000
uv run python -m unittest discover -s tests -v
```

`uv run python -m hanoi_crossing` is equivalent to the installed command.
Without uv, install with `python -m pip install -e .` inside your own virtual
environment, then run `python -m hanoi_crossing ...` and the same unittest command.
Build distributable wheel/source archives with `uv build`.

## Rules and interpretations

Each player starts with `N` disks on their private pole 1: A has odd sizes
`1, 3, ..., 2N-1`, B has even sizes `2, 4, ..., 2N`. Smaller numbers mean smaller
disks. Each player sees their own poles 1 and 3, the one shared pole 2, and their
own hand. On an externally scheduled turn they lift one top disk, place their
held disk, or skip. A placed disk must be smaller than the destination's top.

Choices for cases the supplied rules leave open:

| Question | Decision |
| --- | --- |
| Is an empty board a win? | No. Own pole 3 must be nonempty; own pole 1, shared pole 2, and own hand must all be empty. |
| Must players keep their original disks? | No. Odd/even sizes determine initialization only. Either player can take a shared disk of either parity; any disks on pole 3 can satisfy victory. |
| Whose win is checked? | Both players, after every accepted state change. Lifting the final shared disk can make the **other** player win. |
| What if the other player holds a disk? | That does not prevent your victory; only your own hand must be empty. |
| Can both players win? | Normal play stops at the first victory. An explicitly restored snapshot satisfying both win conditions reports `winners = ["A", "B"]`, a shared victory. |
| Can a player take consecutive turns? | Yes, any sequence is valid, including sequences containing only one player. The engine has no current-player field. |
| What happens to an illegal move? | It returns `accepted: false` and a reason, preserving the exact engine state. The frontend consumes that scheduled turn. |
| What happens after victory? | The engine rejects further actions with `game_over`; replay stops and counts remaining records as ignored. |
| Are skips allowed when holding a disk? | Yes. Skip is always legal until the game ends. |
| What is a random-play timeout? | An unfinished game, not a draw. The turn budget is a frontend limit, not a game rule. |
| What is valid N? | A strictly positive integer; booleans, zero, and negative values are rejected. |

An illegal move cannot create a new winner because it does not change state.
Terminal outcomes are public, while the opponent's private poles and hand remain
absent from observations.

## Replay input

The input is one UTF-8 JSON object with exactly three fields. Arrays are aligned:
`turn_order[i]` performs `moves[i]`. An empty pair of arrays is valid.

```json
{
  "disk_count": 1,
  "turn_order": ["A", "B", "A"],
  "moves": [
    {"action": "lift", "pole": 1},
    {"action": "lift", "pole": 1},
    {"action": "place", "pole": 3}
  ]
}
```

Actions use **relative** pole numbers: `1` and `3` mean the acting player's
private poles, and `2` is shared. Skip is `{"action": "skip"}`. This notation
cannot refer to an opponent's private pole.

Use `replay -` to read standard input. UTF-8 BOMs are accepted. Unknown/missing
fields, duplicate JSON keys, invalid player names, noninteger poles, and unequal
array lengths are input errors. Lift/place must have a pole field. The whole
document is validated before play, including records after a potential win.
By contrast, well-formed illegal actions such as an unknown action string,
`pole: 99`, a skip with a pole, or placing with an empty hand waste a turn.

Examples:

- `examples/example-win.json`: the supplied three-turn example; A wins while B holds disk 2.
- `examples/illegal-turn.json`: two illegal actions interleaved with a legal lift and skip; all four turns are consumed.
- `examples/opponent-win.json`: A's final lift awards B victory using a disk originally belonging to A.

## Output

Successful commands print one JSON object to stdout and exit 0, including when
the game is unfinished. Errors print `{"error": {"type": "input_error",
"message": "..."}}` to stderr and exit 2. `--help` prints normal command help.

| Field | Meaning |
| --- | --- |
| `mode` | `replay` or `random` |
| `status` | `finished` if at least one winner exists; otherwise `unfinished` |
| `stop_reason` | `win`, `turn_order_exhausted` (replay), or `turn_limit` (random) |
| `winners` | `[]`, `["A"]`, `["B"]`, or `["A", "B"]` |
| `turns_consumed` | All attempted turns, including illegal actions and skips |
| `turns_ignored` | Replay suffix after victory; always zero for random play |
| `final_state` | Full snapshot: `disk_count`, five named `poles`, and both `hands` |
| `events` | Ordered attempted moves, each with 1-based `turn`, `player`, `move`, `accepted`, and `reason` (`null` on success) |

Every stack is serialized **bottom to top**. An empty hand is `null`. The example
above ends with this `final_state`:

```json
{
  "disk_count": 1,
  "poles": {"1a": [], "2": [], "3a": [1], "1b": [], "3b": []},
  "hands": {"A": null, "B": 2}
}
```

The full output is intended for the replay operator or a trusted service. A player
policy receives `observe(state, player)`, never `final_state`.

## Random play and reproducibility

```sh
uv run hanoi-crossing random --disks 2 --seed 37 --max-turns 150 --turn-order AAB
```

Defaults are 3 disks per player, seed 0, 1,000 turns, and repeating `AB` order.
The frontend repeats any nonempty sequence of `A` and `B`; `AAB` therefore gives
A two consecutive turns. The engine does not know or enforce that schedule.
Both agents sample uniformly from **all** legal actions, including skip.
Zero turns is supported, and random play is not guaranteed to finish.

Random output also includes `seed`, `schedule`, and a `replay` object. Save that
nested object as a JSON file and feed it to replay to reproduce every attempted
move and the final state. For example:

```sh
uv run hanoi-crossing random --disks 2 --seed 37 --max-turns 150 > random-result.json
uv run python -c "import json; from pathlib import Path; result=json.loads(Path('random-result.json').read_text(encoding='utf-8-sig')); Path('recording.json').write_text(json.dumps(result['replay']), encoding='utf-8')"
uv run hanoi-crossing replay recording.json
```

In Windows PowerShell 5, use `| Out-File -Encoding utf8 random-result.json` instead
of `>` to avoid UTF-16 output. The full random result is deliberately a different
schema from replay input. Seeded runs are reproducible on the same Python version;
recorded moves are the portable source of truth across runtime versions.

## Engine design and reuse

```python
from hanoi_crossing.engine import Action, GameState, new_game, observe, step

state = new_game(2)
view = observe(state, "A")
result = step(state, "A", Action("lift", 1))
assert result.accepted
assert state.hands == (None, None)  # original snapshot still exists
state = result.state
restored = GameState.from_dict(state.to_dict())
assert restored == state
```

`engine.py` owns all game rules. Frozen dataclasses and nested tuples make each
snapshot deeply immutable. The five internal stacks are ordered
`(1a, 2, 3a, 1b, 3b)`; hands are `(A, B)`. Constructors and restoration enforce
exact disk conservation and valid stack ordering. A `Transition` contains the
resulting state, acceptance flag, and optional stable rejection code.

`observe` returns only the player's three visible stacks, own hand, public initial
disk count, player ID, and terminal winners. `legal_actions(view)` derives moves
from that observation. It returns no actions after termination. Unknown player
IDs raise `ValueError`; passing something other than an `Action` to `step` raises
`TypeError`. These are caller errors, separate from illegal game actions.

The engine has no I/O, randomness, hidden mutable global state, turn counter, or
implicit alternation. A server can keep one snapshot per game and serialize
updates to each game, while independent games run concurrently. An RL wrapper
can supply scheduling, rewards, resets, and rollout storage without modifying
the engine. Neither a server nor a training loop is included. Immutable snapshots
do not replace a server's need to arbitrate simultaneous updates to the same game.

Revalidating each newly constructed snapshot favors correctness and simplicity
over throughput; sorting the disk inventory costs O(N log N) per changed state.
The frontends retain O(turns) events in memory for these small assignment games.

## Neuro-symbolic policy boundary

The symbolic engine is the source of rule accuracy. `policy.py` provides a
**neural-ready interface**, with no trained neural network or training claims:

1. `encode(view)` produces numeric features plus an exact symbolic legality mask.
2. An external neural model can score the fixed seven actions.
3. `choose_scored(view, scores)` selects the highest-scored legal action.
4. `step` independently validates the selected action against the current state.

Action order is `skip, lift-1, lift-2, lift-3, place-1, place-2, place-3`.
Feature width is `6N + 1`: each visible stack, bottom to top and padded with zeros
to `2N` entries, followed by the held disk. Disk sizes are divided by `2N`; zero
means an empty slot/hand. Width is fixed for a chosen N. Opponent-private state
and actor identity are not encoded; the rules are symmetric under player swap.

```python
from random import Random
from hanoi_crossing.engine import new_game, observe, step
from hanoi_crossing.policy import choose_random, choose_scored, encode

state = new_game(2)
view = observe(state, "A")
encoded = encode(view)  # features: 13 numbers; action_mask: 7 booleans
action = choose_scored(view, [0, 2, 100, 100, 100, 100, 100])
# Only skip and lift-1 are legal here, so illegal high scores cannot win.
assert action.kind == "lift" and action.pole == 1
result = step(state, "A", action)
random_action = choose_random(view, Random(42))
```

The score adapter requires seven finite real numbers, rejects booleans/NaN/
infinities, and resolves ties by action order. On terminal observations the mask
is all false and policy selection raises `ValueError`. Legal moves are guaranteed
for a current, engine-produced observation, but the mask does not guarantee good
strategy. The required random player consumes this same observation-only policy
boundary with caller-owned RNG.

## Layout and verification

```text
src/hanoi_crossing/
  engine.py       immutable state, rules, observations, serialization
  policy.py       random policy, numeric features, masked score adapter
  cli.py          JSON validation, scheduling, replay/random runners
  __main__.py     python -m entry point
tests/
  test_engine.py  direct rule/invariant/isolation tests
  test_policy.py  legality masks, privacy, deterministic selection
  test_cli.py     formats, errors, command entry point, random-to-replay round trip
examples/         ready-to-run recordings
pyproject.toml    src-layout package and console entry point
uv.lock          reproducible project resolution
```

Tests exercise the actual engine without mocks. They cover the supplied example,
illegal wasted turns, consecutive turns, shared/foreign disks, nonacting wins,
terminal states, hidden information, snapshot validation, independent games,
and disk/stack invariants across thousands of seeded transitions. Additional
policy and CLI tests verify the complete agent boundary and recording format.
An exhaustive regression test visits all 1,956 reachable states for N=1 and N=2
and checks both players' accepted actions against the advertised legal actions.

Verified locally on Python 3.14.7: **54 tests passed**, wheel and source archives
built successfully, and the complete test suite also passed against the wheel
installed into a separate environment. CI is configured for Python 3.11 and 3.14;
the remote workflow has not been run as part of this local submission.

Check the core's physical line count, including comments and blank lines:

```sh
uv run python -c "from pathlib import Path; n=len(Path('src/hanoi_crossing/engine.py').read_text().splitlines()); print(n); assert n < 500"
```

## Development journey and AI assistance

The Git history records real checkpoints: initial design/package setup, symbolic
engine with direct tests, frontends and policy integration, then final review and
documentation. Rule decisions were recorded before implementation. The
neuro-symbolic adapter was added following the requested design refinement.

OpenAI Codex assisted with implementation, documentation, test design, and
review. Parallel Codex agents handled rule/test review, the CLI, and the policy
adapter, followed by integration and independent review. No neural training was
performed. Tests and build checks were run against the resulting code rather
than relying only on generated assertions.
