"""独立领域 Alembic 入口；部署持锁编排在 T1 实现。"""

import argparse
from pathlib import Path

from alembic import command
from alembic.config import Config

from services.common.migration_runtime import DATABASES

BACKEND = Path(__file__).resolve().parents[1]


def configuration(domain):
    directory = BACKEND / "services" / domain / "migrations"
    config = Config(str(directory / "alembic.ini"))
    config.set_main_option("script_location", str(directory))
    return config


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--domain", required=True, choices=[*DATABASES, "all"])
    parser.add_argument("--sql", action="store_true")
    parser.add_argument("--output-dir", type=Path)
    args = parser.parse_args()
    if args.domain == "all" and not args.sql:
        raise SystemExit("在线迁移须指定单一领域；统一持锁执行器由 T1 提供")
    if args.output_dir and not args.sql:
        raise SystemExit("--output-dir 仅用于离线 SQL")
    domains = DATABASES if args.domain == "all" else [args.domain]
    for domain in domains:
        config = configuration(domain)
        if args.output_dir:
            args.output_dir.mkdir(parents=True, exist_ok=True)
            with (args.output_dir / f"{domain}.sql").open("w") as stream:
                config.output_buffer = stream
                command.upgrade(config, "head", sql=True)
        else:
            command.upgrade(config, "head", sql=args.sql)


if __name__ == "__main__":
    main()
