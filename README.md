# Hanoi Crossing

A reusable Python engine for the supplied Hanoi Crossing v1.1 rules, with JSON replay and seeded random-play frontends.

## Implementation plan

1. Establish the package layout and record rule interpretations.
2. Implement an immutable, deterministic engine with private player observations.
3. Add replay and random-play command-line frontends.
4. Exercise the engine directly, validate the frontends, and finish usage documentation.

The core will contain fewer than 500 physical Python lines. Turn scheduling, random number generation, file access, and command-line parsing stay outside it.

## Decisions recorded before implementation

- `N` must be a positive integer. Stacks are stored bottom to top.
- A player wins when their hand, own pole 1, and the shared pole are empty, and their own pole 3 is nonempty. Disk ownership is not a victory requirement.
- Evaluate both players: removing the final shared disk can make the other player win.
- Stop at the first terminal state. A restored state satisfying both victory conditions is a shared victory.
- Illegal actions preserve the entire engine state; the frontend still consumes the corresponding turn.
- Pole numbers in actions and observations are relative to the acting player: 1, 2 (shared), 3.
- Random play samples uniformly from legal actions, including skip, and has a finite turn budget. Exhaustion means unfinished, not a draw.
- Frozen snapshots contain no scheduling or RNG state. Public observations omit the opponent's hand and private poles.

## AI assistance

OpenAI Codex assisted with rules analysis, implementation, documentation, and test design/review. Parallel Codex agents are used for independent review and bounded implementation tasks. The Git history records actual development checkpoints.
