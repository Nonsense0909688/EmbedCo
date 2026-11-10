import unittest

from embedco.errors import NotFoundError, ValidationError
from embedco.services.projects import ProjectStore

from .helpers import HomeTestCase


class ProjectStoreTests(HomeTestCase):
    def setUp(self):
        super().setUp()
        self.store = ProjectStore(self.home / "projects")

    def test_crud_roundtrip(self):
        meta, _ = self.store.create({"name": "My Robot", "board": "uno", "setup": [], "loop": [{"type": "wait"}]})
        self.assertEqual(meta["id"], "My_Robot")
        self.assertEqual(meta["nodes"], 1)
        _, data = self.store.get("My_Robot")
        self.assertEqual(data["board"], "uno")
        meta, _ = self.store.rename("My_Robot", "Better Robot")
        self.assertEqual(meta["id"], "Better_Robot")
        self.store.duplicate("Better_Robot")
        self.assertEqual({m["id"] for m in self.store.list()}, {"Better_Robot", "Better_Robot_copy"})
        self.store.delete("Better_Robot")
        with self.assertRaises(NotFoundError):
            self.store.get("Better_Robot")

    def test_name_collisions_get_suffix(self):
        self.store.create({"name": "A"})
        meta, _ = self.store.create({"name": "A"})
        self.assertEqual(meta["id"], "A_2")

    def test_path_traversal_is_rejected(self):
        for bad in ("../secret", "..%2Fsecret", "a/b", ".hidden", ""):
            with self.subTest(bad), self.assertRaises(NotFoundError):
                self.store.get(bad)

    def test_validation(self):
        with self.assertRaises(ValidationError):
            self.store.create({"name": "x", "setup": "nope"})
        with self.assertRaises(ValidationError):
            self.store.create({"name": "x", "board": 5})
        with self.assertRaises(ValidationError):
            self.store.create(["not", "an", "object"])
        meta, _ = self.store.create({"name": "ok"})
        with self.assertRaises(ValidationError):
            self.store.rename(meta["id"], "   ")

    def test_no_temp_files_left_behind(self):
        self.store.create({"name": "clean"})
        self.assertEqual([p.name for p in (self.home / "projects").iterdir()], ["clean.json"])


if __name__ == "__main__":
    unittest.main()
