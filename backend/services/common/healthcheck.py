"""容器内探测：凭据不出现在命令行，失败只返回退出码。"""

import sys
import urllib.request


def main():
    try:
        with urllib.request.urlopen("http://127.0.0.1:8000/health/ready", timeout=4) as response:
            if response.status != 200:
                raise ValueError("not ready")
    except Exception:
        sys.exit(1)


if __name__ == "__main__":
    main()
