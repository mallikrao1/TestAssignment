import dataclasses
import json
import random
import unittest
from collections import deque

from hanoi_crossing.engine import (
    Action,
    GameState,
    legal_actions,
    new_game,
    observe,
    step,
)


class EngineTests(unittest.TestCase):
    def assert_valid(self, state):
        disks = [disk for pole in state.poles for disk in pole]
        disks.extend(disk for disk in state.hands if disk is not None)
        self.assertEqual(sorted(disks), list(range(1, 2 * state.disk_count + 1)))
        self.assertEqual(len(state.poles), 5)
        self.assertEqual(len(state.hands), 2)
        for pole in state.poles:
            self.assertIsInstance(pole, tuple)
            self.assertTrue(all(lower > upper for lower, upper in zip(pole, pole[1:])))

    def test_initial_state_uses_odd_and_even_descending_stacks(self):
        state = new_game(3)
        self.assertEqual(state.poles, ((5, 3, 1), (), (), (6, 4, 2), ()))
        self.assertEqual(state.hands, (None, None))
        self.assertEqual(state.winners, ())
        self.assertFalse(state.terminal)
        self.assert_valid(state)

    def test_disk_count_requires_positive_non_boolean_integer(self):
        for value in (0, -1, True, False, 1.5, "2", None):
            with self.subTest(value=value), self.assertRaises((ValueError, TypeError)):
                new_game(value)

    def test_example_allows_repeated_player_and_hidden_opponent_hand(self):
        state = new_game(1)
        for player, action in (
            ("A", Action("lift", 1)),
            ("B", Action("lift", 1)),
            ("A", Action("place", 3)),
        ):
            result = step(state, player, action)
            self.assertTrue(result.accepted)
            state = result.state
        self.assertEqual(state.winners, ("A",))
        self.assertEqual(state.hands, (None, 2))
        self.assertTrue(state.terminal)

    def test_turn_order_is_supplied_externally(self):
        state = new_game(2)
        for action in (Action("lift", 1), Action("place", 2), Action("lift", 1)):
            result = step(state, "A", action)
            self.assertTrue(result.accepted)
            state = result.state
        self.assertEqual(state.hands, (3, None))
        self.assertEqual(state.poles[1], (1,))
        self.assertEqual(state.poles[3], (4, 2))

    def test_each_player_uses_relative_private_pole_numbers(self):
        state = new_game(2)
        state = step(state, "B", Action("lift", 1)).state
        state = step(state, "B", Action("place", 3)).state
        self.assertEqual(state.poles, ((3, 1), (), (), (4,), (2,)))
        self.assertEqual(observe(state, "B").poles, ((4,), (), (2,)))

    def test_lift_only_removes_top_disk(self):
        result = step(new_game(3), "B", Action("lift", 1))
        self.assertTrue(result.accepted)
        self.assertEqual(result.state.hands, (None, 2))
        self.assertEqual(result.state.poles[3], (6, 4))

    def test_both_players_can_lift_any_shared_top_disk(self):
        for owner, other, disk in (("A", "B", 1), ("B", "A", 2)):
            with self.subTest(owner=owner):
                state = step(new_game(2), owner, Action("lift", 1)).state
                state = step(state, owner, Action("place", 2)).state
                result = step(state, other, Action("lift", 2))
                self.assertTrue(result.accepted)
                self.assertEqual(observe(result.state, other).hand, disk)
                self.assertEqual(result.state.poles[1], ())

    def test_place_smaller_disk_on_larger_disk(self):
        state = step(new_game(2), "B", Action("lift", 1)).state
        state = step(state, "B", Action("place", 2)).state
        state = step(state, "A", Action("lift", 1)).state
        result = step(state, "A", Action("place", 2))
        self.assertTrue(result.accepted)
        self.assertEqual(result.state.poles[1], (2, 1))
        self.assertEqual(result.state.hands, (None, None))

    def test_illegal_gameplay_actions_preserve_identical_state(self):
        initial = new_game(2)
        holding = step(initial, "A", Action("lift", 1)).state
        shared = step(holding, "A", Action("place", 2)).state
        larger = step(shared, "B", Action("lift", 1)).state
        for state, player, action in (
            (initial, "A", Action("lift", 2)),
            (initial, "B", Action("place", 3)),
            (holding, "A", Action("lift", 1)),
            (larger, "B", Action("place", 2)),
        ):
            with self.subTest(action=action, player=player):
                result = step(state, player, action)
                self.assertFalse(result.accepted)
                self.assertIs(result.state, state)
                self.assertIsInstance(result.reason, str)
                self.assertTrue(result.reason)

    def test_malformed_action_values_are_rejected_without_mutation(self):
        state = new_game(2)
        for action in (
            Action("dance"),
            Action("lift"),
            Action("place", 0),
            Action("lift", 4),
            Action("lift", "1b"),
            Action("lift", True),
            Action("lift", 1.0),
            Action("skip", 1),
        ):
            with self.subTest(action=action):
                result = step(state, "A", action)
                self.assertFalse(result.accepted)
                self.assertIs(result.state, state)

    def test_illegal_turn_does_not_block_next_external_turn(self):
        state = new_game(1)
        wasted = step(state, "A", Action("place", 3))
        self.assertFalse(wasted.accepted)
        lifted = step(wasted.state, "B", Action("lift", 1))
        self.assertTrue(lifted.accepted)
        self.assertEqual(lifted.state.hands, (None, 2))

    def test_skip_is_legal_with_empty_or_full_hand(self):
        initial = new_game(2)
        for state in (initial, step(initial, "A", Action("lift", 1)).state):
            with self.subTest(hand=state.hands[0]):
                result = step(state, "A", Action("skip"))
                self.assertTrue(result.accepted)
                self.assertIs(result.state, state)
                self.assertIsNone(result.reason)

    def test_shared_stack_blocks_victory(self):
        state = GameState(1, ((), (2,), (1,), (), ()), (None, None))
        self.assertEqual(state.winners, ())
        self.assertFalse(state.terminal)

    def test_lifting_shared_disk_can_award_nonacting_player_victory(self):
        state = GameState(1, ((), (2,), (), (), (1,)), (None, None))
        result = step(state, "A", Action("lift", 2))
        self.assertTrue(result.accepted)
        self.assertEqual(result.state.winners, ("B",))
        self.assertEqual(result.state.hands, (2, None))

    def test_foreign_disk_can_complete_victory_without_original_disk(self):
        state = GameState(1, ((), (2,), (), (1,), ()), (None, None))
        state = step(state, "A", Action("lift", 2)).state
        result = step(state, "A", Action("place", 3))
        self.assertTrue(result.accepted)
        self.assertEqual(result.state.winners, ("A",))
        self.assertEqual(result.state.poles[2], (2,))
        self.assertEqual(result.state.poles[3], (1,))

    def test_empty_destination_does_not_win(self):
        state = GameState(1, ((), (), (), (2, 1), ()), (None, None))
        self.assertEqual(state.winners, ())
        self.assertFalse(state.terminal)

    def test_full_hand_blocks_own_victory(self):
        state = GameState(1, ((), (), (1,), (), ()), (2, None))
        self.assertEqual(state.winners, ())

    def test_restored_simultaneous_winners_are_both_reported(self):
        state = GameState(1, ((), (), (1,), (), (2,)), (None, None))
        self.assertEqual(state.winners, ("A", "B"))
        self.assertTrue(state.terminal)

    def test_terminal_state_rejects_all_actions_and_has_no_legal_actions(self):
        state = GameState(1, ((), (), (1,), (2,), ()), (None, None))
        for player in ("A", "B"):
            self.assertEqual(legal_actions(observe(state, player)), ())
            for action in (Action("skip"), Action("lift", 1), Action("place", 3)):
                result = step(state, player, action)
                self.assertFalse(result.accepted)
                self.assertIs(result.state, state)

    def test_unknown_player_is_a_request_error(self):
        state = new_game(1)
        for player in ("C", "a", "", None, 0):
            with self.subTest(player=player):
                with self.assertRaises(ValueError):
                    observe(state, player)
                with self.assertRaises(ValueError):
                    step(state, player, Action("skip"))

    def test_player_observation_excludes_hidden_private_poles_and_hand(self):
        initial = new_game(2)
        holding = step(initial, "B", Action("lift", 1)).state
        moved = step(holding, "B", Action("place", 3)).state
        self.assertEqual(observe(initial, "A"), observe(holding, "A"))
        self.assertEqual(observe(initial, "A"), observe(moved, "A"))
        self.assertEqual(observe(holding, "B").hand, 2)
        self.assertEqual(observe(initial, "A").player, "A")
        self.assertEqual(observe(initial, "A").disk_count, 2)
        self.assertEqual(observe(initial, "A").poles, ((3, 1), (), ()))

    def test_initial_legal_actions_are_only_skip_and_lift_first_pole(self):
        for player in ("A", "B"):
            actions = legal_actions(observe(new_game(2), player))
            self.assertIsInstance(actions, tuple)
            self.assertEqual(set(actions), {Action("skip"), Action("lift", 1)})

    def test_legal_actions_only_offer_placements_when_holding(self):
        state = step(new_game(2), "A", Action("lift", 1)).state
        self.assertEqual(
            set(legal_actions(observe(state, "A"))),
            {Action("skip"), Action("place", 1), Action("place", 2), Action("place", 3)},
        )
        state = step(state, "A", Action("place", 2)).state
        state = step(state, "B", Action("lift", 1)).state
        self.assertNotIn(Action("place", 2), legal_actions(observe(state, "B")))

    def test_snapshots_and_actions_are_immutable(self):
        state = new_game(2)
        with self.assertRaises(dataclasses.FrozenInstanceError):
            state.hands = (1, None)
        action = Action("skip")
        with self.assertRaises(dataclasses.FrozenInstanceError):
            action.kind = "lift"
        original = state.to_dict()
        result = step(state, "A", Action("lift", 1))
        self.assertEqual(state.to_dict(), original)
        self.assertIsNot(result.state, state)

    def test_serialization_roundtrip_and_defensive_copies(self):
        state = step(new_game(3), "B", Action("lift", 1)).state
        snapshot = json.loads(json.dumps(state.to_dict()))
        self.assertEqual(set(snapshot), {"disk_count", "poles", "hands"})
        self.assertEqual(set(snapshot["poles"]), {"1a", "2", "3a", "1b", "3b"})
        self.assertEqual(set(snapshot["hands"]), {"A", "B"})
        restored = GameState.from_dict(snapshot)
        self.assertEqual(restored, state)
        snapshot["poles"]["1a"].clear()
        snapshot["hands"]["B"] = None
        self.assertEqual(restored, state)
        self.assertEqual(state.poles[0], (5, 3, 1))
        self.assertEqual(state.hands[1], 2)

    def test_invalid_custom_states_are_rejected(self):
        for poles, hands in (
            (((1,), (), (), (), ()), (None, None)),
            (((1,), (), (), (1,), ()), (None, None)),
            (((1, 2), (), (), (), ()), (None, None)),
            (((1,), (), (), (3,), ()), (None, None)),
            (((True,), (), (), (2,), ()), (None, None)),
            (((1.0,), (), (), (2,), ()), (None, None)),
            (((1,), (), (), (2,), ()), (1, None)),
            (((1,), (), (), (2,)), (None, None)),
            (((1,), (), (), (2,), ()), (None,)),
            (([1], (), (), (2,), ()), (None, None)),
            ([(), (), (), (2, 1), ()], (None, None)),
            (((1,), (), (), (2,), ()), [None, None]),
        ):
            with self.subTest(poles=poles, hands=hands):
                with self.assertRaises((ValueError, TypeError)):
                    GameState(1, poles, hands)

    def test_snapshot_decoder_rejects_unknown_or_missing_fields(self):
        original = new_game(1).to_dict()
        for key in ("disk_count", "poles", "hands"):
            snapshot = dict(original)
            del snapshot[key]
            with self.subTest(missing=key), self.assertRaises((ValueError, TypeError)):
                GameState.from_dict(snapshot)
        for key, value in (("winners", []), ("terminal", False), ("turn", "A")):
            with self.subTest(extra=key), self.assertRaises((ValueError, TypeError)):
                GameState.from_dict({**original, key: value})
        for field, key in (("poles", "secret"), ("hands", "C")):
            snapshot = json.loads(json.dumps(original))
            snapshot[field][key] = None
            with self.subTest(field=field), self.assertRaises((ValueError, TypeError)):
                GameState.from_dict(snapshot)

    def test_long_seeded_runs_preserve_invariants_and_all_offered_moves_work(self):
        rng = random.Random(104729)
        transitions = 0
        for _ in range(12):
            state = new_game(3)
            for _ in range(400):
                self.assert_valid(state)
                if state.terminal:
                    break
                player = rng.choice(("A", "B"))
                actions = legal_actions(observe(state, player))
                self.assertTrue(actions)
                self.assertEqual(len(actions), len(set(actions)))
                before = state.to_dict()
                for action in actions:
                    candidate = step(state, player, action)
                    self.assertTrue(candidate.accepted, (player, action, candidate.reason))
                    self.assert_valid(candidate.state)
                    self.assertEqual(state.to_dict(), before)
                state = step(state, player, rng.choice(actions)).state
                transitions += 1
        self.assertGreater(transitions, 500)

    def test_repeated_inputs_are_deterministic(self):
        first = new_game(3)
        second = new_game(3)
        rng = random.Random(2026)
        for _ in range(500):
            if first.terminal:
                break
            player = rng.choice(("A", "B"))
            action = rng.choice(legal_actions(observe(first, player)))
            result = step(first, player, action)
            repeated = step(second, player, action)
            self.assertEqual(result, repeated)
            first, second = result.state, repeated.state

    def test_exhaustive_small_games_advertise_exactly_all_accepted_actions(self):
        actions = (Action("skip"),) + tuple(
            Action(kind, pole) for kind in ("lift", "place") for pole in (1, 2, 3)
        )
        total_states = 0
        for disk_count in (1, 2):
            initial = new_game(disk_count)
            visited = {initial}
            pending = deque([initial])
            while pending:
                state = pending.popleft()
                for player in ("A", "B"):
                    transitions = {action: step(state, player, action) for action in actions}
                    accepted = {
                        action for action, transition in transitions.items() if transition.accepted
                    }
                    self.assertEqual(
                        set(legal_actions(observe(state, player))),
                        accepted,
                        (state, player),
                    )
                    for action in accepted:
                        candidate = transitions[action].state
                        if candidate not in visited:
                            visited.add(candidate)
                            pending.append(candidate)
            self.assertTrue(any(state.terminal for state in visited))
            total_states += len(visited)
        self.assertGreater(total_states, 1900)

    def test_games_can_be_interleaved_without_interference(self):
        first = new_game(1)
        second = new_game(2)
        first = step(first, "A", Action("lift", 1)).state
        second = step(second, "B", Action("lift", 1)).state
        first = step(first, "A", Action("place", 3)).state
        second = step(second, "B", Action("place", 2)).state
        self.assertEqual(first.winners, ("A",))
        self.assertEqual(first.poles, ((), (), (1,), (2,), ()))
        self.assertFalse(second.terminal)
        self.assertEqual(second.poles, ((3, 1), (2,), (), (4,), ()))
        self.assertEqual(new_game(1).poles, ((1,), (), (), (2,), ()))


if __name__ == "__main__":
    unittest.main()
