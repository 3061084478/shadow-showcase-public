from __future__ import annotations

import re
from collections import Counter
from datetime import datetime
from typing import Iterable, List


STOPWORDS = {
    "的",
    "了",
    "和",
    "是",
    "在",
    "就",
    "也",
    "都",
    "很",
    "让",
    "把",
    "被",
    "着",
    "一个",
    "没有",
    "我们",
    "你们",
    "他们",
    "真的",
    "这个",
    "那个",
    "还是",
    "不是",
    "自己",
    "时候",
    "感觉",
}
ENGLISH_STOPWORDS = {
    "a", "an", "the", "and", "or", "but", "if", "then", "than", "so", "because", "as", "at", "by", "for",
    "from", "in", "into", "of", "on", "onto", "out", "over", "to", "up", "with", "without", "about", "after",
    "before", "between", "through", "during", "under", "again", "further", "once", "here", "there", "when",
    "where", "why", "how", "all", "any", "both", "each", "few", "more", "most", "other", "some", "such",
    "no", "nor", "not", "only", "own", "same", "too", "very", "can", "will", "just", "don", "don't", "should",
    "should've", "now", "i", "i'm", "im", "me", "my", "myself", "we", "our", "ours", "ourselves", "you",
    "your", "yours", "yourself", "yourselves", "he", "him", "his", "himself", "she", "her", "hers",
    "herself", "it", "its", "itself", "they", "them", "their", "theirs", "themselves", "this", "that",
    "these", "those", "am", "is", "are", "was", "were", "be", "been", "being", "have", "has", "had", "having",
    "do", "does", "did", "doing", "would", "could", "should", "ought", "ain", "aren", "couldn", "didn", "doesn",
    "hadn", "hasn", "haven", "isn", "ma", "mightn", "mustn", "needn", "shan", "shouldn", "wasn", "weren",
    "won", "wouldn", "oh", "ooh", "ah", "uh", "yeah", "yeaah", "hey", "na", "la", "woah", "whoa",
}
LYRIC_FILLER_WORDS = {
    "baby", "babe", "shawty", "shawt", "girl", "boy", "ohh", "oohh", "nah", "mmm", "hmm", "ya", "yo",
    "gon", "gonna", "wanna", "gotta", "cuz", "cause", "coz", "yuh", "ayy", "aye",
}

LYRIC_TIMESTAMP_RE = re.compile(r"\[(?:\d{1,2}:)?\d{1,2}(?:\.\d{1,3})?\]")
LYRIC_META_RE = re.compile(r"\[(?:ti|ar|al|by|offset):[^\]]*\]", re.IGNORECASE)
ENGLISH_TOKEN_RE = re.compile(r"[A-Za-z][A-Za-z0-9'_-]*")
CHINESE_SEGMENT_RE = re.compile(r"[\u4e00-\u9fff]{2,8}")


def normalize_whitespace(text: str) -> str:
    return re.sub(r"\s+", " ", str(text or "")).strip()


def clean_comment_text(text: str) -> str:
    value = normalize_whitespace(text)
    value = re.sub(r"\[[^\]]+\]", "", value)
    return normalize_whitespace(value)


def clean_comments(comments: Iterable[str]) -> List[str]:
    cleaned = []
    seen = set()
    for comment in comments:
        text = clean_comment_text(comment)
        if not text or text in seen:
            continue
        cleaned.append(text)
        seen.add(text)
    return cleaned


def clean_lyric_text(text: str) -> str:
    value = str(text or "")
    value = LYRIC_META_RE.sub(" ", value)
    value = LYRIC_TIMESTAMP_RE.sub(" ", value)
    value = re.sub(r"\[[^\]]+\]", " ", value)
    lines = [normalize_whitespace(line) for line in value.splitlines()]
    return normalize_whitespace(" ".join(line for line in lines if line))


def _clean_lyric_lines(text: str) -> List[str]:
    value = str(text or "")
    value = LYRIC_META_RE.sub(" ", value)
    value = LYRIC_TIMESTAMP_RE.sub(" ", value)
    value = re.sub(r"\[[^\]]+\]", " ", value)
    return [normalize_whitespace(line) for line in value.splitlines() if normalize_whitespace(line)]


