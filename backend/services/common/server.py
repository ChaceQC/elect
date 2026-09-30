"""关闭访问日志，避免框架默认日志泄露查询串或认证参数。"""

import uvicorn


def serve(service):
    uvicorn.run(
        f"services.{service}.app:app",
        host="0.0.0.0",
        port=8000,
        access_log=False,
        proxy_headers=False,
        log_level="warning",
    )
