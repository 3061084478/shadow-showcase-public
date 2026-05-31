from __future__ import annotations

import argparse
import os
import sys

SCRIPT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
if SCRIPT_ROOT not in sys.path:
    sys.path.insert(0, SCRIPT_ROOT)

from shadow_music_models.account_playlists import build_playlist_summaries, parse_playlist_selection
from shadow_music_models.collectors import PlaylistCollector
from shadow_music_models.config_store import ConfigStore
from shadow_music_models.startup_bootstrap import StartupBootstrap, StartupBootstrapError


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="只采集指定歌单数据，不运行模型一和模型二。")
    parser.add_argument("playlist_ids", nargs="*", help="一个或多个网易云歌单 ID。")
    parser.add_argument("--force-relogin", action="store_true", help="采集前强制重新扫码登录。")
    parser.add_argument("--list-playlists", action="store_true", help="列出当前登录账号下的全部歌单 ID。")
    parser.add_argument("--select-playlists", action="store_true", help="列出当前账号歌单后按序号选择，并直接开始采集。")
    return parser


def _load_account_playlists(bootstrap: StartupBootstrap, profile: dict) -> list[dict]:
    user_id = str(profile.get("user_id") or "").strip()
    if not user_id:
        raise ValueError("当前账号缺少 user_id，无法列出歌单。")
    data = bootstrap.api_client.get_user_playlists(user_id)
    return build_playlist_summaries(data.get("playlist") or [], current_user_id=user_id)


def _print_account_playlists(playlists: list[dict]) -> None:
    if not playlists:
        print("当前账号下没有可用歌单。")
        return
    print("\n=== 当前账号歌单列表 ===")
    for index, item in enumerate(playlists, start=1):
        owner_flag = "我创建" if item["is_mine"] else "收藏"
        name = item["playlist_name"] or "未命名歌单"
        print(
            f"{index:>2}. {name} | ID={item['playlist_id']} | {item['track_count']} 首 | {owner_flag}"
        )


def _prompt_for_playlist_ids(playlists: list[dict]) -> list[str]:
    while True:
        selection = input("请输入要采集的歌单序号，支持逗号多选，或输入 all：").strip()
        try:
            selected_items = parse_playlist_selection(selection, playlists)
        except ValueError as exc:
            print(f"输入无效：{exc}")
            continue
        selected_ids = [item["playlist_id"] for item in selected_items if str(item.get("playlist_id") or "").strip()]
        if not selected_ids:
            print("没有选中可采集的歌单，请重新输入。")
            continue
        print(f"已选择 {len(selected_ids)} 个歌单：{', '.join(selected_ids)}")
        return selected_ids


def _merge_playlist_ids(*groups: list[str]) -> list[str]:
    merged: list[str] = []
    seen: set[str] = set()
    for group in groups:
        for playlist_id in group:
            normalized = str(playlist_id or "").strip()
            if not normalized or normalized in seen:
                continue
            merged.append(normalized)
            seen.add(normalized)
    return merged


def _safe_console_text(value: str) -> str:
    text = str(value or "")
    try:
        text.encode("gbk")
        return text
    except Exception:
        return text.encode("gbk", errors="replace").decode("gbk", errors="replace")



def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    config_store = ConfigStore()
    bootstrap = StartupBootstrap(config_store)

    try:
        profile = bootstrap.ensure_authenticated(force_relogin=args.force_relogin)
    except StartupBootstrapError as exc:
        print(f"采集前认证失败：{exc}")
        return 1

    print(f"API 已就绪，当前账号：{profile.get('nickname') or '未知用户'}")
    selected_playlist_ids: list[str] = []
    if args.list_playlists or args.select_playlists:
        try:
            playlists = _load_account_playlists(bootstrap, profile)
        except Exception as exc:  # pragma: no cover - integration path
            print(f"列出歌单失败：{exc}")
            return 1
        _print_account_playlists(playlists)
        if args.select_playlists:
            if not playlists:
                return 0
            selected_playlist_ids = _prompt_for_playlist_ids(playlists)
        elif not args.playlist_ids:
            return 0

    playlist_ids = _merge_playlist_ids(args.playlist_ids, selected_playlist_ids)
    if not playlist_ids:
        print("请提供至少一个 playlist_id，或者使用 --select-playlists 先列出歌单并按序号选择。")
        return 1

    collector = PlaylistCollector(bootstrap.api_client, config_store)

    try:
        results = collector.collect_playlists(playlist_ids)
    except Exception as exc:  # pragma: no cover - integration path
        print(f"采集失败：{exc}")
        return 1

    for result in results:
        report = result["report"]
        playlist_name = _safe_console_text(result["playlist_name"] or result["playlist_id"])
        print(
            f"歌单 {playlist_name} 采集完成："
            f"{report['song_count']} 首，报告 -> {result['report_path']}"
        )

    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
