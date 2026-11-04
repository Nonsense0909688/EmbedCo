"""EmbedCoGenerator: turns a block graph (plain dicts / JSON) into an Arduino sketch.

Program format
--------------
    {"setup": [block, ...], "loop": [block, ...]}
or a flat list of blocks where each block may carry ``"section": "setup"|"loop"``.

A block is ``{"type": "servo_move", "inputs": {"pin": 6, "angle": 90}}``.
Control blocks hold child blocks:

    if            -> "then": [...], "else": [...]   (or a following "otherwise" block)
    repeat        -> "body": [...]
    repeat_while  -> "body": [...]
    run_every     -> "body": [...]

Any input may be a number/bool (literal), a string (raw C++, or quoted for text
ports), or another block dict with an output (the node wired into that port).

The generator keeps per-run state, so an instance must not be used by two
threads at once (the web layer serialises access in ``CodegenService``).
"""

import difflib
import logging
import time
from pathlib import Path

from ..errors import BlockError
from .boards import BoardRegistry
from .catalog import BlockCatalog
from .control import ControlFlowMixin
from .inputs import InputsMixin
from .plugins import PluginRegistry
from .state import GenerationState
from .text import braces, render

logger = logging.getLogger(__name__)

DEFAULT_ROOT = Path(__file__).resolve().parents[2]


class EmbedCoGenerator(InputsMixin, ControlFlowMixin):

    def __init__(self, definitions=None, boards=None, plugins_dir=None):
        definitions = Path(definitions) if definitions else DEFAULT_ROOT / "blocks"
        boards = Path(boards) if boards else DEFAULT_ROOT / "boards.yaml"
        plugins_dir = Path(plugins_dir) if plugins_dir else DEFAULT_ROOT / "plugins"

        self.catalog = BlockCatalog.from_definitions(definitions)
        self.boards = BoardRegistry(boards)
        self.plugin_registry = PluginRegistry(plugins_dir, self.catalog)
        self.plugin_registry.load()

        self.state = GenerationState()
        self.configure_board("arduino")

    # ---- convenient views used by the web layer ----

    @property
    def blocks(self):
        return self.catalog.blocks

    @property
    def board_profiles(self):
        return self.boards.profiles

    @property
    def warnings(self):
        return self.state.warnings

    @property
    def libraries(self):
        return self.state.libraries

    # ---- boards ----

    def configure_board(self, board):
        selection = self.boards.resolve(board)
        if selection.warning:
            self.state.warn(selection.warning)
        self.state.board = selection.profile
        self.state.board_label = selection.label
        self.state.builtins = selection.builtins

    # ---- block lookup ----

    def get_definition(self, block):
        if not isinstance(block, dict) or "type" not in block:
            raise BlockError(f"Every block needs a 'type': {block!r}")

        block_type = block["type"]
        if block_type not in self.catalog:
            close = difflib.get_close_matches(str(block_type), self.catalog.blocks, n=1)
            hint = f" Did you mean '{close[0]}'?" if close else ""
            raise BlockError(f"Unknown block: {block_type}.{hint}")
        return self.catalog.blocks[block_type]

    # ---- expressions and statements ----

    def generate_expression(self, node):
        definition = self.get_definition(node)

        if "output" not in definition or definition.get("control"):
            raise BlockError(
                f"'{definition['id']}' does not return a value, so it cannot be connected to an input"
            )

        values = self.prepare(node, definition)
        self.register(definition, values)
        return render(definition["code"], values, definition["id"])

    def generate_action(self, block, definition):
        block_type = definition["id"]

        if "output" in definition:
            self.state.warn(
                f"'{definition['name']}' returns a value but isn't connected to anything, so it was skipped"
            )
            return ""

        values = self.prepare(block, definition)
        self.register(definition, values)

        code = definition.get("code")
        if not code:
            if any(k in definition for k in ("setup", "declare", "variable")):
                return ""   # hardware / variable setup only
            raise BlockError(f"No code generator for {block_type}")

        return render(code, values, block_type).strip("\n")

    def generate_block(self, block, else_body=None):
        definition = self.get_definition(block)
        control = definition.get("control")

        if control == "conditional":
            return self.generate_if(block, definition, else_body)
        if control == "loop":
            return self.generate_repeat(block, definition)
        if control == "while":
            return self.generate_while(block, definition)
        if control == "timer":
            return self.generate_timer(block, definition)
        if control == "else":
            raise BlockError("'Otherwise' must come directly after an 'If' block")
        return self.generate_action(block, definition)

    def generate_sequence(self, blocks):
        blocks = list(blocks or [])
        output = []
        i = 0

        while i < len(blocks):
            block = blocks[i]
            definition = self.get_definition(block)
            else_body = None

            # "If" followed by an "Otherwise" block -> if/else
            if (
                definition.get("control") == "conditional"
                and "else" not in block
                and i + 1 < len(blocks)
                and isinstance(blocks[i + 1], dict)
                and self.catalog.blocks.get(blocks[i + 1].get("type"), {}).get("control") == "else"
            ):
                else_body = blocks[i + 1].get("body", [])
                i += 1

            code = self.generate_block(block, else_body)
            if code:
                output.append(code)
            i += 1

        return "\n".join(output)

    # ---- main pipeline ----

    @staticmethod
    def split_program(program):
        if isinstance(program, dict):
            return list(program.get("setup", [])), list(program.get("loop", []))

        setup, loop = [], []
        for block in program:
            section = block.get("section", "loop")
            if section not in ("setup", "loop"):
                raise BlockError(f"Invalid section: {section}")
            (setup if section == "setup" else loop).append(block)
        return setup, loop

    def generate(self, program, board="arduino"):
        started = time.perf_counter()
        self.state = GenerationState()
        self.configure_board(board)
        state = self.state

        setup_blocks, loop_blocks = self.split_program(program)

        # Order matters: setup first, so variables created there exist in loop.
        user_setup = self.generate_sequence(setup_blocks)
        loop_body = self.generate_sequence(loop_blocks)

        header = ["// Generated by EmbedCo", f"// Board: {state.board_label}"]
        if state.libraries:
            header.append("// Install these libraries: " + ", ".join(sorted(state.libraries)))
        header += [f"// WARNING: {w}" for w in state.warnings]

        parts = ["\n".join(header)]

        if state.includes:
            parts.append("\n".join(f"#include <{inc}>" for inc in sorted(state.includes)))

        if state.declarations:
            parts.append("\n".join(state.declarations))

        setup_lines = [*state.board.get("init", []), *state.setup_map.values(), user_setup]
        parts.append(braces("void setup()", "\n".join(line for line in setup_lines if line)))
        parts.append(braces("void loop()", loop_body))

        code = "\n\n".join(parts) + "\n"
        logger.debug(
            "Generated sketch for %s: %d setup block(s), %d loop block(s), %d byte(s), %d warning(s) in %.1f ms",
            state.board_label, len(setup_blocks), len(loop_blocks), len(code),
            len(state.warnings), (time.perf_counter() - started) * 1000,
        )
        return code

    def generate_project(self, project):
        """project = {"board": ..., "setup": [...], "loop": [...]} or {"blocks": [...]}"""
        if not isinstance(project, dict):
            raise BlockError("Project must be a JSON object")
        program = project if ("setup" in project or "loop" in project) else project["blocks"]
        return self.generate(program, project.get("board", "arduino"))

    # ---- editor / plugin support ----

    def palette(self):
        return self.catalog.palette(self.plugin_registry.disabled)

    @property
    def plugins(self):
        return self.plugin_registry.plugins

    @property
    def disabled_plugins(self):
        return self.plugin_registry.disabled
