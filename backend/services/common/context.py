"""不创建Web应用的领域上下文；API、核心和邮件共享资源初始化边界。"""

from contextlib import asynccontextmanager

from . import business
from .database import create_database, migration_head
from .runtime import load_runtime, public_origin, side_effect_policy
from .security import validate_keys


@asynccontextmanager
async def domain_context(app, service, *, runtime=None, enabled=True,
                         database_factory=create_database, head=migration_head):
    state = app.state
    state.runtime = runtime or load_runtime(service)
    validate_keys(state.runtime)
    state.public_origin = public_origin()
    state.side_effect_policy = side_effect_policy()
    state.database = None
    state.background = None
    try:
        if state.runtime.db_url:
            state.database = database_factory(state.runtime.db_url.get_secret_value())
        state.migration_head = head(service) if state.database else None
        if enabled:
            await business.initialize(app, service)
        yield app
    finally:
        try:
            if state.background:
                await state.background.close()
        finally:
            try:
                if enabled:
                    await business.close(app)
            finally:
                if state.database:
                    await state.database.dispose()
