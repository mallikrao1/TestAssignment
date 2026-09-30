import contextlib
import io
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

from hanoi_crossing.cli import main


class CliTests(unittest.TestCase):
    def invoke(self, args, source=None):
        stdout = io.StringIO()
        stderr = io.StringIO()
        with contextlib.redirect_stdout(stdout), contextlib.redirect_stderr(stderr):
            if source is None:
                code = main(args)
            else:
                previous = sys.stdin
                sys.stdin = io.StringIO(source)
                try:
                    code = main(args)
                finally:
                    sys.stdin = previous
        return code, stdout.getvalue(), stderr.getvalue()

    def example(self):
        return {
            "disk_count": 1,
            "turn_order": ["A", "B", "A"],
            "moves": [
                {"action": "lift", "pole": 1},
                {"action": "lift", "pole": 1},
                {"action": "place", "pole": 3},
            ],
        }

    def test_spec_example_from_stdin(self):
        code, stdout, stderr = self.invoke(["replay", "-"], json.dumps(self.example()))
        result = json.loads(stdout)
        self.assertEqual((code, stderr), (0, ""))
        self.assertEqual(result["winners"], ["A"])
        self.assertEqual(result["turns_consumed"], 3)
        self.assertEqual(result["stop_reason"], "win")
        self.assertEqual(result["final_state"]["poles"]["3a"], [1])
        self.assertEqual(result["final_state"]["hands"], {"A": None, "B": 2})

    def test_utf8_bom_file(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "moves.json"
            path.write_text(json.dumps(self.example()), encoding="utf-8-sig")
            code, stdout, stderr = self.invoke(["replay", str(path)])
        self.assertEqual((code, stderr), (0, ""))
        self.assertEqual(json.loads(stdout)["winners"], ["A"])

    def test_illegal_move_consumes_turn(self):
        document = {"disk_count": 1, "turn_order": ["B", "B", "B"], "moves": [
            {"action": "place", "pole": 2},
            {"action": "unknown"},
            {"action": "lift", "pole": 99},
        ]}
        code, stdout, stderr = self.invoke(["replay", "-"], json.dumps(document))
        result = json.loads(stdout)
        self.assertEqual((code, stderr), (0, ""))
        self.assertEqual(result["turns_consumed"], 3)
        self.assertEqual(result["status"], "unfinished")
        self.assertTrue(all(not event["accepted"] for event in result["events"]))
        self.assertEqual(result["final_state"]["poles"]["1b"], [2])

    def test_terminal_stops_before_remaining_valid_records(self):
        document = self.example()
        document["turn_order"].append("B")
        document["moves"].append({"action": "place", "pole": 3})
        code, stdout, stderr = self.invoke(["replay", "-"], json.dumps(document))
        self.assertEqual((code, stderr), (0, ""))
        self.assertEqual(json.loads(stdout)["turns_ignored"], 1)

    def test_entire_input_is_validated_even_after_winning_record(self):
        document = self.example()
        document["turn_order"].append("B")
        document["moves"].append({"action": "lift"})
        code, stdout, stderr = self.invoke(["replay", "-"], json.dumps(document))
        self.assertEqual((code, stdout), (2, ""))
        self.assertIn("Move 4", json.loads(stderr)["error"]["message"])

    def test_schema_errors(self):
        cases = [None, [], {}, {**self.example(), "unexpected": True},
                 {**self.example(), "disk_count": True},
                 {**self.example(), "disk_count": 0},
                 {**self.example(), "turn_order": ["C", "B", "A"]},
                 {**self.example(), "moves": []},
                 {"disk_count": 1, "turn_order": [], "moves": "wrong"}]
        for move in ({}, {"action": 4}, {"action": "skip", "pole": True},
                     {"action": "lift", "pole": None}, {"action": "skip", "extra": 1}):
            cases.append({"disk_count": 1, "turn_order": ["A"], "moves": [move]})
        for document in cases:
            with self.subTest(document=document):
                code, stdout, stderr = self.invoke(["replay", "-"], json.dumps(document))
                self.assertEqual((code, stdout), (2, ""))
                self.assertEqual(json.loads(stderr)["error"]["type"], "input_error")

    def test_malformed_json_and_duplicate_keys(self):
        for source in ("{broken", '{"disk_count":1,"disk_count":2,"turn_order":[],"moves":[]}'):
            with self.subTest(source=source):
                code, stdout, stderr = self.invoke(["replay", "-"], source)
                self.assertEqual((code, stdout), (2, ""))
                self.assertIn("message", json.loads(stderr)["error"])

    def test_file_error_is_structured(self):
        with tempfile.TemporaryDirectory() as directory:
            code, stdout, stderr = self.invoke(["replay", str(Path(directory) / "missing.json")])
        self.assertEqual((code, stdout), (2, ""))
        self.assertEqual(json.loads(stderr)["error"]["type"], "input_error")

    def test_argument_errors_are_structured(self):
        for args in ([], ["other"], ["random", "--disks", "wrong"],
                     ["random", "--max-turns", "-1"], ["random", "--disks", "0"],
                     ["random", "--turn-order", ""], ["random", "--turn-order", "AC"]):
            with self.subTest(args=args):
                code, stdout, stderr = self.invoke(args)
                self.assertEqual((code, stdout), (2, ""))
                self.assertEqual(json.loads(stderr)["error"]["type"], "input_error")

    def test_random_is_deterministic_legal_and_replayable(self):
        args = ["random", "--disks", "2", "--seed", "37", "--max-turns", "150", "--turn-order", "AAB"]
        first = self.invoke(args)
        self.assertEqual(first, self.invoke(args))
        self.assertEqual((first[0], first[2]), (0, ""))
        result = json.loads(first[1])
        self.assertTrue(result["events"])
        self.assertTrue(all(event["accepted"] for event in result["events"]))
        self.assertEqual(result["replay"]["turn_order"], ["AAB"[index % 3] for index in range(result["turns_consumed"])])
        replay = self.invoke(["replay", "-"], json.dumps(result["replay"]))
        self.assertEqual((replay[0], replay[2]), (0, ""))
        self.assertEqual(json.loads(replay[1])["final_state"], result["final_state"])
        self.assertEqual(json.loads(replay[1])["events"], result["events"])

    def test_zero_turn_limit(self):
        code, stdout, stderr = self.invoke(["random", "--max-turns", "0"])
        result = json.loads(stdout)
        self.assertEqual((code, stderr), (0, ""))
        self.assertEqual(result["stop_reason"], "turn_limit")
        self.assertEqual(result["turns_consumed"], 0)
        self.assertEqual(result["replay"]["moves"], [])

    def test_module_entrypoint(self):
        process = subprocess.run(
            [sys.executable, "-m", "hanoi_crossing", "replay", "-"],
            input=json.dumps(self.example()), capture_output=True, text=True, check=False,
        )
        self.assertEqual((process.returncode, process.stderr), (0, ""))
        self.assertEqual(json.loads(process.stdout)["winners"], ["A"])


if __name__ == "__main__":
    unittest.main()
