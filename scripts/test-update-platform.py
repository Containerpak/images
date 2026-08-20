#!/usr/bin/env python3

import datetime
import importlib.util
import io
import json
import tempfile
import unittest
from pathlib import Path
from unittest import mock


SPEC = importlib.util.spec_from_file_location(
    "update_platform",
    Path(__file__).with_name("update-platform.py"),
)
update_platform = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(update_platform)


class Response(io.BytesIO):
    def __init__(self, body=b"", headers=None, status=200):
        super().__init__(body)
        self.headers = headers or {}
        self.status = status

    def __enter__(self):
        return self

    def __exit__(self, *args):
        self.close()


class PlatformUpdateTest(unittest.TestCase):
    def test_updates_digest_snapshot_version_and_epoch(self):
        manifest = {
            "manifests": [
                {"platform": {"architecture": "amd64"}},
                {"platform": {"architecture": "arm64"}},
            ]
        }
        responses = [
            Response(json.dumps({"token": "token"}).encode()),
            Response(
                json.dumps(manifest).encode(),
                {"Docker-Content-Digest": "sha256:" + "b" * 64},
            ),
            Response(),
        ]
        now = datetime.datetime(2026, 8, 20, tzinfo=datetime.UTC)
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "ubuntu.env"
            path.write_text(
                "UBUNTU_IMAGE=docker.io/library/ubuntu:26.04@sha256:old\n"
                "UBUNTU_SNAPSHOT=20260814T000000Z\n"
                "PLATFORM_VERSION=26.04.20260814.4\n"
                "PLATFORM_EPOCH=1786665600\n"
            )
            with mock.patch.object(update_platform, "request", side_effect=responses):
                self.assertTrue(update_platform.update(path, now))
            values = update_platform.read_environment(path)
        self.assertEqual(values["UBUNTU_SNAPSHOT"], "20260818T000000Z")
        self.assertEqual(values["PLATFORM_VERSION"], "26.04.20260818.1")
        self.assertEqual(values["PLATFORM_EPOCH"], "1787011200")


if __name__ == "__main__":
    unittest.main()
