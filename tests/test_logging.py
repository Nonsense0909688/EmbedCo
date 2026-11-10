import io
import json
import logging
import unittest

from embedco.logging_config import JsonFormatter, RequestIdFilter, request_id_var


class LoggingTests(unittest.TestCase):
    def _logger(self, formatter):
        stream = io.StringIO()
        handler = logging.StreamHandler(stream)
        handler.setFormatter(formatter)
        handler.addFilter(RequestIdFilter())
        logger = logging.getLogger(f"cf.test.{id(stream)}")
        logger.handlers[:] = [handler]
        logger.propagate = False
        logger.setLevel(logging.DEBUG)
        return logger, stream

    def test_json_lines_include_request_id_and_extras(self):
        logger, stream = self._logger(JsonFormatter())
        token = request_id_var.set("req-42")
        try:
            logger.info("hello %s", "world", extra={"duration_ms": 3.5})
        finally:
            request_id_var.reset(token)
        record = json.loads(stream.getvalue())
        self.assertEqual(record["msg"], "hello world")
        self.assertEqual(record["request_id"], "req-42")
        self.assertEqual(record["duration_ms"], 3.5)
        self.assertEqual(record["level"], "INFO")

    def test_exceptions_are_serialised(self):
        logger, stream = self._logger(JsonFormatter())
        try:
            1 / 0
        except ZeroDivisionError:
            logger.exception("boom")
        self.assertIn("ZeroDivisionError", json.loads(stream.getvalue())["exc"])


if __name__ == "__main__":
    unittest.main()
