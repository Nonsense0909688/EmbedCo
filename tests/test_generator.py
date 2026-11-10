import json
import unittest

from embedco.errors import BlockError
from embedco.generator import EmbedCoGenerator

from .helpers import ROOT, HomeTestCase


class GeneratorTests(HomeTestCase):
    def setUp(self):
        super().setUp()
        self.gen = EmbedCoGenerator(
            definitions=self.home / "blocks", boards=self.home / "boards.yaml",
            plugins_dir=self.home / "plugins",
        )

    def test_golden_output_matches_original_generator(self):
        cases = json.loads((ROOT / "tests/golden/generator_cases.json").read_text())
        for name, case in cases.items():
            with self.subTest(name):
                self.assertEqual(self.gen.generate(case["program"], board=case["board"]), case["code"])
                self.assertEqual(self.gen.warnings, case["warnings"])

    def test_unknown_block_suggests_close_match(self):
        with self.assertRaisesRegex(BlockError, "Did you mean 'servo_move'"):
            self.gen.generate({"loop": [{"type": "servo_mov"}]})

    def test_missing_input_is_reported(self):
        with self.assertRaisesRegex(BlockError, "missing input"):
            self.gen.generate({"loop": [{"type": "servo_move", "inputs": {"pin": 6}}]})

    def test_variable_must_exist_before_use(self):
        with self.assertRaises(BlockError):
            self.gen.generate({"loop": [{"type": "set_variable", "inputs": {"name": "x", "value": 1}}]})

    def test_state_is_fresh_for_every_run(self):
        prog = {"loop": [{"type": "servo_move", "inputs": {"pin": 6, "angle": 1}}]}
        first = self.gen.generate(prog)
        self.assertEqual(first, self.gen.generate(prog))

    def test_flat_program_with_sections(self):
        code = self.gen.generate([
            {"type": "serial_begin", "section": "setup", "inputs": {}},
            {"type": "wait", "inputs": {"milliseconds": 1}},
        ])
        self.assertIn("delay(1);", code)

    def test_invalid_section(self):
        with self.assertRaisesRegex(BlockError, "Invalid section"):
            self.gen.generate([{"type": "wait", "section": "nope", "inputs": {"milliseconds": 1}}])

    def test_otherwise_without_if(self):
        with self.assertRaisesRegex(BlockError, "Otherwise"):
            self.gen.generate({"loop": [{"type": "otherwise", "body": []}]})

    def test_non_dict_project_rejected(self):
        with self.assertRaises(BlockError):
            self.gen.generate_project([1, 2])

    def test_plugin_install_and_toggle(self):
        plugin = {"id": "demo", "categories": {"demo": [{"id": "demo_block", "name": "Demo", "code": "demo();"}]}}
        meta = self.gen.plugin_registry.install(plugin, "demo")
        self.assertEqual(meta["blocks"], ["demo_block"])
        self.assertIn("demo_block", self.gen.palette()["demo"][0]["id"])
        self.assertTrue(self.gen.plugin_registry.set_enabled("demo", False))
        self.assertNotIn("demo", self.gen.palette())
        # disabled plugin blocks still build old projects
        self.assertIn("demo();", self.gen.generate({"loop": [{"type": "demo_block"}]}))
        from embedco.errors import ConflictError
        with self.assertRaises(ConflictError):
            self.gen.plugin_registry.install(plugin, "demo")


if __name__ == "__main__":
    unittest.main()
