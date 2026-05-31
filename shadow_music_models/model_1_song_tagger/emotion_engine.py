from __future__ import annotations

import re
import zipfile
from collections import Counter, defaultdict
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, Iterable, List
from xml.etree import ElementTree

from ..preprocessing import normalize_whitespace


XLSX_NS = {"a": "http://schemas.openxmlformats.org/spreadsheetml/2006/main"}
REL_NS = "{http://schemas.openxmlformats.org/officeDocument/2006/relationships}"
POSITIVE_HINT_TAGS = {"治愈", "快乐", "浪漫", "温柔", "明亮", "松弛", "热血"}
NEGATIVE_HINT_TAGS = {"伤感", "孤独", "emo", "压抑", "暗色"}
COMMENT_KEYWORD_RULES = {
    "治愈": ("治愈", "疗愈", "温暖", "安慰", "抚慰", "救赎"),
    "伤感": ("伤感", "难过", "遗憾", "眼泪", "失去", "心碎", "分开"),
    "怀旧": ("怀旧", "回忆", "以前", "从前", "老歌", "小时候", "过去"),
    "浪漫": ("浪漫", "心动", "恋爱", "告白", "喜欢", "拥抱", "玫瑰"),
    "孤独": ("孤独", "寂寞", "一个人", "独处", "失眠", "深夜"),
    "热血": ("热血", "燃", "战歌", "冲", "力量", "激情", "炸"),
    "安静": ("安静", "平静", "静下来", "夜晚", "睡前", "舒缓"),
    "快乐": ("快乐", "开心", "甜", "轻快", "上头", "蹦迪"),
    "青春感": ("青春", "校园", "少年", "夏天", "年少", "成长"),
    "emo": ("emo", "破防", "崩溃", "丧", "脆弱", "压垮"),
    "梦幻": ("梦幻", "空灵", "朦胧", "仙气", "漂浮", "星空"),
    "压抑": ("压抑", "窒息", "沉重", "焦虑", "喘不过气", "内耗"),
    "温柔": ("温柔", "轻柔", "细腻", "柔软", "耳边"),
    "复古": ("复古", "old school", "胶片", "港风", "磁带"),
    "暗色": ("黑夜", "阴天", "雨夜", "阴郁", "灰色", "冷色"),
    "明亮": ("阳光", "晴天", "明亮", "通透", "清澈", "夏日"),
    "松弛": ("松弛", "放松", "自在", "散步", "慵懒", "呼吸"),
}
DUT_CATEGORY_TO_TAG_WEIGHTS = {
    "PA": {"快乐": 1.0, "明亮": 0.35},
    "PE": {"治愈": 1.0, "松弛": 0.55, "安静": 0.45},
    "PD": {"明亮": 0.45, "温柔": 0.25},
    "PH": {"明亮": 0.85, "快乐": 0.65},
    "PG": {"治愈": 0.55, "温柔": 0.45},
    "PB": {"浪漫": 0.95, "温柔": 0.7},
    "PK": {"明亮": 0.45, "热血": 0.35},
    "NA": {"热血": 0.45, "压抑": 0.65, "暗色": 0.25},
    "NB": {"伤感": 1.0, "emo": 0.35},
    "NJ": {"emo": 0.95, "压抑": 0.7, "伤感": 0.45},
    "NH": {"压抑": 0.85, "伤感": 0.25},
    "PF": {"怀旧": 0.9, "孤独": 0.55, "青春感": 0.25},
    "NI": {"压抑": 0.75, "暗色": 0.45},
    "NC": {"暗色": 0.95, "压抑": 0.7},
    "NG": {"温柔": 0.35, "浪漫": 0.25, "孤独": 0.2},
    "NE": {"emo": 0.8, "压抑": 0.85},
    "ND": {"暗色": 0.85, "压抑": 0.7},
    "NN": {"暗色": 0.7, "压抑": 0.55},
    "NK": {"emo": 0.65, "压抑": 0.45},
    "NL": {"暗色": 0.55, "压抑": 0.45},
    "PC": {"梦幻": 0.8, "明亮": 0.55},
}


@dataclass(frozen=True)
class EmotionLexiconEntry:
    term: str
    category: str
    intensity: int
    polarity: int
    aux_category: str = ""
    aux_intensity: int = 0
    aux_polarity: int = 0
    normalized_term: str = ""


