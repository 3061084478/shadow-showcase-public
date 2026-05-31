from __future__ import annotations

import argparse
import os
import sys

SCRIPT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
if SCRIPT_ROOT not in sys.path:
    sys.path.insert(0, SCRIPT_ROOT)

from shadow_music_models.account_playlists import build_playlist_summaries
from shadow_music_models.config_store import ConfigStore
from shadow_music_models.startup_bootstrap import StartupBootstrap, StartupBootstrapError


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="列出当前登录网易云账号下的全部歌单 ID。")
    parser.add_argument("--force-relogin", action="store_true", help="列歌单前强制重新扫码登录。")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    config_store = ConfigStore()
    bootstrap = StartupBootstrap(config_store)

    try:
        profile = bootstrap.ensure_authenticated(force_relogin=args.force_relogin)
    except StartupBootstrapError as exc:
        print(f"认证失败：{exc}")
        return 1

    user_id = str(profile.get("user_id") or "").strip()
    if not user_id:
        print("当前账号缺少 user_id，无法列出歌单。")
        return 1

    data = bootstrap.api_client.get_user_playlists(user_id)
    summaries = build_playlist_summaries(data.get("playlist") or [], current_user_id=user_id)
    if not summaries:
        print("当前账号下没有可用歌单。")
        return 0

    print(f"当前账号：{profile.get('nickname') or '未知用户'}")
    print("=== 歌单列表 ===")
    for index, item in enumerate(summaries, start=1):
        owner_flag = "我创建" if item["is_mine"] else "收藏"
        print(
            f"{index:>2}. {item['playlist_name'] or '未命名歌单'} | "
            f"ID={item['playlist_id']} | {item['track_count']} 首 | {owner_flag}"
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
