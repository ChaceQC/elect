"""容器内探测：凭据不出现在命令行，失败只返回退出码。"""

import os
import ssl
import sys
import urllib.request


def main():
    if sys.argv[1:] == ["worker"]:
        from .heartbeat import job_healthy

        sys.exit(0 if job_healthy() else 1)
    try:
        tls = bool(os.environ.get("ELECT_INTERNAL_TLS_CERT_FILE"))
        context = (
            ssl.create_default_context(cafile=os.environ["ELECT_INTERNAL_CA_FILE"]) if tls else None
        )
        url = "https://localhost:8000/health/ready" if tls else "http://127.0.0.1:8000/health/ready"
        with urllib.request.urlopen(url, context=context, timeout=4) as response:
            if response.status != 200:
                raise ValueError("not ready")
    except Exception:
        sys.exit(1)


if __name__ == "__main__":
    main()
