"""CI镜像包和公开来源清单；不读取配置、凭据或业务数据。"""
import argparse
import hashlib
import json
import os
from pathlib import Path
import subprocess
import time
import tomllib

ROOT = Path(__file__).resolve().parents[2]
IMAGES = {
    "backend": {"runtime": "elect-backend:test", "test": "elect-backend-smoke:test"},
    "frontend": {"runtime": "elect-frontend:test", "test": "elect-frontend-browser-check"},
}
PREFIX = "org.opencontainers.image."


def source():
    revision = subprocess.check_output(
        ["git", "-C", str(ROOT), "rev-parse", "HEAD"], text=True, encoding="utf-8",
    ).strip()
    if os.environ.get("GITHUB_SHA", revision) != revision:
        raise ValueError("检出提交与本次运行不一致")
    backend = tomllib.loads((ROOT / "backend/pyproject.toml").read_text(encoding="utf-8"))
    frontend = json.loads((ROOT / "frontend/package.json").read_text(encoding="utf-8"))
    version = backend["project"]["version"]
    if version != frontend["version"]:
        raise ValueError("前后端版本不一致")
    return {"revision": revision, "version": "v" + version}


def inspect(tag, expected):
    value = json.loads(subprocess.check_output(
        ["docker", "image", "inspect", tag], text=True, encoding="utf-8",
    ))[0]
    labels = value["Config"]["Labels"] or {}
    for key, wanted in expected.items():
        if labels.get(PREFIX + key) != wanted:
            raise ValueError(f"{tag} 的 {key} 与检出源码不一致")
    if value["Os"] != "linux" or value["Architecture"] != "amd64":
        raise ValueError("镜像平台必须为linux/amd64")
    return value["Id"]


def sha256(path):
    with path.open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def report(label, started, **extra):
    record = {"phase": label, "seconds": round(time.monotonic() - started, 2), **extra}
    line = json.dumps(record, ensure_ascii=False)
    print(line, flush=True)
    if os.environ.get("GITHUB_STEP_SUMMARY"):
        with open(os.environ["GITHUB_STEP_SUMMARY"], "a", encoding="utf-8") as stream:
            stream.write("- " + line + "\n")


def pack(part, directory, expected):
    directory.mkdir(parents=True, exist_ok=False)
    entries = {}
    for role, tag in IMAGES[part].items():
        started = time.monotonic()
        image_id = inspect(tag, expected)
        archive = directory / f"{role}.tar.zst"
        with archive.open("wb") as output:
            with subprocess.Popen(["docker", "save", tag], stdout=subprocess.PIPE) as save:
                compressed = subprocess.run(
                    ["zstd", "-T2", "--fast=1", "-c"], stdin=save.stdout, stdout=output,
                    check=False,
                )
                save.stdout.close()
                if save.wait() or compressed.returncode:
                    raise RuntimeError("镜像导出失败")
        entries[role] = {"tag": tag, "id": image_id, "sha256": sha256(archive)}
        report(f"pack-{part}-{role}", started, bytes=archive.stat().st_size)
    manifest = {"schema": 1, "part": part, **expected, "images": entries}
    (directory / "images.json").write_text(
        json.dumps(manifest, indent=2, ensure_ascii=False) + "\n", encoding="utf-8",
    )


def validate(part, directory, expected):
    manifest = json.loads((directory / "images.json").read_text(encoding="utf-8"))
    if manifest.get("schema") != 1 or manifest.get("part") != part:
        raise ValueError("镜像清单类型不匹配")
    if any(manifest.get(key) != value for key, value in expected.items()):
        raise ValueError("镜像包不属于本次提交/版本")
    entries = manifest.get("images", {})
    if set(entries) != set(IMAGES[part]):
        raise ValueError("镜像清单缺项")
    for role, tag in IMAGES[part].items():
        entry = entries[role]
        if entry.get("tag") != tag or entry.get("sha256") != sha256(directory / f"{role}.tar.zst"):
            raise ValueError("镜像包校验失败")
    return entries


def load(part, directory, expected, runtime_only):
    started = time.monotonic()
    entries = validate(part, directory, expected)
    report(f"verify-{part}", started)
    for role, entry in entries.items():
        if runtime_only and role != "runtime":
            continue
        started = time.monotonic()
        with subprocess.Popen(
            ["zstd", "-dc", str(directory / f"{role}.tar.zst")], stdout=subprocess.PIPE,
        ) as unpack:
            result = subprocess.run(["docker", "load"], stdin=unpack.stdout, check=False)
            unpack.stdout.close()
            if unpack.wait() or result.returncode:
                raise RuntimeError("镜像加载失败")
        if inspect(entry["tag"], expected) != entry["id"]:
            raise ValueError("加载的镜像ID与受测清单不一致")
        report(f"load-{part}-{role}", started)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("action", choices=["metadata", "pack", "load", "verify"])
    parser.add_argument("--part", choices=list(IMAGES))
    parser.add_argument("--directory", type=Path)
    parser.add_argument("--runtime-only", action="store_true")
    args = parser.parse_args()
    expected = source()
    if args.action == "metadata":
        print("\n".join(f"{key}={value}" for key, value in expected.items()))
        return
    if not args.part or not args.directory:
        parser.error("需要part与directory")
    if args.action == "pack":
        pack(args.part, args.directory, expected)
    elif args.action == "load":
        load(args.part, args.directory, expected, args.runtime_only)
    else:
        for role, entry in validate(args.part, args.directory, expected).items():
            if not args.runtime_only or role == "runtime":
                if inspect(entry["tag"], expected) != entry["id"]:
                    raise ValueError("运行后的镜像ID改变")


if __name__ == "__main__":
    main()
