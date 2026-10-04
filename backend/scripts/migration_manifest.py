"""构建时生成迁移head清单，CI检查源码清单没有落后于迁移。"""

import argparse
import json
from pathlib import Path

from alembic.script import ScriptDirectory

from scripts.migrations import configuration
from services.common.domains import DATABASES

MANIFEST = Path(__file__).resolve().parents[1] / "services/common/migration_heads.json"


def heads():
    return {name: ScriptDirectory.from_config(configuration(name)).get_current_head()
            for name in DATABASES}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--check", action="store_true")
    args = parser.parse_args()
    expected = heads()
    if not all(expected.values()):
        raise SystemExit("迁移必须有且只有一个head")
    if args.check:
        if json.loads(MANIFEST.read_text(encoding="utf-8")) != expected:
            raise SystemExit("迁移版本清单过期，请重新生成")
    else:
        MANIFEST.write_text(json.dumps(expected, indent=2) + "\n", encoding="utf-8")


if __name__ == "__main__":
    main()