def extract_keywords(texts: Iterable[str], top_k: int = 6) -> List[str]:
    combined = " ".join(clean_comment_text(text) for text in texts if clean_comment_text(text))
    if not combined:
        return []
    tokens = re.findall(r"[\u4e00-\u9fff]{2,}|[A-Za-z][A-Za-z0-9&'_-]{2,}", combined)
    counter: Counter[str] = Counter()
    for token in tokens:
        normalized = token.lower()
        if normalized in STOPWORDS:
            continue
        counter[token] += 1
    return [word for word, _count in counter.most_common(top_k)]


def extract_lyric_keywords(text: str, top_k: int = 8) -> List[str]:
    lines = _clean_lyric_lines(text)
    if not lines:
        return []

    phrase_counter: Counter[str] = Counter()
    token_counter: Counter[str] = Counter()
    unique_line_counter: Counter[str] = Counter()

    for line in lines:
        unique_line_counter[line.lower()] += 1

        english_segments: List[List[str]] = []
        current_segment: List[str] = []
        for raw_token in ENGLISH_TOKEN_RE.findall(line):
            token = raw_token.lower().strip("'-_")
            if len(token) < 3:
                if current_segment:
                    english_segments.append(current_segment)
                    current_segment = []
                continue
            if token in ENGLISH_STOPWORDS or token in LYRIC_FILLER_WORDS:
                if current_segment:
                    english_segments.append(current_segment)
                    current_segment = []
                continue
            if token.endswith("'s"):
                token = token[:-2]
            if token in ENGLISH_STOPWORDS or token in LYRIC_FILLER_WORDS or len(token) < 3:
                if current_segment:
                    english_segments.append(current_segment)
                    current_segment = []
                continue
            current_segment.append(token)
            token_counter[token] += 1
        if current_segment:
            english_segments.append(current_segment)

        for segment in english_segments:
            for size in (3, 2):
                for index in range(len(segment) - size + 1):
                    phrase = " ".join(segment[index:index + size])
                    if phrase:
                        phrase_counter[phrase] += 1

        for segment in CHINESE_SEGMENT_RE.findall(line):
            normalized = segment.strip()
            if normalized in STOPWORDS or len(normalized) < 2:
                continue
            phrase_counter[normalized] += 1

    scored: List[tuple[str, float]] = []
    for phrase, count in phrase_counter.items():
        parts = phrase.split()
        token_bonus = sum(token_counter.get(part, 0) for part in parts)
        phrase_bonus = 0.9 if len(parts) >= 2 else 0.35
        score = count * 1.7 + token_bonus * 0.28 + phrase_bonus
        scored.append((phrase, score))

    if not scored:
        for token, count in token_counter.items():
            scored.append((token, count * 1.2))

    scored.sort(key=lambda item: (-item[1], -len(item[0]), item[0]))
    keywords: List[str] = []
    seen_tokens: set[str] = set()
    for phrase, _score in scored:
        normalized = phrase.lower()
        if normalized in seen_tokens:
            continue
        if any(normalized in existing.lower() or existing.lower() in normalized for existing in keywords):
            continue
        keywords.append(phrase)
        seen_tokens.add(normalized)
        if len(keywords) >= top_k:
            break
    return keywords


def summarize_comments(comments: Iterable[str], keywords: Iterable[str]) -> str:
    cleaned = clean_comments(comments)
    if not cleaned:
        return ""
    keyword_list = [keyword for keyword in keywords if keyword]
    if keyword_list:
        top = "、".join(keyword_list[:3])
        return f"评论主要围绕{top}展开。"
    snippet = cleaned[0][:36]
    return f"评论集中提到“{snippet}”。"


def normalize_publish_time(value: object) -> str:
    if value in (None, "", 0):
        return ""
    try:
        numeric = int(value)
    except (TypeError, ValueError):
        text = normalize_whitespace(str(value))
        if not text:
            return ""
        for pattern in ("%Y-%m-%d", "%Y/%m/%d", "%Y-%m", "%Y/%m", "%Y"):
            try:
                parsed = datetime.strptime(text, pattern)
                return parsed.strftime("%Y-%m-%d")
            except ValueError:
                continue
        return ""
    timestamp = numeric / 1000 if numeric > 10_000_000_000 else numeric
    try:
        return datetime.fromtimestamp(timestamp).strftime("%Y-%m-%d")
    except (OverflowError, OSError, ValueError):
        return ""
