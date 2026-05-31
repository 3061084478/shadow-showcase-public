from __future__ import annotations

import argparse
import ast
import os
import re
import sys
from typing import Sequence

SCRIPT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
if SCRIPT_ROOT not in sys.path:
    sys.path.insert(0, SCRIPT_ROOT)

from shadow_music_models.collectors import PlaylistCollector
from shadow_music_models.config_store import ConfigStore
from shadow_music_models.scripts.run_song_tagger import main as run_song_tagger_main
from shadow_music_models.startup_bootstrap import StartupBootstrap, StartupBootstrapError


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="模型一路线A：采集歌单并直接打标，产出给模型二使用的 tagged.json。"
    )
    parser.add_argument("playlist_ids", nargs="+", help="一个或多个歌单 ID，或一个形如 ['a','b'] 的列表字符串。")
    parser.add_argument("--force-relogin", action="store_true", help="采集前强制重新扫码登录。")
    return parser


def _flatten_playlist_id_inputs(raw_values: Sequence[str]) -> list[str]:
    text = " ".join(str(item).strip() for item in raw_values if str(item).strip())
    if not text:
        return []

    extracted: list[str] = []
    seen: set[str] = set()

    try:
        if text.startswith("[") and text.endswith("]"):
            parsed = ast.literal_eval(text)
            if isinstance(parsed, (list, tuple, set)):
                for item in parsed:
                    value = str(item).strip()
                    if value and value not in seen:
                        extracted.append(value)
                        seen.add(value)
                if extracted:
                    return extracted
    except Exception:
        pass

    for match in re.findall(r"\d{3,}", text):
        if match in seen:
            continue
        extracted.append(match)
        seen.add(match)
    return extracted


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    playlist_ids = _flatten_playlist_id_inputs(args.playlist_ids)
    if not playlist_ids:
        print("没有可处理的 playlist_id。")
        return 1

    config_store = ConfigStore()
    bootstrap = StartupBootstrap(config_store)

    try:
        profile = bootstrap.ensure_authenticated(force_relogin=bool(args.force_relogin))
    except StartupBootstrapError as exc:
        print(f"采集前认证失败：{exc}")
        return 1

    print(f"API 已就绪，当前账号：{profile.get('nickname') or '未知用户'}")

    collector = PlaylistCollector(bootstrap.api_client, config_store)
    collected_playlist_ids: list[str] = []
    for playlist_id in playlist_ids:
        try:
            result = collector.collect_playlist(playlist_id)
            collected_playlist_ids.append(playlist_id)
            print(f"{playlist_id} | 采集完成 | songs {len(result.get('songs') or [])}")
        except Exception as exc:
            print(f"{playlist_id} | 采集失败 | {exc}")

    if not collected_playlist_ids:
        print("没有成功采集的歌单，未运行模型一。")
        return 1

    return run_song_tagger_main(collected_playlist_ids)


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
