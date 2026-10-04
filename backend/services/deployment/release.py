"""固定摘要发布清单与目标机预检；仅处理公开配置和镜像标签。"""

import argparse
import json
import re
import sys
import tomllib
from pathlib import Path

PINNED = re.compile(r"[a-z0-9][a-z0-9./:_-]*@sha256:[0-9a-f]{64}")
VERSION = re.compile(r"v(?:0|[1-9][0-9]*)\.(?:0|[1-9][0-9]*)\.(?:0|[1-9][0-9]*)")
SOURCE = "https://github.com/ChaceQC/elect"
BASE_IMAGES = ("MYSQL_IMAGE", "REDIS_IMAGE", "RABBITMQ_IMAGE", "RABBITMQ_LOW_RESOURCE_IMAGE")


def check_version(root, tag):
    if not VERSION.fullmatch(tag):
        raise ValueError("发布标签须为vX.Y.Z")
    backend = tomllib.loads((root / "backend/pyproject.toml").read_text())["project"]["version"]
    frontend = json.loads((root / "frontend/package.json").read_text())["version"]
    if backend != frontend or tag != f"v{backend}":
        raise ValueError("发布标签与前后端版本不一致")


def check_config(config, allow_local=False):
    services = config["services"]
    backend = services["gateway"]["image"]
    for name, service in services.items():
        image = service.get("image", "")
        if not allow_local and (not PINNED.fullmatch(image) or service.get("build")):
            raise ValueError("发布配置必须无构建入口且所有镜像固定sha256摘要")
        if name not in {"mysql", "redis", "rabbitmq", "nginx", "smoke", "browser"}:
            if image != backend:
                raise ValueError("同次部署的后端角色必须使用同一镜像")
    return sorted(name for name, value in services.items() if not value.get("profiles"))


def check_images(images, version, revision):
    if not VERSION.fullmatch(version) or not re.fullmatch(r"[0-9a-f]{40}", revision):
        raise ValueError("发布版本/源提交元数据缺失或无效")
    if len(images) != 2:
        raise ValueError("须核对前后端两张实际镜像")
    for image in images:
        labels = image["Config"].get("Labels") or {}
        if any(labels.get(f"org.opencontainers.image.{key}") != expected
               for key, expected in (("version", version), ("revision", revision),
                                     ("source", SOURCE))):
            raise ValueError("前后端实际镜像与发布版本/源提交不一致")


def write_manifest(root, output, tag, revision, backend, frontend, run_url):
    check_version(root, tag)
    if not re.fullmatch(r"[0-9a-f]{40}", revision):
        raise ValueError("源提交无效")
    if not all(PINNED.fullmatch(value) for value in (backend, frontend)):
        raise ValueError("应用镜像须固定摘要")
    overrides = {"ELECT_IMAGE": backend, "ELECT_WEB_IMAGE": frontend,
                 "ELECT_IMAGE_MODE": "published", "ELECT_DEPLOYMENT_MODE": "combined"}
    lines = (root / "deploy/.env.example").read_text().splitlines()
    values = {}
    for index, line in enumerate(lines):
        if "=" in line and not line.startswith("#"):
            key, value = line.split("=", 1)
            values[key] = overrides.get(key, value)
            lines[index] = f"{key}={values[key]}"
    if not overrides.keys() <= values.keys():
        raise ValueError("公开模板缺少发布配置字段")
    if not all(PINNED.fullmatch(values[key]) for key in BASE_IMAGES):
        raise ValueError("基础镜像须固定摘要")
    lines += [f"ELECT_RELEASE_VERSION={tag}", f"ELECT_RELEASE_REVISION={revision}"]
    output.mkdir(parents=True, exist_ok=True)
    (output / "release.env").write_text("\n".join(lines) + "\n")
    (output / "release.json").write_text(json.dumps({
        "version": tag, "revision": revision, "platform": "linux/amd64", "check_run": run_url,
        "backend": backend, "frontend": frontend,
        "base_images": {key: values[key] for key in BASE_IMAGES},
        "capacity_2cpu_2gb_50users_24h_verified": False,
    }, ensure_ascii=False, indent=2) + "\n")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    config = commands.add_parser("check-config")
    config.add_argument("--allow-local", action="store_true")
    images = commands.add_parser("check-images")
    images.add_argument("--version", required=True)
    images.add_argument("--revision", required=True)
    version = commands.add_parser("check-version")
    manifest = commands.add_parser("manifest")
    for command in (version, manifest):
        command.add_argument("--source-root", type=Path, required=True)
        command.add_argument("--tag", required=True)
    manifest.add_argument("--output", type=Path, required=True)
    for key in ("revision", "backend", "frontend", "run-url"):
        manifest.add_argument(f"--{key}", required=True)
    args = parser.parse_args()
    try:
        if args.command == "check-config":
            print("\n".join(check_config(json.load(sys.stdin), args.allow_local)))
        elif args.command == "check-images":
            check_images(json.load(sys.stdin), args.version, args.revision)
        elif args.command == "check-version":
            check_version(args.source_root, args.tag)
        else:
            write_manifest(args.source_root, args.output, args.tag, args.revision,
                           args.backend, args.frontend, args.run_url)
    except (ValueError, KeyError):
        parser.exit(2, "发布配置或镜像元数据校验失败\n")


if __name__ == "__main__":
    main()
