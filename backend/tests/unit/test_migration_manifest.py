import subprocess
import sys

from scripts.migration_manifest import heads
from services.common.database import migration_head
from services.common.domains import DATABASES


def test_manifest_matches_all_domain_heads():
    assert {name: migration_head(name) for name in DATABASES} == heads()


def test_runtime_and_mail_entry_do_not_import_alembic_or_create_web_app():
    subprocess.run([sys.executable, "-c", (
        "import sys; from services.common.runtime import Runtime; "
        "from services.common.database import migration_head; "
        "import services.notification.job; migration_head('identity'); "
        "assert not any(n == 'alembic' or n.startswith('alembic.') for n in sys.modules); "
        "assert 'services.common.app' not in sys.modules"
    )], check=True)
