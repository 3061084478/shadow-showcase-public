from __future__ import annotations

import argparse
import os
import sys
import time

from .http_server import build_app_context, JsonHttpServer


def main() -> int:
    app_root = os.environ.get("SHADOW_APP_ROOT", "").strip()
    if app_root and app_root not in sys.path:
        sys.path.insert(0, app_root)
    parser = argparse.ArgumentParser(description="Shadow Music 独立网站一期后端")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8787)
    args = parser.parse_args()

    context = build_app_context()
    server = JsonHttpServer((args.host, args.port), context)
    print(f"Shadow Music Site API 已启动: http://{args.host}:{args.port}")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("收到中断，正在关闭服务...")
    finally:
        server.server_close()
    time.sleep(0.1)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
