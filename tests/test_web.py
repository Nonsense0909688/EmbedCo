import http.client
import json
import threading
import unittest

from embedco.settings import Settings
from embedco.web.app import build_services, create_server

from .helpers import HomeTestCase


class WebTests(HomeTestCase):
    def setUp(self):
        super().setUp()
        self.settings = Settings(home=self.home, host="127.0.0.1", port=0, log_to_file=False,
                                 max_body_bytes=2048, request_timeout=5)
        self.server = create_server(self.settings, build_services(self.settings))
        self.port = self.server.server_address[1]
        thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        thread.start()
        self.addCleanup(self._stop, thread)

    def _stop(self, thread):
        self.server.shutdown()
        self.server.server_close()
        thread.join(5)

    def call(self, method, path, body=None, headers=None, raw=None):
        conn = http.client.HTTPConnection("127.0.0.1", self.port, timeout=5)
        payload = raw if raw is not None else (json.dumps(body) if body is not None else None)
        conn.request(method, path, body=payload, headers=headers or {"Content-Type": "application/json"})
        resp = conn.getresponse()
        data = resp.read()
        conn.close()
        try:
            return resp.status, json.loads(data), resp
        except ValueError:
            return resp.status, data, resp

    def test_health_and_security_headers(self):
        status, data, resp = self.call("GET", "/healthz")
        self.assertEqual(status, 200)
        self.assertEqual(data["status"], "ok")
        self.assertEqual(resp.getheader("X-Content-Type-Options"), "nosniff")
        self.assertTrue(resp.getheader("X-Request-ID"))

    def test_request_id_is_echoed_when_valid_and_replaced_when_not(self):
        _, _, resp = self.call("GET", "/healthz", headers={"X-Request-ID": "abc-123"})
        self.assertEqual(resp.getheader("X-Request-ID"), "abc-123")
        _, _, resp = self.call("GET", "/healthz", headers={"X-Request-ID": "bad id\x01!"})
        self.assertNotEqual(resp.getheader("X-Request-ID"), "bad id\x01!")

    def test_index_served(self):
        status, data, _ = self.call("GET", "/")
        self.assertEqual(status, 200)
        self.assertIn(b"<html", data.lower())

    def test_palette(self):
        status, data, _ = self.call("GET", "/api/palette")
        self.assertEqual(status, 200)
        self.assertIn("timing", data["palette"])
        self.assertTrue(any(b["id"] == "uno" for b in data["boards"]))

    def test_generate_ok_and_block_error(self):
        status, data, _ = self.call("POST", "/api/generate", {"loop": [{"type": "wait", "inputs": {"milliseconds": 5}}]})
        self.assertEqual(status, 200)
        self.assertIn("delay(5);", data["code"])
        status, data, _ = self.call("POST", "/api/generate", {"loop": [{"type": "nope"}]})
        self.assertEqual(status, 400)
        self.assertIn("Unknown block", data["error"])

    def test_malformed_payloads_are_400_not_500(self):
        status, data, _ = self.call("POST", "/api/generate", raw="{not json")
        self.assertEqual(status, 400)
        status, data, _ = self.call("POST", "/api/generate", raw="[1,2,3]")
        self.assertEqual(status, 400)
        status, data, _ = self.call("POST", "/api/generate", {"loop": [{"type": "wait", "inputs": "x"}]})
        self.assertEqual(status, 400)

    def test_project_lifecycle_over_http(self):
        status, data, _ = self.call("POST", "/api/projects", {"project": {"name": "Demo", "board": "uno"}})
        self.assertEqual(status, 201)
        pid = data["meta"]["id"]
        status, data, _ = self.call("PUT", f"/api/projects/{pid}", {"project": {"name": "Demo", "loop": [{"type": "wait"}]}})
        self.assertEqual(status, 200)
        status, data, _ = self.call("GET", f"/api/projects/{pid}")
        self.assertEqual(len(data["project"]["loop"]), 1)
        status, _, _ = self.call("POST", f"/api/projects/{pid}/rename", {"name": "Renamed"})
        self.assertEqual(status, 200)
        status, _, _ = self.call("DELETE", "/api/projects/Renamed")
        self.assertEqual(status, 200)
        status, data, _ = self.call("GET", "/api/projects/Renamed")
        self.assertEqual(status, 404)

    def test_traversal_attempt_is_404(self):
        status, _, _ = self.call("GET", "/api/projects/..%2F..%2Fetc%2Fpasswd")
        self.assertEqual(status, 404)

    def test_unknown_route_404_and_wrong_method_405(self):
        self.assertEqual(self.call("GET", "/nope")[0], 404)
        self.assertEqual(self.call("DELETE", "/api/palette")[0], 405)

    def test_body_size_limit(self):
        status, data, _ = self.call("POST", "/api/generate", raw=json.dumps({"x": "a" * 5000}))
        self.assertEqual(status, 413)

    def test_bad_host_and_cross_origin_blocked(self):
        status, _, _ = self.call("GET", "/healthz", headers={"Host": "evil.example.com"})
        self.assertEqual(status, 403)
        status, _, _ = self.call("POST", "/api/projects", {"project": {"name": "x"}},
                                 headers={"Content-Type": "text/plain", "Origin": "http://evil.example.com"})
        self.assertEqual(status, 403)

    def test_terminal_requires_header(self):
        status, _, _ = self.call("POST", "/api/terminal", {"cmd": "echo hi"})
        self.assertEqual(status, 403)
        status, data, _ = self.call("POST", "/api/terminal", {"cmd": "echo hi"},
                                    headers={"Content-Type": "application/json", "X-EmbedCo-Terminal": "1"})
        self.assertEqual(status, 200)
        self.assertIn("hi", data["out"])

    def test_upload_without_port(self):
        status, data, _ = self.call("POST", "/api/upload", {"board": "uno", "loop": []})
        self.assertEqual(status, 400)
        self.assertFalse(data["ok"])
        self.assertIn("serial port", data["log"])

    def test_upload_rejects_option_like_port(self):
        status, data, _ = self.call("POST", "/api/upload", {"board": "uno", "loop": [], "port": "--evil"})
        self.assertEqual(status, 400)
        self.assertIn("Invalid serial port", data["log"])

    def test_keepalive_survives_rejected_post(self):
        conn = http.client.HTTPConnection("127.0.0.1", self.port, timeout=5)
        conn.request("POST", "/nope", body=json.dumps({"a": 1}), headers={"Content-Type": "application/json"})
        r = conn.getresponse(); r.read()
        self.assertEqual(r.status, 404)
        conn.request("GET", "/healthz")
        r = conn.getresponse(); r.read()
        self.assertEqual(r.status, 200)
        conn.close()


class TerminalDisabledOnPublicBind(HomeTestCase):
    def test_terminal_off_when_not_loopback(self):
        settings = Settings(home=self.home, host="0.0.0.0", port=0, log_to_file=False)
        self.assertFalse(build_services(settings).terminal.enabled)


if __name__ == "__main__":
    unittest.main()