def _normalize_matching_text(text: str) -> str:
    return re.sub(r"[^0-9a-zA-Z\u4e00-\u9fff]+", "", str(text or "").lower())


def _parse_int(value: Any) -> int:
    try:
        return int(str(value).strip())
    except (TypeError, ValueError):
        return 0


def _column_index(cell_ref: str) -> int:
    match = re.match(r"([A-Z]+)", str(cell_ref or ""))
    if not match:
        return 0
    index = 0
    for char in match.group(1):
        index = index * 26 + (ord(char) - 64)
    return index - 1


def _read_shared_strings(archive: zipfile.ZipFile) -> List[str]:
    if "xl/sharedStrings.xml" not in archive.namelist():
        return []
    root = ElementTree.fromstring(archive.read("xl/sharedStrings.xml"))
    values: List[str] = []
    for item in root.findall("a:si", XLSX_NS):
        values.append("".join(node.text or "" for node in item.iterfind(".//a:t", XLSX_NS)))
    return values


def _read_first_sheet_rows(path: Path) -> List[List[str]]:
    with zipfile.ZipFile(path) as archive:
        shared_strings = _read_shared_strings(archive)
        workbook = ElementTree.fromstring(archive.read("xl/workbook.xml"))
        sheets = workbook.find("a:sheets", XLSX_NS)
        if sheets is None or not list(sheets):
            return []
        first_sheet = list(sheets)[0]
        relation_id = first_sheet.attrib.get(f"{REL_NS}id", "")
        relations = ElementTree.fromstring(archive.read("xl/_rels/workbook.xml.rels"))
        target = ""
        for relation in relations:
            if relation.attrib.get("Id") == relation_id:
                target = relation.attrib.get("Target", "")
                break
        if not target:
            return []
        worksheet = ElementTree.fromstring(archive.read(f"xl/{target}"))
        rows: List[List[str]] = []
        for row in worksheet.findall("a:sheetData/a:row", XLSX_NS):
            values: Dict[int, str] = {}
            max_index = -1
            for cell in row.findall("a:c", XLSX_NS):
                cell_ref = cell.attrib.get("r", "")
                index = _column_index(cell_ref)
                max_index = max(max_index, index)
                value_node = cell.find("a:v", XLSX_NS)
                if value_node is None:
                    values[index] = ""
                    continue
                if cell.attrib.get("t") == "s":
                    shared_index = _parse_int(value_node.text)
                    values[index] = shared_strings[shared_index] if shared_index < len(shared_strings) else ""
                else:
                    values[index] = value_node.text or ""
            if max_index < 0:
                continue
            rows.append([values.get(index, "") for index in range(max_index + 1)])
        return rows


def load_emotion_lexicon_entries(path: Path) -> List[EmotionLexiconEntry]:
    if not path.exists():
        return []
    rows = _read_first_sheet_rows(path)
    entries: List[EmotionLexiconEntry] = []
    for row in rows[1:]:
        if len(row) < 7:
            continue
        term = normalize_whitespace(row[0])
        normalized_term = _normalize_matching_text(term)
        category = normalize_whitespace(row[4]).upper()
        if len(normalized_term) < 2 or not category:
            continue
        entries.append(
            EmotionLexiconEntry(
                term=term,
                category=category,
                intensity=_parse_int(row[5]) or 1,
                polarity=_parse_int(row[6]),
                aux_category=normalize_whitespace(row[7]).upper() if len(row) > 7 else "",
                aux_intensity=_parse_int(row[8]) if len(row) > 8 else 0,
                aux_polarity=_parse_int(row[9]) if len(row) > 9 else 0,
                normalized_term=normalized_term,
            )
        )
    return entries


