from __future__ import annotations

from typing import Any, Dict, List

from .aggregate_features import build_playlist_profile


class PlaylistAnalyzer:
    def build_profile(
        self,
        playlist_id: str,
        playlist_name: str,
        songs: List[Dict[str, Any]],
        playlist_description: str = "",
    ) -> Dict[str, Any]:
        return build_playlist_profile(playlist_id, playlist_name, songs, playlist_description)

    @staticmethod
    def _top_keys(distribution: Dict[str, float], limit: int = 3) -> List[str]:
        return [key for key in list(distribution.keys())[:limit] if key and key != "未知"]

    def generate(self, playlist_profile: Dict[str, Any]) -> Dict[str, Any]:
        genre_distribution = playlist_profile.get("genre_distribution") or {}
        era_distribution = playlist_profile.get("era_distribution") or {}
        representative_songs = playlist_profile.get("representative_songs") or []

        genre_keys = self._top_keys(genre_distribution)
        era_keys = self._top_keys(era_distribution)

        genre_text = "、".join(genre_keys) if genre_keys else "未知风格"
        era_text = "、".join(era_keys) if era_keys else "时间分布不明"

        playlist_summary = (
            f"这是一份以{genre_text}为主的歌单。"
            if genre_keys
            else "这是一份仍需更多结构化信号补充的歌单。"
        )
        genre_analysis = (
            f"从流派分布看，歌单主要集中在{genre_text}，说明整体听感并不是随机堆叠，而是有明确偏向。"
            if genre_keys
            else "当前流派信号不足，暂时更适合先补充标签后再做判断。"
        )
        era_analysis = (
            f"年代分布主要落在{era_text}，因此歌单带有明显的时间层次，而不是只停留在单一时期。"
            if era_keys
            else "年代信息还不够完整，暂时不强行下时间结论。"
        )

        representative_song_analysis = "暂未筛出足够稳定的代表性歌曲。"
        representative_lines = []
        if representative_songs:
            picks = representative_songs[:2]
            representative_lines = [
                f"{item['song_name']} - {'/'.join(item.get('artist_names') or [])}".strip(" -")
                for item in picks
                if str(item.get("song_name") or "").strip()
            ]
            if representative_lines:
                representative_song_analysis = (
                    f"像{'、'.join(representative_lines)}这样的歌曲，能直接支撑歌单的主流派判断。"
                )

        representative_text = ""
        if representative_lines:
            representative_text = f"代表性歌曲方面，{'、'.join(representative_lines)}最能说明歌单的结构。"

        final_text_parts = [
            playlist_summary,
            genre_analysis,
            era_analysis,
            representative_text,
        ]
        final_text = " ".join(part for part in final_text_parts if part).strip()

        return {
            "playlist_summary": playlist_summary,
            "genre_analysis": genre_analysis,
            "era_analysis": era_analysis,
            "representative_song_analysis": representative_song_analysis,
            "final_text": final_text,
            "model_version": "playlist_analyzer_v1_genre_only",
        }
