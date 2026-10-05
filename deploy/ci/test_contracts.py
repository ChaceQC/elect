"""仅检查CI失败门禁和镜像传递拒绝路径，不重复业务测试。"""
import copy
import hashlib
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

import gate
import images


class GateTests(unittest.TestCase):
    def test_required_results(self):
        complete = {name: {"result": "success"} for name in gate.REQUIRED}
        gate.verify(complete)
        for name in gate.REQUIRED:
            for result in ["failure", "cancelled", "skipped", "", None]:
                with self.subTest(name=name, result=result):
                    changed = copy.deepcopy(complete)
                    changed[name]["result"] = result
                    with self.assertRaises(ValueError):
                        gate.verify(changed)
            missing = copy.deepcopy(complete)
            del missing[name]
            with self.assertRaises(ValueError):
                gate.verify(missing)
        with self.assertRaises(ValueError):
            gate.verify({**complete, "unexpected": {"result": "success"}})


class ImageTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.directory = Path(self.temporary.name)
        self.source = {"revision": "a" * 40, "version": "v0.19.2"}
        self.manifest = {"schema": 1, "part": "backend", **self.source, "images": {}}
        for role, tag in images.IMAGES["backend"].items():
            data = role.encode()
            (self.directory / f"{role}.tar.zst").write_bytes(data)
            self.manifest["images"][role] = {
                "tag": tag, "id": "sha256:" + "b" * 64,
                "sha256": hashlib.sha256(data).hexdigest(),
            }
        self.save()

    def save(self):
        (self.directory / "images.json").write_text(json.dumps(self.manifest), encoding="utf-8")

    def test_current_and_wrong_source(self):
        images.validate("backend", self.directory, self.source)
        for key in ["revision", "version"]:
            with self.assertRaises(ValueError):
                images.validate("backend", self.directory, {**self.source, key: "other"})

    def test_corrupt_archive(self):
        (self.directory / "runtime.tar.zst").write_bytes(b"changed")
        with self.assertRaises(ValueError):
            images.validate("backend", self.directory, self.source)

    def test_missing_and_wrong_image(self):
        self.manifest["images"]["runtime"]["tag"] = "unrelated"
        self.save()
        with self.assertRaises(ValueError):
            images.validate("backend", self.directory, self.source)
        del self.manifest["images"]["runtime"]
        self.save()
        with self.assertRaises(ValueError):
            images.validate("backend", self.directory, self.source)

    def test_loaded_identity_and_labels(self):
        value = {"Id": "sha256:" + "b" * 64, "Os": "linux", "Architecture": "amd64",
                 "Config": {"Labels": {images.PREFIX + k: v for k, v in self.source.items()}}}
        with patch("subprocess.check_output", return_value=json.dumps([value])):
            self.assertEqual(images.inspect("test", self.source), value["Id"])
            with self.assertRaises(ValueError):
                images.inspect("test", {**self.source, "revision": "other"})
        with patch("images.inspect", return_value="different"), patch("images.source", return_value=self.source):
            with patch("sys.argv", ["images", "verify", "--part", "backend",
                                   "--directory", str(self.directory)]):
                with self.assertRaises(ValueError):
                    images.main()


if __name__ == "__main__":
    unittest.main()
