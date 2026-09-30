"""从冻结的初始 Alembic 迁移导出表结构目录，仅读取声明。"""

import argparse
import importlib.util
import json
from pathlib import Path

import sqlalchemy as sa
from sqlalchemy.dialects import mysql

from services.common.migration_runtime import DATABASES

BACKEND = Path(__file__).resolve().parents[1]
TARGET = BACKEND.parent / "docs/database/schema-catalog.json"


class Recorder:
    def __init__(self):
        self.metadata = sa.MetaData()

    def create_table(self, name, *items, **options):
        return sa.Table(name, self.metadata, *items, **options)

    def create_index(self, name, table, columns):
        sa.Index(name, *[self.metadata.tables[table].c[key] for key in columns])

    def create_foreign_key(self, name, source, target, columns, targets, **options):
        self.metadata.tables[source].append_constraint(
            sa.ForeignKeyConstraint(
                columns,
                [f"{target}.{key}" for key in targets],
                name=name,
                **options,
            )
        )


def table_schema(table):
    columns = {}
    for column in table.columns:
        columns[column.name] = {
            "type": str(column.type.compile(dialect=mysql.dialect())),
            "nullable": column.nullable,
            "primary_key": column.primary_key,
        }
        if column.computed:
            columns[column.name]["computed"] = str(column.computed.sqltext)
    return {
        "columns": columns,
        "unique": sorted(
            [
                list(constraint.columns.keys())
                for constraint in table.constraints
                if isinstance(constraint, sa.UniqueConstraint)
            ]
        ),
        "checks": sorted(
            str(constraint.sqltext)
            for constraint in table.constraints
            if isinstance(constraint, sa.CheckConstraint)
        ),
        "foreign_keys": sorted(
            [
                {
                    "columns": list(constraint.column_keys),
                    "targets": [element.target_fullname for element in constraint.elements],
                }
                for constraint in table.constraints
                if isinstance(constraint, sa.ForeignKeyConstraint)
            ],
            key=lambda item: item["columns"],
        ),
        "indexes": sorted([list(index.columns.keys()) for index in table.indexes]),
    }


def catalog():
    databases = {}
    for domain, database in DATABASES.items():
        path = BACKEND / "services" / domain / "migrations/versions/0001_initial.py"
        spec = importlib.util.spec_from_file_location(f"initial_{domain}", path)
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        recorder = Recorder()
        module.op = recorder
        module.upgrade()
        databases[domain] = {
            "database": database,
            "revision": module.revision,
            "tables": {
                table.name: table_schema(table) for table in recorder.metadata.tables.values()
            },
        }
    return {"schema_version": 1, "databases": databases}


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--check", action="store_true")
    args = parser.parse_args()
    content = json.dumps(catalog(), ensure_ascii=False, indent=2) + "\n"
    if args.check:
        if TARGET.read_text() != content:
            raise SystemExit("表结构目录与初始迁移不同步")
        print("七域表结构目录检查通过")
    else:
        TARGET.parent.mkdir(parents=True, exist_ok=True)
        TARGET.write_text(content)


if __name__ == "__main__":
    main()
