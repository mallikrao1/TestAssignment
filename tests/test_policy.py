"""Tests of the public symbolic boundary used by random and scored agents."""

from dataclasses import FrozenInstanceError, replace
from random import Random
import unittest

from hanoi_crossing.engine import Action, Observation, legal_actions, new_game, observe, step
from hanoi_crossing.policy import ACTIONS, choose_random, choose_scored, encode


class PolicyTests(unittest.TestCase):
    def setUp(self):
        self.observation = Observation(
            player="A",
            disk_count=3,
            poles=((5, 3, 1), (), ()),
            hand=None,
            winners=(),
        )

    def test_encoding_is_normalized_padded_and_immutable(self):
        encoded = encode(self.observation)
        self.assertEqual(encoded.features, (5 / 6, 3 / 6, 1 / 6) + (0.0,) * 16)
        self.assertEqual(
            encoded.action_mask, (True, True, False, False, False, False, False)
        )
        with self.assertRaises(FrozenInstanceError):
            encoded.features = ()

    def test_encoding_preserves_all_visible_stacks_and_held_disk(self):
        observation = Observation(
            player="B", disk_count=2, poles=((3,), (4,), (1,)), hand=2, winners=()
        )
        self.assertEqual(
            encode(observation).features,
            (0.75, 0, 0, 0, 1, 0, 0, 0, 0.25, 0, 0, 0, 0.5),
        )
        self.assertEqual(
            encode(observation).action_mask,
            (True, False, False, False, True, True, False),
        )

    def test_features_do_not_encode_actor_identity(self):
        self.assertEqual(
            encode(self.observation), encode(replace(self.observation, player="B"))
        )

    def test_hidden_opponent_move_does_not_change_policy_inputs_or_decisions(self):
        initial = new_game(3)
        changed = step(initial, "B", Action("lift", 1)).state
        before = observe(initial, "A")
        after = observe(changed, "A")
        self.assertNotEqual(initial.hands, changed.hands)
        self.assertNotEqual(initial.poles, changed.poles)
        self.assertEqual(encode(before), encode(after))
        self.assertEqual(choose_random(before, Random(42)), choose_random(after, Random(42)))
        self.assertEqual(choose_scored(before, range(7)), choose_scored(after, range(7)))

    def test_random_is_valid_reproducible_and_includes_skip(self):
        first = Random(12345)
        second = Random(12345)
        actions = tuple(choose_random(self.observation, first) for _ in range(2000))
        self.assertEqual(
            actions, tuple(choose_random(self.observation, second) for _ in actions)
        )
        self.assertEqual(set(actions), set(legal_actions(self.observation)))
        self.assertGreater(actions.count(Action("skip")), 800)
        self.assertLess(actions.count(Action("skip")), 1200)

    def test_scored_ignores_illegal_preferred_moves(self):
        observation = Observation(
            player="A", disk_count=2, poles=((1,), (4, 3), ()), hand=2, winners=()
        )
        self.assertEqual(
            choose_scored(observation, (1, 2, 3, 4, 100, 7, 6)), Action("place", 2)
        )
        self.assertIn(
            choose_scored(observation, (1, 2, 3, 4, 100, 7, 6)),
            legal_actions(observation),
        )

    def test_scored_ties_follow_stable_action_order(self):
        self.assertEqual(choose_scored(self.observation, (0,) * 7), Action("skip"))
        observation = replace(self.observation, poles=((5, 3), (2,), (1,)))
        self.assertEqual(
            choose_scored(observation, (-1, 1, 1, 1, 0, 0, 0)), Action("lift", 1)
        )

    def test_scored_accepts_generators_and_large_finite_integers(self):
        self.assertEqual(
            choose_scored(self.observation, (score for score in (0, 10**400, 0, 0, 0, 0, 0))),
            Action("lift", 1),
        )

    def test_scored_rejects_wrong_length(self):
        for scores in ((), (0,) * 6, (0,) * 8):
            with self.subTest(scores=scores), self.assertRaisesRegex(ValueError, "seven|7"):
                choose_scored(self.observation, scores)

    def test_scored_rejects_invalid_scores_even_for_illegal_actions(self):
        for invalid in (float("nan"), float("inf"), -float("inf"), "1", None, True, 1j):
            with self.subTest(invalid=invalid), self.assertRaisesRegex(ValueError, "finite real"):
                choose_scored(self.observation, (0, 1, 0, 0, 0, 0, invalid))

    def test_terminal_observation_has_no_legal_policy_action(self):
        observation = replace(self.observation, winners=("A",))
        self.assertEqual(encode(observation).action_mask, (False,) * len(ACTIONS))
        with self.assertRaisesRegex(ValueError, "terminal"):
            choose_random(observation, Random(0))
        with self.assertRaisesRegex(ValueError, "terminal"):
            choose_scored(observation, (0,) * 7)


if __name__ == "__main__":
    unittest.main()
