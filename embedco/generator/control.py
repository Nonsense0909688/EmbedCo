"""Control-flow block emitters (if / repeat / while / timers)."""

from .text import braces, indent


class ControlFlowMixin:
    """Requires: ``prepare``, ``register``, ``generate_sequence`` and ``self.state``."""

    def generate_if(self, block, definition, else_body=None):
        values = self.prepare(block, definition)
        self.register(definition, values)

        result = braces(f"if ({values['condition']})", self.generate_sequence(block.get("then", [])))

        else_blocks = block.get("else", else_body)
        if else_blocks:
            result += " " + braces("else", self.generate_sequence(else_blocks))
        return result

    def generate_repeat(self, block, definition):
        values = self.prepare(block, definition)
        n = self.state.next_id()
        i, limit = f"cf_i{n}", f"cf_n{n}"

        # The count is evaluated once, not on every pass.
        header = f"for (int {i} = 0, {limit} = ({values['count']}); {i} < {limit}; {i}++)"
        return braces(header, self.generate_sequence(block.get("body", [])))

    def generate_while(self, block, definition):
        values = self.prepare(block, definition)
        return braces(f"while ({values['condition']})", self.generate_sequence(block.get("body", [])))

    def generate_timer(self, block, definition):
        values = self.prepare(block, definition)
        n = self.state.next_id()
        last = f"cf_last_{n}"

        body = self.generate_sequence(block.get("body", []))
        inner = f"{last} = millis();" + (f"\n{body}" if body else "")

        check = braces(
            f"if (millis() - {last} >= (unsigned long)({values['interval']}))",
            inner,
        )
        return "{\n" + indent(f"static unsigned long {last} = 0;\n{check}") + "\n}"
