from __future__ import annotations

import argparse
import os
import sys

SCRIPT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
if SCRIPT_ROOT not in sys.path:
    sys.path.insert(0, SCRIPT_ROOT)

from shadow_music_models.config_store import ConfigStore
from shadow_music_models.startup_bootstrap import StartupBootstrap, StartupBootstrapError


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="启动 NeteaseCloudMusicApi 并通过终端二维码登录网易云。")
    parser.add_argument("--force", action="store_true", help="忽略本地已有 Cookie，强制重新扫码登录。")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    config_store = ConfigStore()
    bootstrap = StartupBootstrap(config_store)
    try:
        profile = bootstrap.ensure_authenticated(force_relogin=args.force)
    except StartupBootstrapError as exc:
        print(f"登录失败：{exc}")
        return 1

    nickname = profile.get("nickname") or "未知用户"
    user_id = profile.get("user_id") or "-"
    print(f"当前登录账号：{nickname} | UID={user_id}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
