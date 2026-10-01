import json
from pathlib import Path

from alembic.script import ScriptDirectory

from scripts.migrations import configuration
from scripts.schema_catalog import catalog
from services.common.migration_runtime import DATABASES

ROOT = Path(__file__).resolve().parents[3]


def test_catalog_matches_seven_independent_migration_heads():
    value = catalog()
    assert json.loads((ROOT / "docs/database/schema-catalog.json").read_text()) == value
    assert set(value["databases"]) == set(DATABASES)
    revisions = set()
    for domain, database in value["databases"].items():
        script = ScriptDirectory.from_config(configuration(domain))
        assert script.get_heads() == [database["revision"]]
        bases = [revision for revision in script.walk_revisions() if revision.down_revision is None]
        assert len(bases) == 1
        revisions.add(database["revision"])
        for table in database["tables"].values():
            assert "password" not in table["columns"]
            assert "student_id" not in table["columns"]
            for foreign in table["foreign_keys"]:
                assert all(target.count(".") == 1 for target in foreign["targets"])
    assert len(revisions) == 7
