from __future__ import annotations

import math
from collections import Counter, defaultdict
from datetime import datetime
from typing import Any, Dict, Iterable, List, Optional, Tuple

from .bootstrap import StartupBootstrap
from .storage import SiteRepository


def _year_bucket(value: str) -> str:
    text = str(value or "").strip()
    if len(text) >= 4 and text[:4].isdigit():
        return text[:4]
    return "未知时间"


def _month_bucket(value: str) -> str:
    text = str(value or "").strip()
    if len(text) >= 7 and text[4] == "-" and text[:4].isdigit():
        return text[:7]
    return "未知月份"


def _parse_dt(value: str) -> datetime | None:
    text = str(value or "").strip()
    if not text:
        return None
    try:
        return datetime.strptime(text, "%Y-%m-%d %H:%M:%S")
    except ValueError:
        return None


def _normalize_artist_name(value: Any) -> str:
    return str(value or "").strip().casefold()


class MusicRelationService:
    def __init__(self, repository: SiteRepository, bootstrap: StartupBootstrap) -> None:
        self.repository = repository
        self.bootstrap = bootstrap

    @staticmethod
    def _share_rows_to_song_payload(rows: Iterable[Dict[str, Any]]) -> List[Dict[str, Any]]:
        return [
            {
                "song_name": row.get("song_name") or "",
                "artist_names": row.get("artist_names") or [],
                "album_name": row.get("album_name") or "",
                "publish_time": row.get("publish_time") or "",
                "genre_label": row.get("genre_label") or "",
                "direction": row.get("direction") or "",
                "sender_name": row.get("sender_name") or "",
                "sender_uid": row.get("sender_uid") or "",
                "uid": row.get("uid") or "",
                "msg_time_str": row.get("msg_time_str") or "",
            }
            for row in rows
        ]

    @staticmethod
    def _distribution(rows: Iterable[Dict[str, Any]], field: str) -> List[Dict[str, Any]]:
        counter: Counter[str] = Counter()
        for row in rows:
            value = str(row.get(field) or "").strip()
            if not value:
                continue
            counter[value] += 1
        total = sum(counter.values())
        result: List[Dict[str, Any]] = []
        for name, count in counter.most_common():
            ratio = round(count / total, 4) if total else 0.0
            result.append({"name": name, "count": int(count), "ratio": ratio})
        return result

    @staticmethod
    def _top_artists(rows: Iterable[Dict[str, Any]]) -> List[Dict[str, Any]]:
        counter: Counter[str] = Counter()
        for row in rows:
            for artist in row.get("artist_names") or []:
                name = str(artist or "").strip()
                if name:
                    counter[name] += 1
        return [{"name": name, "count": int(count)} for name, count in counter.most_common(10)]

    @staticmethod
    def _genre_overlap(my_rows: Iterable[Dict[str, Any]], friend_rows: Iterable[Dict[str, Any]]) -> Dict[str, Any]:
        my_counter = Counter(str(row.get("genre_label") or "").strip() for row in my_rows if str(row.get("genre_label") or "").strip())
        friend_counter = Counter(str(row.get("genre_label") or "").strip() for row in friend_rows if str(row.get("genre_label") or "").strip())
        overlap = []
        for genre in sorted(set(my_counter) & set(friend_counter), key=lambda name: (-(my_counter[name] + friend_counter[name]), name)):
            overlap.append(
                {
                    "genre_label": genre,
                    "my_count": int(my_counter[genre]),
                    "friend_count": int(friend_counter[genre]),
                    "shared_count": int(my_counter[genre] + friend_counter[genre]),
                }
            )
        return {"genres": overlap, "overlap_count": len(overlap)}

    @staticmethod
    def _hour_heatmap(raw_rows: Iterable[Dict[str, Any]], song_rows: Optional[Iterable[Dict[str, Any]]] = None) -> Dict[str, Any]:
        def bucket_for_hour(hour: int) -> str:
            if 6 <= hour <= 17:
                return "白天时段"
            if 18 <= hour <= 23:
                return "夜间时段"
            return "深夜时段"

        def build_hour_series(rows: Iterable[Dict[str, Any]]) -> Tuple[List[Dict[str, Any]], Counter[str]]:
            hours = [{"hour": hour, "count": 0, "bucket": bucket_for_hour(hour)} for hour in range(24)]
            label_counter: Counter[str] = Counter()
            for row in rows:
                dt = _parse_dt(str(row.get("msg_time_str") or ""))
                if not dt:
                    continue
                hour = dt.hour
                bucket = bucket_for_hour(hour)
                hours[hour]["count"] += 1
                hours[hour]["bucket"] = bucket
                label_counter[bucket] += 1
            return hours, label_counter

        hours, label_counter = build_hour_series(raw_rows)
        song_hours, _ = build_hour_series(song_rows or [])
        total = sum(item["count"] for item in hours)
        bucket_ratios = []
        for label in ["白天时段", "夜间时段", "深夜时段"]:
            count = int(label_counter.get(label, 0))
            ratio = round(count / total, 4) if total else 0.0
            bucket_ratios.append({"label": label, "count": count, "ratio": ratio})
        dominant = max(bucket_ratios, key=lambda item: item["count"], default={"label": "白天时段", "ratio": 0.0})
        conclusion = f"{dominant['label']}互动特征明显，核心活跃时段贡献约 {round(float(dominant['ratio']) * 100, 1)}%。"
        return {
            "hours": hours,
            "song_hours": song_hours,
            "bucket_ratios": bucket_ratios,
            "dominant_bucket": dominant["label"],
            "conclusion": conclusion,
        }

    def _trend_series(
        self,
        raw_rows: List[Dict[str, Any]],
        deduped_rows: List[Dict[str, Any]],
        my_rows: List[Dict[str, Any]],
        friend_rows: List[Dict[str, Any]],
        timeline_song_rows: List[Dict[str, Any]] | None = None,
    ) -> List[Dict[str, Any]]:
        raw_counter: Dict[str, int] = defaultdict(int)
        total_counter: Dict[str, int] = defaultdict(int)
        my_counter: Dict[str, int] = defaultdict(int)
        friend_counter: Dict[str, int] = defaultdict(int)
        for row in raw_rows:
            raw_counter[_month_bucket(row.get("msg_time_str") or "")] += 1
        for row in deduped_rows:
            total_counter[_month_bucket(row.get("msg_time_str") or "")] += 1
        for row in my_rows:
            my_counter[_month_bucket(row.get("msg_time_str") or "")] += 1
        for row in friend_rows:
            friend_counter[_month_bucket(row.get("msg_time_str") or "")] += 1

        periods = sorted(set(raw_counter) | set(total_counter) | set(my_counter) | set(friend_counter))
        if timeline_song_rows:
            periods = sorted(set(periods) | {
                _month_bucket(row.get("msg_time_str") or "")
                for row in timeline_song_rows
                if _month_bucket(row.get("msg_time_str") or "") != "未知月份"
            })
        if not periods:
            return []
        peak = max((total_counter.get(period, 0) for period in periods), default=0)
        result = []
        previous_count = None
        for period in periods:
            current_count = total_counter.get(period, 0)
            if peak > 0 and current_count >= peak * 0.75:
                phase = "爆发期"
            elif previous_count is not None and current_count < previous_count * 0.45:
                phase = "回落期"
            else:
                phase = "稳定期"
            result.append(
                {
                    "period": period,
                    "message_count_raw": int(raw_counter.get(period, 0)),
                    "distinct_song_count": int(current_count),
                    "my_distinct_song_count": int(my_counter.get(period, 0)),
                    "friend_distinct_song_count": int(friend_counter.get(period, 0)),
                    "phase_label": phase,
                }
            )
            previous_count = current_count
        return result

    @staticmethod
    def _timeline_visual(
        raw_rows: List[Dict[str, Any]],
        trend_series: List[Dict[str, Any]],
        song_rows: List[Dict[str, Any]],
    ) -> Dict[str, Any]:
        nodes: List[Dict[str, Any]] = []
        if raw_rows:
            first = raw_rows[0]
            nodes.append(
                {
                    "title": "第一次分享",
                    "period": _month_bucket(first.get("msg_time_str") or ""),
                    "description": f"关系起点在 { _month_bucket(first.get('msg_time_str') or '') }，第一条归档消息落在这里。",
                }
            )
        if top_artists:
            nodes.append(
                {
                    "title": "第一次被带入歌手",
                    "period": trend_series[0]["period"] if trend_series else "未知月份",
                    "description": f"最早形成存在感的歌手是 {top_artists[0]['name']}。",
                }
            )
        if trend_series:
            peak = max(trend_series, key=lambda item: int(item.get("distinct_song_count") or 0))
            nodes.append(
                {
                    "title": "高峰阶段",
                    "period": peak["period"],
                    "description": f"{peak['period']} 到达阶段峰值，歌曲 {peak['distinct_song_count']} 首，消息 {peak['message_count_raw']} 条。",
                }
            )
            for previous, current in zip(trend_series, trend_series[1:]):
                delta = int(current.get("distinct_song_count") or 0) - int(previous.get("distinct_song_count") or 0)
                if delta >= 5:
                    nodes.append(
                        {
                            "title": "爆发转折",
                            "period": current["period"],
                            "description": f"{current['period']} 出现显著增长（环比 +{delta} 首歌曲）。",
                        }
                    )
                    break
            for previous, current in zip(trend_series, trend_series[1:]):
                delta = int(current.get("distinct_song_count") or 0) - int(previous.get("distinct_song_count") or 0)
                if delta <= -5:
                    nodes.append(
                        {
                            "title": "回落转折",
                            "period": current["period"],
                            "description": f"{current['period']} 出现明显回落（环比 {delta} 首歌曲）。",
                        }
                    )
                    break
        return {"nodes": nodes}

    @staticmethod
    def _timeline_visual(
        raw_rows: List[Dict[str, Any]],
        trend_series: List[Dict[str, Any]],
        song_rows: List[Dict[str, Any]],
    ) -> Dict[str, Any]:
        nodes: List[Dict[str, Any]] = []
        if raw_rows:
            first = min(raw_rows, key=lambda row: _parse_dt(str(row.get("msg_time_str") or "")) or datetime.max)
            first_period = _month_bucket(first.get("msg_time_str") or "")
            nodes.append(
                {
                    "title": "社交故事开始",
                    "period": first_period,
                    "description": f"{first_period} 出现第一条真实归档消息，关系故事从这里开始。",
                }
            )

        song_candidates = [
            row
            for row in song_rows
            if _month_bucket(row.get("msg_time_str") or "") != "未知月份" and (row.get("artist_names") or row.get("song_name"))
        ]
        if song_candidates:
            first_song = min(song_candidates, key=lambda row: _parse_dt(str(row.get("msg_time_str") or "")) or datetime.max)
            first_song_period = _month_bucket(first_song.get("msg_time_str") or "")
            artist_names = [str(name or "").strip() for name in (first_song.get("artist_names") or []) if str(name or "").strip()]
            artist_text = " / ".join(artist_names[:3])
            song_name = str(first_song.get("song_name") or "").strip()
            detail = artist_text or song_name
            if detail:
                nodes.append(
                    {
                        "title": "第一次被带入歌手",
                        "period": first_song_period,
                        "description": f"{first_song_period} 第一次出现真实歌曲记录，歌手是 {detail}。",
                    }
                )

        if trend_series:
            peak = max(trend_series, key=lambda item: int(item.get("distinct_song_count") or 0) + int(item.get("message_count_raw") or 0))
            if int(peak.get("distinct_song_count") or 0) > 0 or int(peak.get("message_count_raw") or 0) > 0:
                nodes.append(
                    {
                        "title": "高峰阶段",
                        "period": peak["period"],
                        "description": f"{peak['period']} 达到阶段峰值，歌曲 {peak['distinct_song_count']} 首，消息 {peak['message_count_raw']} 条。",
                    }
                )
            for previous, current in zip(trend_series, trend_series[1:]):
                delta = int(current.get("distinct_song_count") or 0) - int(previous.get("distinct_song_count") or 0)
                if delta >= 5:
                    nodes.append(
                        {
                            "title": "爆发转折",
                            "period": current["period"],
                            "description": f"{current['period']} 歌曲分享明显增加，环比多 {delta} 首。",
                        }
                    )
                    break
            for previous, current in zip(trend_series, trend_series[1:]):
                delta = int(current.get("distinct_song_count") or 0) - int(previous.get("distinct_song_count") or 0)
                if delta <= -5:
                    nodes.append(
                        {
                            "title": "回落转折",
                            "period": current["period"],
                            "description": f"{current['period']} 歌曲分享明显回落，环比 {delta} 首。",
                        }
                    )
                    break
        return {"nodes": nodes}

    @staticmethod
    def _silence_and_burst(raw_rows: List[Dict[str, Any]], trend_series: List[Dict[str, Any]]) -> Dict[str, Any]:
        longest_gap_days = 0
        recover_point = ""
        sorted_dates = [_parse_dt(str(row.get("msg_time_str") or "")) for row in raw_rows]
        sorted_dates = [item for item in sorted_dates if item is not None]
        for left, right in zip(sorted_dates, sorted_dates[1:]):
            gap_days = (right - left).days
            if gap_days > longest_gap_days:
                longest_gap_days = gap_days
                recover_point = right.strftime("%Y-%m")
        peak = max(trend_series, key=lambda item: int(item.get("distinct_song_count") or 0), default=None)
        return {
            "longest_silence_days": longest_gap_days,
            "recover_period": recover_point,
            "peak_period": peak.get("period") if peak else "",
            "peak_song_count": int(peak.get("distinct_song_count") or 0) if peak else 0,
        }

    @staticmethod
    def _artist_overview(
        my_rows: List[Dict[str, Any]],
        friend_rows: List[Dict[str, Any]],
        all_rows: List[Dict[str, Any]],
        my_raw_rows: List[Dict[str, Any]] | None = None,
        friend_raw_rows: List[Dict[str, Any]] | None = None,
    ) -> Dict[str, Any]:
        my_top = MusicRelationService._top_artists(my_rows)
        friend_top = MusicRelationService._top_artists(friend_rows)
        overall_counter: Counter[str] = Counter()
        my_counter: Counter[str] = Counter()
        friend_counter: Counter[str] = Counter()
        display_counter: defaultdict[str, Counter[str]] = defaultdict(Counter)
        my_raw_counter: Counter[str] = Counter()
        friend_raw_counter: Counter[str] = Counter()

        source_my_raw_rows = my_raw_rows if my_raw_rows is not None else my_rows
        source_friend_raw_rows = friend_raw_rows if friend_raw_rows is not None else friend_rows

        for row in my_rows:
            seen_names: set[str] = set()
            for artist in row.get("artist_names") or []:
                display_name = str(artist or "").strip()
                name = _normalize_artist_name(display_name)
                if not name or name in seen_names:
                    continue
                seen_names.add(name)
                my_counter[name] += 1
                display_counter[name][display_name] += 1

        for row in friend_rows:
            seen_names: set[str] = set()
            for artist in row.get("artist_names") or []:
                display_name = str(artist or "").strip()
                name = _normalize_artist_name(display_name)
                if not name or name in seen_names:
                    continue
                seen_names.add(name)
                friend_counter[name] += 1
                display_counter[name][display_name] += 1

        for row in all_rows:
            seen_names: set[str] = set()
            for artist in row.get("artist_names") or []:
                display_name = str(artist or "").strip()
                name = _normalize_artist_name(display_name)
                if not name or name in seen_names:
                    continue
                seen_names.add(name)
                overall_counter[name] += 1
                display_counter[name][display_name] += 1

        for row in source_my_raw_rows:
            for artist in row.get("artist_names") or []:
                display_name = str(artist or "").strip()
                name = _normalize_artist_name(display_name)
                if not name:
                    continue
                my_raw_counter[name] += 1
                display_counter[name][display_name] += 1

        for row in source_friend_raw_rows:
            for artist in row.get("artist_names") or []:
                display_name = str(artist or "").strip()
                name = _normalize_artist_name(display_name)
                if not name:
                    continue
                friend_raw_counter[name] += 1
                display_counter[name][display_name] += 1

        common_names = set(my_counter) & set(friend_counter)
        common = [
            {
                "name": display_counter[name].most_common(1)[0][0] if display_counter[name] else name,
                "count": int(my_raw_counter[name] + friend_raw_counter[name]),
                "my_count": int(my_raw_counter[name]),
                "friend_count": int(friend_raw_counter[name]),
            }
            for name in common_names
        ]
        common.sort(
            key=lambda item: (
                -int(item["count"]),
                -int(my_raw_counter.get(_normalize_artist_name(item["name"]), 0) + friend_raw_counter.get(_normalize_artist_name(item["name"]), 0)),
                item["name"],
            )
        )
        overall = [
            {
                "name": display_counter[name].most_common(1)[0][0] if display_counter[name] else name,
                "count": int(count),
            }
            for name, count in overall_counter.most_common(10)
        ]
        return {
            "my_top_artists": my_top[:5],
            "friend_top_artists": friend_top[:5],
            "common_artists": common[:5],
            "common_artist_total": len(common),
            "representative_artist": overall[0] if overall else {},
        }

    @staticmethod
    def _common_world(genre_overlap: Dict[str, Any], artist_overview: Dict[str, Any], decade_distribution: List[Dict[str, Any]]) -> Dict[str, Any]:
        return {
            "shared_genres": genre_overlap.get("genres", [])[:6],
            "shared_artists": artist_overview.get("common_artists", [])[:5],
            "shared_artist_total": int(artist_overview.get("common_artist_total") or 0),
            "shared_decades": decade_distribution[:4],
        }

    @staticmethod
    def _safe_ratio(numerator: int, denominator: int) -> float:
        if denominator <= 0:
            return 0.0
        return round(numerator / denominator, 4)

    def _self_account_profile(self) -> Dict[str, str]:
        try:
            return self.bootstrap.ensure_authenticated()
        except Exception:
            return {}

    def _friend_avatar_map(self) -> Dict[str, str]:
        return {
            str(row.get("uid") or "").strip(): str(row.get("avatar_url") or "").strip()
            for row in self.repository.list_friends()
            if str(row.get("uid") or "").strip()
        }

    @staticmethod
    def _log_ratio(value: int, max_value: int) -> float:
        if value <= 0 or max_value <= 0:
            return 0.0
        return math.log1p(min(value, max_value)) / math.log1p(max_value)

    @staticmethod
    def _balance_score(left_count: int, right_count: int) -> float:
        total = left_count + right_count
        if total <= 0:
            return 0.0
        return min(left_count, right_count) / max(left_count, right_count)

    @classmethod
    def _relation_temperature_score(
        cls,
        *,
        message_count: int,
        song_count: int,
        active_day_count: int,
        my_song_count: int,
        friend_song_count: int,
        max_message_count: int,
        max_song_count: int,
        max_active_day_count: int,
    ) -> int:
        message_part = cls._log_ratio(message_count, max_message_count)
        song_part = cls._log_ratio(song_count, max_song_count)
        active_part = cls._log_ratio(active_day_count, max_active_day_count)
        balance_part = cls._balance_score(my_song_count, friend_song_count)
        if message_count <= 0 and song_count <= 0:
            return 0
        score = 8 + message_part * 30 + song_part * 42 + active_part * 12 + balance_part * 8
        return max(1, min(99, int(round(score))))

    def _global_top3(
        self,
        friend_rows: List[Dict[str, Any]],
        avatar_map: Dict[str, str],
    ) -> Dict[str, List[Dict[str, Any]]]:
        chat_top3: List[Dict[str, Any]] = []
        song_top3: List[Dict[str, Any]] = []
        temperature_top3: List[Dict[str, Any]] = []

        metric_rows: List[Dict[str, Any]] = []
        for friend in friend_rows:
            uid = str(friend.get("uid") or "").strip()
            if not uid:
                continue
            nickname = str(friend.get("nickname") or uid).strip() or uid
            raw_messages = self.repository.query_raw_messages(uid)
            deduped_rows = self.repository.distinct_shared_song_rows(uid)
            known_rows = [row for row in deduped_rows if str(row.get("genre_status") or "") == "known"]
            my_known_rows = [row for row in known_rows if str(row.get("direction") or "") == "self"]
            friend_known_rows = [row for row in known_rows if str(row.get("direction") or "") == "friend"]
            active_days = {
                str(row.get("msg_time_str") or "")[:10]
                for row in raw_messages
                if str(row.get("msg_time_str") or "")[:10]
            }
            metric_base = {
                "uid": uid,
                "nickname": nickname,
                "avatar_url": avatar_map.get(uid) or None,
            }
            metric_rows.append(
                {
                    **metric_base,
                    "message_count": len(raw_messages),
                    "song_count": len(deduped_rows),
                    "known_song_count": len(known_rows),
                    "my_song_count": len(my_known_rows),
                    "friend_song_count": len(friend_known_rows),
                    "active_day_count": len(active_days),
                }
            )

        max_message_count = max((int(row.get("message_count") or 0) for row in metric_rows), default=0)
        max_song_count = max((int(row.get("known_song_count") or 0) for row in metric_rows), default=0)
        max_active_day_count = max((int(row.get("active_day_count") or 0) for row in metric_rows), default=0)

        for row in metric_rows:
            metric_base = {
                "uid": row["uid"],
                "nickname": row["nickname"],
                "avatar_url": row["avatar_url"],
            }
            raw_message_count = int(row.get("message_count") or 0)
            deduped_song_count = int(row.get("song_count") or 0)
            known_song_count = int(row.get("known_song_count") or 0)
            chat_top3.append({**metric_base, "value": raw_message_count})
            song_top3.append({**metric_base, "value": deduped_song_count})
            temperature_top3.append(
                {
                    **metric_base,
                    "value": self._relation_temperature_score(
                        message_count=raw_message_count,
                        song_count=known_song_count,
                        active_day_count=int(row.get("active_day_count") or 0),
                        my_song_count=int(row.get("my_song_count") or 0),
                        friend_song_count=int(row.get("friend_song_count") or 0),
                        max_message_count=max_message_count,
                        max_song_count=max_song_count,
                        max_active_day_count=max_active_day_count,
                    ),
                }
            )

        def sort_items(items: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
            items.sort(key=lambda item: (-int(item.get("value") or 0), str(item.get("nickname") or ""), str(item.get("uid") or "")))
            return items[:3]

        return {
            "chat_top3": sort_items(chat_top3),
            "song_top3": sort_items(song_top3),
            "temperature_top3": sort_items(temperature_top3),
        }

    def _global_social_structure(
        self,
        friend_rows: List[Dict[str, Any]],
        friend_map: Dict[str, str],
        avatar_map: Dict[str, str],
        raw_messages: List[Dict[str, Any]],
        known_rows: List[Dict[str, Any]],
        my_rows: List[Dict[str, Any]],
        friend_song_rows: List[Dict[str, Any]],
    ) -> Dict[str, Any]:
        music_input_counter: Counter[str] = Counter()
        music_output_counter: Counter[str] = Counter()
        chat_input_counter: Counter[str] = Counter()
        chat_output_counter: Counter[str] = Counter()

        for row in friend_song_rows:
            uid = str(row.get("uid") or "").strip()
            if uid:
                music_input_counter[uid] += 1

        for row in my_rows:
            uid = str(row.get("uid") or "").strip()
            if uid:
                music_output_counter[uid] += 1

        for row in raw_messages:
            uid = str(row.get("uid") or "").strip()
            if not uid:
                continue
            if str(row.get("direction") or "") == "friend":
                chat_input_counter[uid] += 1
            else:
                chat_output_counter[uid] += 1

        def io_label(output_count: int, input_count: int, *, output_text: str, input_text: str, balance_text: str) -> str:
            if output_count > input_count * 1.4:
                return output_text
            if input_count > output_count * 1.4:
                return input_text
            return balance_text

        def density_label(counter: Counter[str], total_count: int, *, singular_text: str) -> str:
            if total_count <= 0 or not counter:
                return "低集中"
            top_value = counter.most_common(1)[0][1]
            ratio = self._safe_ratio(top_value, total_count)
            if ratio >= 0.65:
                return "高集中"
            if ratio >= 0.35:
                return "中集中"
            if len(counter) <= 2:
                return singular_text
            return "低集中"

        def graph_payload(title: str, counter: Counter[str], summary_prefix: str) -> Dict[str, Any]:
            total = sum(counter.values())
            top_uid = counter.most_common(1)[0][0] if counter else ""
            top_name = friend_map.get(top_uid, top_uid) if top_uid else "暂无"
            top_count = counter.get(top_uid, 0) if top_uid else 0
            ratio = self._safe_ratio(top_count, total)
            nodes = [
                {
                    "uid": uid,
                    "nickname": friend_map.get(uid, uid),
                    "avatar_url": avatar_map.get(uid) or None,
                    "value": int(value),
                }
                for uid, value in counter.most_common(5)
            ]
            return {
                "title": title,
                "summary": f"{summary_prefix}以{top_name}为核心（{top_count}，占比 {round(ratio * 100, 1)}%）。" if total > 0 else f"{summary_prefix}当前还没有形成明显中心。",
                "nodes": nodes,
            }

        total_music_input = sum(music_input_counter.values())
        total_music_output = sum(music_output_counter.values())
        total_chat_input = sum(chat_input_counter.values())
        total_chat_output = sum(chat_output_counter.values())

        return {
            "music_io_type": {
                "label": "音乐输入/输出类型",
                "summary": io_label(total_music_output, total_music_input, output_text="输出型", input_text="输入型", balance_text="平衡型"),
            },
            "chat_io_type": {
                "label": "聊天输入/输出类型",
                "summary": io_label(total_chat_output, total_chat_input, output_text="输出型", input_text="输入型", balance_text="平衡型"),
            },
            "music_circle_density": {
                "label": "音乐圈层浓度",
                "summary": density_label(music_output_counter + music_input_counter, len(known_rows), singular_text="双核心"),
            },
            "chat_circle_density": {
                "label": "聊天圈层浓度",
                "summary": density_label(chat_output_counter + chat_input_counter, len(raw_messages), singular_text="双核心"),
            },
            "music_input_graph": graph_payload("音乐输入", music_input_counter, "音乐输入网络"),
            "music_output_graph": graph_payload("音乐输出", music_output_counter, "音乐输出网络"),
            "chat_input_graph": graph_payload("聊天输入", chat_input_counter, "聊天输入网络"),
            "chat_output_graph": graph_payload("聊天输出", chat_output_counter, "聊天输出网络"),
        }

    @staticmethod
    def _dual_perspective(my_rows: List[Dict[str, Any]], friend_rows: List[Dict[str, Any]]) -> Dict[str, Any]:
        my_count = len(my_rows)
        friend_count = len(friend_rows)
        if my_count > friend_count * 1.4:
            label = "我方主导型"
        elif friend_count > my_count * 1.4:
            label = "好友输入型"
        else:
            label = "平衡交换型"
        return {
            "label": label,
            "my_output_count": my_count,
            "friend_output_count": friend_count,
        }

    @staticmethod
    def _annual_review(raw_rows: List[Dict[str, Any]], deduped_rows: List[Dict[str, Any]]) -> Dict[str, Any]:
        message_counter: Dict[str, int] = defaultdict(int)
        song_counter: Dict[str, int] = defaultdict(int)
        for row in raw_rows:
            message_counter[_year_bucket(row.get("msg_time_str") or "")] += 1
        for row in deduped_rows:
            song_counter[_year_bucket(row.get("publish_time") or row.get("msg_time_str") or "")] += 1
        years = sorted(set(message_counter) | set(song_counter))
        return {
            "years": [
                {
                    "year": year,
                    "message_count": int(message_counter.get(year, 0)),
                    "song_count": int(song_counter.get(year, 0)),
                }
                for year in years
            ]
        }

    @staticmethod
    def _evidence_tracks(rows: List[Dict[str, Any]], trend_series: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        if not rows:
            return []
        evidence: List[Dict[str, Any]] = []
        first = rows[0]
        evidence.append(
            {
                "title": "起点样本",
                "period": _month_bucket(first.get("msg_time_str") or ""),
                "song_name": first.get("song_name") or "",
                "artist_names": first.get("artist_names") or [],
                "genre_label": first.get("genre_label") or "",
            }
        )
        if trend_series:
            peak_period = max(trend_series, key=lambda item: int(item.get("distinct_song_count") or 0))["period"]
            peak_row = next((row for row in rows if _month_bucket(row.get("msg_time_str") or "") == peak_period), rows[-1])
            evidence.append(
                {
                    "title": "高峰样本",
                    "period": peak_period,
                    "song_name": peak_row.get("song_name") or "",
                    "artist_names": peak_row.get("artist_names") or [],
                    "genre_label": peak_row.get("genre_label") or "",
                }
            )
        latest = rows[-1]
        evidence.append(
            {
                "title": "最近样本",
                "period": _month_bucket(latest.get("msg_time_str") or ""),
                "song_name": latest.get("song_name") or "",
                "artist_names": latest.get("artist_names") or [],
                "genre_label": latest.get("genre_label") or "",
            }
        )
        return evidence

    @staticmethod
    def _build_cover_line(friend_name: str, relation_label: str, peak_period: str, message_count: int, song_count: int) -> str:
        if peak_period:
            return f"{relation_label} · 互动高峰出现在 {peak_period}（消息 {message_count} / 歌曲 {song_count}），当前关系保持稳定节奏。"
        return f"{friend_name} 的关系样本已归档，但峰值阶段仍待进一步形成。"

    def friend_relation(self, uid: str) -> Dict[str, Any]:
        friend_meta = self.repository.get_friend(uid) or {"uid": uid, "nickname": uid}
        raw_rows = self.repository.query_raw_messages(uid)
        deduped_all_rows = self.repository.distinct_shared_song_rows(uid)
        known_rows = [row for row in deduped_all_rows if str(row.get("genre_status") or "") == "known"]
        unknown_rows = [row for row in deduped_all_rows if str(row.get("genre_status") or "") == "unknown"]
        my_known_rows = self.repository.distinct_shared_song_rows(uid, known_only=True, direction="self")
        friend_known_rows = self.repository.distinct_shared_song_rows(uid, known_only=True, direction="friend")
        my_known_raw_rows = self.repository.query_shared_song_messages(uid, direction="self", known_only=True)
        friend_known_raw_rows = self.repository.query_shared_song_messages(uid, direction="friend", known_only=True)
        raw_song_rows = self.repository.query_shared_song_messages(uid, known_only=False)
        trend_series = self._trend_series(raw_rows, known_rows, my_known_rows, friend_known_rows, raw_song_rows)
        timeline_visual = self._timeline_visual(raw_rows, trend_series, raw_song_rows)
        heatmap = self._hour_heatmap(raw_rows, known_rows)
        silence_and_burst = self._silence_and_burst(raw_rows, trend_series)
        artist_overview = self._artist_overview(my_known_rows, friend_known_rows, known_rows, my_known_raw_rows, friend_known_raw_rows)
        decade_distribution = self._distribution([{"bucket": _year_bucket(row.get("publish_time") or "")} for row in known_rows], "bucket")[:10]
        genre_overlap = self._genre_overlap(my_known_raw_rows, friend_known_raw_rows)
        dual_perspective = self._dual_perspective(my_known_rows, friend_known_rows)
        annual_review = self._annual_review(raw_rows, known_rows)
        evidence_tracks = self._evidence_tracks(known_rows, trend_series)
        common_world = self._common_world(genre_overlap, artist_overview, decade_distribution)
        peak = max(trend_series, key=lambda item: int(item.get("distinct_song_count") or 0), default=None)
        active_day_count = len(set(str(row.get("msg_time_str") or "")[:10] for row in raw_rows if str(row.get("msg_time_str") or "")[:10]))
        temperature_score = self._relation_temperature_score(
            message_count=len(raw_rows),
            song_count=len(known_rows),
            active_day_count=active_day_count,
            my_song_count=len(my_known_rows),
            friend_song_count=len(friend_known_rows),
            max_message_count=5000,
            max_song_count=420,
            max_active_day_count=180,
        )
        if temperature_score >= 85:
            relation_label = "高温关系"
        elif temperature_score >= 65:
            relation_label = "稳定共振"
        elif temperature_score >= 40:
            relation_label = "持续连接"
        else:
            relation_label = "关系待细化"

        profile = {
            "uid": uid,
            "friend_name": friend_meta.get("nickname") or uid,
            "message_count_total": len(raw_rows),
            "song_share_count_total": len(deduped_all_rows),
            "active_days_total": active_day_count,
            "known_song_count": len(known_rows),
            "unknown_song_count": len(unknown_rows),
            "my_song_count": len(my_known_rows),
            "friend_song_count": len(friend_known_rows),
            "my_top_genres": self._distribution(my_known_rows, "genre_label")[:10],
            "friend_top_genres": self._distribution(friend_known_rows, "genre_label")[:10],
            "overall_top_genres": self._distribution(known_rows, "genre_label")[:10],
            "top_artists": self._top_artists(known_rows),
            "decade_distribution": decade_distribution,
            "top_languages": [],
            "top_moods": [],
            "genre_overlap": genre_overlap,
            "songs": self._share_rows_to_song_payload(known_rows),
            "relation_temperature": {"score": temperature_score, "label": relation_label},
            "trend_series": trend_series,
            "trend_conclusion": f"{peak['period']} 是这段关系的歌曲高峰期，当前整体呈现 {relation_label}。" if peak else "暂无趋势结论。",
            "activity_conclusion": heatmap["conclusion"],
            "cover_line": self._build_cover_line(friend_meta.get("nickname") or uid, relation_label, peak["period"] if peak else "", int(peak["message_count_raw"]) if peak else 0, int(peak["distinct_song_count"]) if peak else 0),
            "timeline_visual": timeline_visual,
            "silence_and_burst": silence_and_burst,
            "network_block": {},
            "artist_overview": artist_overview,
            "personality_cards": [],
            "personality_tags": [relation_label, dual_perspective["label"]],
            "evidence_tracks": evidence_tracks,
            "common_world": common_world,
            "dual_perspective": dual_perspective,
            "annual_review": annual_review,
            "activity_heatmap": heatmap,
        }
        return profile

    def friend_annual_relation(self, uid: str) -> Dict[str, Any]:
        rows = self.repository.distinct_shared_song_rows(uid, known_only=True)
        yearly_counter: Dict[str, Dict[str, int]] = defaultdict(lambda: {"song_count": 0, "my_song_count": 0, "friend_song_count": 0})
        for row in rows:
            year = _year_bucket(row.get("publish_time") or row.get("msg_time_str") or "")
            yearly_counter[year]["song_count"] += 1
            if str(row.get("direction") or "") == "self":
                yearly_counter[year]["my_song_count"] += 1
            else:
                yearly_counter[year]["friend_song_count"] += 1
        return {
            "uid": uid,
            "years": [{"year": year, **counts} for year, counts in sorted(yearly_counter.items())],
        }

    def friend_similarity(self, uid: str) -> Dict[str, Any]:
        target_rows = self.repository.distinct_shared_song_rows(uid, known_only=True)
        target_counter = Counter(
            str(row.get("genre_label") or "").strip()
            for row in target_rows
            if str(row.get("genre_label") or "").strip()
        )
        friend_rows = self.repository.list_friends()
        friend_map = {row["uid"]: row["nickname"] for row in friend_rows}

        def cosine(left: Counter[str], right: Counter[str]) -> float:
            keys = set(left) | set(right)
            if not keys:
                return 0.0
            dot = sum(left[key] * right[key] for key in keys)
            left_norm = sum(value * value for value in left.values()) ** 0.5
            right_norm = sum(value * value for value in right.values()) ** 0.5
            if left_norm <= 0 or right_norm <= 0:
                return 0.0
            return round(dot / (left_norm * right_norm), 4)

        related: List[Dict[str, Any]] = []
        for other_uid, other_name in friend_map.items():
            if other_uid == uid:
                continue
            other_counter = Counter(
                str(row.get("genre_label") or "").strip()
                for row in self.repository.distinct_shared_song_rows(other_uid, known_only=True)
                if str(row.get("genre_label") or "").strip()
            )
            score = cosine(target_counter, other_counter)
            if score <= 0:
                continue
            related.append(
                {
                    "uid": other_uid,
                    "name": other_name,
                    "score": score,
                    "common_genres": sorted(set(target_counter) & set(other_counter))[:5],
                }
            )
        related.sort(key=lambda item: float(item.get("score") or 0), reverse=True)
        return {"uid": uid, "pairs": related[:20]}

    def self_relation(self) -> Dict[str, Any]:
        raw_messages = []
        friend_list = self.repository.list_friends_with_archive_contacts()
        all_raw_song_rows = self.repository.query_all_shared_song_messages(known_only=False)
        song_contact_ids = {
            str(row.get("uid") or "").strip()
            for row in all_raw_song_rows
            if str(row.get("uid") or "").strip()
        }
        friend_ids = sorted({str(row.get("uid") or "").strip() for row in friend_list if str(row.get("uid") or "").strip()} | song_contact_ids)
        for uid in friend_ids:
            raw_messages.extend(self.repository.query_raw_messages(uid))
        raw_messages.sort(key=lambda item: (int(item.get("msg_time_ms") or 0), str(item.get("msg_id") or "")))
        all_rows = self.repository.distinct_all_shared_song_rows(known_only=False)
        known_rows = [row for row in all_rows if str(row.get("genre_status") or "") == "known"]
        my_rows = [row for row in known_rows if str(row.get("direction") or "") == "self"]
        friend_rows = [row for row in known_rows if str(row.get("direction") or "") == "friend"]
        all_raw_known_rows = self.repository.query_all_shared_song_messages(known_only=True)
        my_raw_rows = [row for row in all_raw_known_rows if str(row.get("direction") or "") == "self"]
        friend_raw_rows = [row for row in all_raw_known_rows if str(row.get("direction") or "") == "friend"]
        friends = {str(row.get("uid") or "") for row in known_rows if str(row.get("uid") or "").strip()}
        active_friends = {
            str(row.get("uid") or "").strip()
            for row in raw_messages + known_rows
            if str(row.get("uid") or "").strip()
        }

        friend_map = {str(row.get("uid") or ""): str(row.get("nickname") or row.get("friend_name") or row.get("uid") or "") for row in friend_list}
        for uid in friend_ids:
            friend_map.setdefault(uid, uid)
        avatar_map = self._friend_avatar_map()
        friend_metric_rows = [
            {
                "uid": uid,
                "nickname": friend_map.get(uid, uid),
                "avatar_url": avatar_map.get(uid) or "",
            }
            for uid in friend_ids
        ]
        songs = []
        for row in known_rows:
            payload = {
                "song_name": row.get("song_name") or "",
                "artist_names": row.get("artist_names") or [],
                "album_name": row.get("album_name") or "",
                "publish_time": row.get("publish_time") or "",
                "genre_label": row.get("genre_label") or "",
                "friend_uid": row.get("uid") or "",
                "friend_name": friend_map.get(str(row.get("uid") or ""), str(row.get("uid") or "")),
                "direction": row.get("direction") or "",
            }
            songs.append(payload)

        trend_series = self._trend_series(raw_messages, known_rows, my_rows, friend_rows, all_raw_song_rows)
        timeline_visual = self._timeline_visual(raw_messages, trend_series, all_raw_song_rows)
        heatmap = self._hour_heatmap(raw_messages, known_rows)
        silence_and_burst = self._silence_and_burst(raw_messages, trend_series)
        artist_overview = self._artist_overview(my_rows, friend_rows, known_rows, my_raw_rows, friend_raw_rows)
        decade_distribution = self._distribution([{"bucket": _year_bucket(row.get("publish_time") or "")} for row in known_rows], "bucket")[:10]
        genre_overlap = self._genre_overlap(my_raw_rows, friend_raw_rows)
        dual_perspective = self._dual_perspective(my_rows, friend_rows)
        annual_review = self._annual_review(raw_messages, known_rows)
        evidence_tracks = self._evidence_tracks(known_rows, trend_series)
        common_world = self._common_world(genre_overlap, artist_overview, decade_distribution)
        account_profile = self._self_account_profile()
        global_top3 = self._global_top3(friend_metric_rows, avatar_map)
        global_social_structure = self._global_social_structure(
            friend_metric_rows,
            friend_map,
            avatar_map,
            raw_messages,
            known_rows,
            my_rows,
            friend_rows,
        )
        core_friend = ""
        for candidate in (
            global_top3.get("temperature_top3", []),
            global_top3.get("chat_top3", []),
            global_top3.get("song_top3", []),
        ):
            if candidate:
                core_friend = str(candidate[0].get("nickname") or "").strip()
                if core_friend:
                    break
        global_hero = {
            "my_name": str(account_profile.get("nickname") or "我").strip() or "我",
            "my_avatar_url": str(account_profile.get("avatar_url") or "").strip() or None,
            "active_friend_count": len(active_friends),
            "message_count": len(raw_messages),
            "song_count": len(known_rows),
            "peak_period": silence_and_burst.get("peak_period") or "",
            "social_tag": dual_perspective.get("label") or "音乐社交体",
            "core_friend": core_friend or "待形成",
        }

        return {
            "friend_count": len(friends),
            "message_count_total": len(raw_messages),
            "active_friend_count": len(active_friends),
            "known_song_count": len(known_rows),
            "my_song_count": len(my_rows),
            "friends_song_count": len(friend_rows),
            "my_genre_distribution_global": self._distribution(my_rows, "genre_label")[:10],
            "friends_genre_distribution_global": self._distribution(friend_rows, "genre_label")[:10],
            "overall_top_genres_global": self._distribution(known_rows, "genre_label")[:10],
            "genre_overlap_summary_global": genre_overlap,
            "top_artists_global": self._top_artists(known_rows),
            "decade_distribution_global": decade_distribution,
            "top_languages_global": [],
            "top_moods_global": [],
            "trend_series_global": trend_series,
            "trend_conclusion": "整体音乐社交已形成稳定的交换节奏。" if known_rows else "暂无趋势结论。",
            "activity_conclusion": heatmap["conclusion"],
            "cover_line": f"当前覆盖 {len(friends)} 位好友，累计形成 {len(known_rows)} 首去重后的已知风格歌曲。",
            "timeline_visual": timeline_visual,
            "silence_and_burst": silence_and_burst,
            "network_block": {},
            "artist_overview": artist_overview,
            "personality_cards": [],
            "personality_tags": [dual_perspective["label"]],
            "evidence_tracks": evidence_tracks,
            "annual_review": annual_review,
            "songs": songs,
            "activity_heatmap": heatmap,
            "common_world": common_world,
            "dual_perspective": dual_perspective,
            "relation_temperature": {"score": min(100, len(known_rows)), "label": "音乐社交体"},
            "global_hero": global_hero,
            "global_top3": global_top3,
            "global_social_structure": global_social_structure,
        }

    def annual_relation(self) -> Dict[str, Any]:
        all_rows = self.repository.distinct_all_shared_song_rows(known_only=True)
        yearly_counter: Dict[str, Dict[str, int]] = defaultdict(lambda: {"song_count": 0, "my_song_count": 0, "friend_song_count": 0})
        for row in all_rows:
            year = _year_bucket(row.get("publish_time") or row.get("msg_time_str") or "")
            yearly_counter[year]["song_count"] += 1
            if str(row.get("direction") or "") == "self":
                yearly_counter[year]["my_song_count"] += 1
            else:
                yearly_counter[year]["friend_song_count"] += 1
        rows = [{"year": year, **counts} for year, counts in sorted(yearly_counter.items())]
        return {"years": rows}

    def similarity(self) -> Dict[str, Any]:
        friend_ids = [row["uid"] for row in self.repository.list_friends()]
        vectors: Dict[str, Counter[str]] = {}
        for uid in friend_ids:
            rows = self.repository.distinct_shared_song_rows(uid, known_only=True)
            vectors[uid] = Counter(str(row.get("genre_label") or "").strip() for row in rows if str(row.get("genre_label") or "").strip())

        def cosine(left: Counter[str], right: Counter[str]) -> float:
            keys = set(left) | set(right)
            if not keys:
                return 0.0
            dot = sum(left[key] * right[key] for key in keys)
            left_norm = sum(value * value for value in left.values()) ** 0.5
            right_norm = sum(value * value for value in right.values()) ** 0.5
            if left_norm <= 0 or right_norm <= 0:
                return 0.0
            return round(dot / (left_norm * right_norm), 4)

        friend_map = {row["uid"]: row["nickname"] for row in self.repository.list_friends()}
        pairs: List[Dict[str, Any]] = []
        for index, left_uid in enumerate(friend_ids):
            for right_uid in friend_ids[index + 1 :]:
                score = cosine(vectors.get(left_uid, Counter()), vectors.get(right_uid, Counter()))
                if score <= 0:
                    continue
                common = sorted(set(vectors.get(left_uid, Counter())) & set(vectors.get(right_uid, Counter())))
                pairs.append(
                    {
                        "uid_a": left_uid,
                        "name_a": friend_map.get(left_uid, left_uid),
                        "uid_b": right_uid,
                        "name_b": friend_map.get(right_uid, right_uid),
                        "score": score,
                        "common_genres": common[:5],
                    }
                )
        pairs.sort(key=lambda item: float(item.get("score") or 0), reverse=True)
        return {"pairs": pairs[:50]}