class EmotionLexiconEngine:
    def __init__(
        self,
        allowed_tags: Iterable[str],
        lexicon_path: Path | None = None,
        lexicon_entries: Iterable[EmotionLexiconEntry] | None = None,
    ) -> None:
        self.allowed_tags = {str(tag).strip() for tag in allowed_tags if str(tag).strip()}
        if lexicon_entries is not None:
            self.entries = list(lexicon_entries)
        elif lexicon_path is not None:
            self.entries = load_emotion_lexicon_entries(Path(lexicon_path))
        else:
            self.entries = []
        self.entries_by_first_char: Dict[str, List[EmotionLexiconEntry]] = defaultdict(list)
        for entry in self.entries:
            if entry.normalized_term:
                self.entries_by_first_char[entry.normalized_term[0]].append(entry)
        self.backend_name = "emotion_lexicon_comment_mapping_v1" if self.entries else "emotion_comment_mapping_only_v1"

    @staticmethod
    def _confidence_rows(scores: Counter[str], top_k: int = 3) -> List[Dict[str, Any]]:
        if not scores:
            return [{"tag": "未知", "confidence": 0.42}]
        total = sum(scores.values()) or 1.0
        rows: List[Dict[str, Any]] = []
        for tag, score in scores.most_common(top_k):
            share = score / total
            confidence = min(0.48 + share * 0.42 + min(score, 10.0) * 0.02, 0.95)
            rows.append({"tag": tag, "confidence": round(confidence, 2)})
        return rows or [{"tag": "未知", "confidence": 0.42}]

    def _apply_category_score(
        self,
        category: str,
        intensity: int,
        polarity: int,
        factor: float,
        scores: Counter[str],
    ) -> None:
        for tag, weight in DUT_CATEGORY_TO_TAG_WEIGHTS.get(category, {}).items():
            if tag not in self.allowed_tags:
                continue
            contribution = max(intensity, 1) * weight * factor
            if polarity == 1 and tag in POSITIVE_HINT_TAGS:
                contribution *= 1.08
            elif polarity == 2 and tag in NEGATIVE_HINT_TAGS:
                contribution *= 1.08
            elif polarity == 0:
                contribution *= 0.92
            scores[tag] += contribution

    def _score_lexicon_text(
        self,
        text: str,
        scores: Counter[str],
        matched_terms: Counter[str],
    ) -> None:
        compact_text = _normalize_matching_text(text)
        if len(compact_text) < 2 or not self.entries_by_first_char:
            return
        first_chars = {char for char in compact_text if char in self.entries_by_first_char}
        for first_char in first_chars:
            for entry in self.entries_by_first_char[first_char]:
                if entry.normalized_term not in compact_text:
                    continue
                matches = compact_text.count(entry.normalized_term)
                if matches <= 0:
                    continue
                multiplier = float(matches)
                self._apply_category_score(entry.category, entry.intensity, entry.polarity, multiplier, scores)
                if entry.aux_category:
                    self._apply_category_score(
                        entry.aux_category,
                        entry.aux_intensity or entry.intensity,
                        entry.aux_polarity,
                        multiplier * 0.55,
                        scores,
                    )
                matched_terms[entry.term] += (entry.intensity or 1) * matches

    def _score_comment_keywords(
        self,
        text: str,
        scores: Counter[str],
        matched_keywords: Counter[str],
    ) -> None:
        lowered = normalize_whitespace(text).lower()
        if not lowered:
            return
        for tag, keywords in COMMENT_KEYWORD_RULES.items():
            if tag not in self.allowed_tags:
                continue
            hits = [keyword for keyword in keywords if keyword.lower() in lowered]
            if not hits:
                continue
            scores[tag] += 1.1 + len(hits) * 0.6
            for keyword in hits:
                matched_keywords[keyword] += 1

    def predict(self, song_data: Dict[str, Any]) -> Dict[str, Any]:
        lexicon_source = " ".join(
            [
                str(song_data.get("song_name") or ""),
                " ".join(str(item).strip() for item in (song_data.get("lyric_keywords") or []) if str(item).strip()),
            ]
        )
        comment_source = " ".join(
            [
                " ".join(str(item).strip() for item in (song_data.get("comment_keywords") or []) if str(item).strip()),
                str(song_data.get("hot_comments_summary") or ""),
                " ".join(str(item).strip() for item in (song_data.get("hot_comments") or []) if str(item).strip()),
            ]
        )

        scores: Counter[str] = Counter()
        matched_terms: Counter[str] = Counter()
        matched_keywords: Counter[str] = Counter()
        self._score_lexicon_text(lexicon_source, scores, matched_terms)
        self._score_comment_keywords(comment_source, scores, matched_keywords)

        filtered_scores = Counter(
            {
                tag: score
                for tag, score in scores.items()
                if tag in self.allowed_tags and tag != "未知" and score > 0
            }
        )
        return {
            "emotion_style_tags": self._confidence_rows(filtered_scores),
            "emotion_backend": self.backend_name,
            "emotion_evidence": {
                "matched_lexicon_terms": [term for term, _ in matched_terms.most_common(6)],
                "matched_comment_keywords": [term for term, _ in matched_keywords.most_common(6)],
            },
        }
