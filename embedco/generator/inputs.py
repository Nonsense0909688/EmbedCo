"""Input resolution, hardware instance binding and registration of includes/globals/setup."""

import logging

from ..errors import BlockError
from .text import IDENT, c_string, render

logger = logging.getLogger(__name__)


class InputsMixin:
    """Requires: ``self.state`` (GenerationState) and ``self.generate_expression``."""

    def resolve(self, value, where, string=False):
        """Turn one input (literal, raw code, or nested block) into C++ text."""
        if isinstance(value, bool):
            return "true" if value else "false"
        if isinstance(value, (int, float)):
            return str(value)
        if isinstance(value, dict):
            return self.generate_expression(value)
        if value is None:
            raise BlockError(f"'{where}': an input is empty")
        text = str(value)
        return c_string(text) if string else text

    def prepare(self, block, definition):
        """Merge defaults, resolve nested blocks, bind hardware instances."""
        block_type = definition["id"]
        given = block.get("inputs") or {}
        if not isinstance(given, dict):
            raise BlockError(f"'{block_type}': 'inputs' must be an object")

        defaults = {}
        for key, value in (definition.get("defaults") or {}).items():
            if isinstance(value, str) and "{" in value:
                value = render(value, self.state.builtins, block_type)
            defaults[key] = value

        raw = {**defaults, **given}

        missing = [n for n in definition.get("inputs", []) if n not in raw]
        if missing:
            raise BlockError(f"'{block_type}' is missing input(s): {', '.join(missing)}")

        strings = set(definition.get("strings", []))
        values = dict(self.state.builtins)

        for key, value in raw.items():
            values[key] = self.resolve(value, block_type, string=key in strings)

        instance = definition.get("instance")
        if instance:
            values[instance["var"]] = self.bind_instance(block_type, instance, values, given)

        self.check_pwm(block_type, definition, raw)
        self.check_variable(block_type, definition, values)
        return values

    def bind_instance(self, block_type, spec, values, given):
        """Give each physical device one shared, auto-named C++ object."""
        state = self.state
        var = spec["var"]
        prefix = spec["prefix"]
        key = (prefix, *(values[k] for k in spec.get("key", [])))

        explicit = given.get(var)
        if explicit is not None:
            name = str(explicit)
            if not IDENT.match(name):
                raise BlockError(f"'{block_type}': '{name}' is not a valid name")
            state.instances[key] = name
            return name

        if key in state.instances:
            return state.instances[key]

        if spec.get("existing"):
            raise BlockError(
                f"'{block_type}' needs its setup block first "
                f"(add the matching block that creates the {prefix})"
            )

        state.instance_counts[prefix] += 1
        name = f"{prefix}{state.instance_counts[prefix]}"
        state.instances[key] = name
        return name

    def check_pwm(self, block_type, definition, raw):
        pwm_pins = self.state.board.get("pwm_pins")
        if not pwm_pins:
            return

        for port in definition.get("pwm", []):
            value = raw.get(port)
            if isinstance(value, str) and value.isdigit():
                value = int(value)
            if isinstance(value, int) and not isinstance(value, bool) and value not in pwm_pins:
                self.state.warn(
                    f"Pin {value} ({block_type}) is not a PWM pin on "
                    f"{self.state.board.get('name')}. PWM pins: "
                    f"{', '.join(map(str, pwm_pins))}"
                )

    def check_variable(self, block_type, definition, values):
        spec = definition.get("variable")
        if not spec:
            return
        variables = self.state.variables

        if "declare" in spec:
            name = values[spec["declare"]]
            if not IDENT.match(name):
                raise BlockError(f"'{name}' is not a valid variable name")
            if name in variables:
                raise BlockError(f"Variable '{name}' is created more than once")
            variables[name] = values.get("var_type", "int")

        if "use" in spec:
            name = values[spec["use"]]
            if name not in variables:
                raise BlockError(
                    f"Variable '{name}' has not been created yet "
                    f"(add a Create Variable block before using it)"
                )

    def register(self, definition, values):
        """Record includes, libraries, globals and setup lines a block needs."""
        state = self.state
        block_type = definition["id"]
        include_map = state.board.get("include_map", {})
        extra_libs = state.board.get("extra_libraries", {})

        for include in definition.get("includes", []):
            state.includes.add(include_map.get(include, include))
            if include in extra_libs:
                state.libraries.add(extra_libs[include])

        state.libraries.update(definition.get("libraries", []))

        declare = definition.get("declare")
        if declare:
            state.declarations.setdefault(render(declare, values, block_type).strip("\n"), None)

        setup = definition.get("setup")
        if setup:
            text = render(setup, values, block_type).strip("\n")
            key = definition.get("setup_key", text)
            if key not in state.setup_map or definition.get("setup_override"):
                state.setup_map[key] = text
