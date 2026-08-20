#!/usr/bin/env python3

import argparse
import datetime
import json
import re
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
ENV_FILE = ROOT / "platform" / "ubuntu.env"
MANIFEST_TYPES = ", ".join(
    (
        "application/vnd.oci.image.index.v1+json",
        "application/vnd.docker.distribution.manifest.list.v2+json",
    )
)


def request(url, headers=None, method=None):
    query = urllib.request.Request(url, headers=headers or {}, method=method)
    return urllib.request.urlopen(query, timeout=30)


def ubuntu_digest():
    query = urllib.parse.urlencode(
        {
            "service": "registry.docker.io",
            "scope": "repository:library/ubuntu:pull",
        }
    )
    with request(f"https://auth.docker.io/token?{query}") as response:
        token = json.load(response)["token"]
    headers = {
        "Accept": MANIFEST_TYPES,
        "Authorization": f"Bearer {token}",
    }
    with request(
        "https://registry-1.docker.io/v2/library/ubuntu/manifests/26.04",
        headers,
    ) as response:
        manifest = json.load(response)
        digest = response.headers["Docker-Content-Digest"]
    architectures = {
        item.get("platform", {}).get("architecture")
        for item in manifest.get("manifests", [])
    }
    if not {"amd64", "arm64"}.issubset(architectures):
        raise RuntimeError("Ubuntu 26.04 is missing a required architecture")
    if not re.fullmatch(r"sha256:[0-9a-f]{64}", digest):
        raise RuntimeError("Docker Hub returned an invalid Ubuntu digest")
    return digest


def latest_snapshot(now=None):
    now = now or datetime.datetime.now(datetime.UTC)
    for age in range(2, 15):
        day = (now - datetime.timedelta(days=age)).date()
        snapshot = f"{day:%Y%m%d}T000000Z"
        url = f"https://snapshot.ubuntu.com/ubuntu/{snapshot}/dists/resolute/InRelease"
        try:
            with request(url, method="HEAD") as response:
                if response.status == 200:
                    return snapshot
        except urllib.error.HTTPError as error:
            if error.code != 404:
                raise
    raise RuntimeError("no recent Ubuntu snapshot is available")


def read_environment(path):
    values = {}
    for line in path.read_text().splitlines():
        key, value = line.split("=", 1)
        values[key] = value
    return values


def update(path=ENV_FILE, now=None):
    values = read_environment(path)
    digest = ubuntu_digest()
    snapshot = latest_snapshot(now)
    image = f"docker.io/library/ubuntu:26.04@{digest}"
    if values["UBUNTU_IMAGE"] == image and values["UBUNTU_SNAPSHOT"] == snapshot:
        return False
    day = datetime.datetime.strptime(snapshot, "%Y%m%dT%H%M%SZ").replace(tzinfo=datetime.UTC)
    values.update(
        {
            "UBUNTU_IMAGE": image,
            "UBUNTU_SNAPSHOT": snapshot,
            "PLATFORM_VERSION": f"26.04.{day:%Y%m%d}.1",
            "PLATFORM_EPOCH": str(int(day.timestamp())),
        }
    )
    path.write_text("".join(f"{key}={value}\n" for key, value in values.items()))
    return True


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--env", type=Path, default=ENV_FILE)
    args = parser.parse_args()
    print("changed" if update(args.env) else "current")


if __name__ == "__main__":
    main()
