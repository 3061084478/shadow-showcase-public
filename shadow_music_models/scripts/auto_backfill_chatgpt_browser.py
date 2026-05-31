from __future__ import annotations

import argparse
import ast
import json
import os
import re
import subprocess
import sys
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable, Sequence

import requests
import pyautogui
import pygetwindow as gw
import pyperclip
from pywinauto import Desktop

SCRIPT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
if SCRIPT_ROOT not in sys.path:
    sys.path.insert(0, SCRIPT_ROOT)

from shadow_music_models.collectors import PlaylistCollector
from shadow_music_models.config_store import ConfigStore
from shadow_music_models.model_1_song_tagger import SongTagger
from shadow_music_models.model_1_song_tagger.song_tagger import GENRE_TAGS
from shadow_music_models.scripts.add_genre_training_data import main as add_genre_training_data_main
from shadow_music_models.scripts.train_genre_lightgbm import main as train_genre_lightgbm_main
from shadow_music_models.startup_bootstrap import StartupBootstrap, StartupBootstrapError


CHAT_URL = "https://chatgpt.com/c/69fabc5c-19f8-83e8-a65d-ac4bcf7d74a1"
DEFAULT_OUTPUT_DIR = str(Path(SCRIPT_ROOT) / "build" / "auto_backfill_output")
DEFAULT_REPORT_PATH = "shadow_music_models/data/outputs/auto_backfill_run_report.json"
DEFAULT_TRAINING_DATA = "shadow_music_models/data/processed/song_genre_train_merged_singlelabel.json"
DEFAULT_CHROME_DEBUG_PORT = 9222
DEFAULT_RESPONSE_TIMEOUT = 300
DEFAULT_DOWNLOAD_TIMEOUT = 120
DEFAULT_POLL_INTERVAL = 2.0
CHROME_DEBUG_READY_TIMEOUT = 30
DEFAULT_CHROME_DEBUG_PROFILE_DIR = str(
    Path(os.getenv("LOCALAPPDATA", str(Path.home() / "AppData/Local"))) / "Temp" / "shadow_music_chatgpt_debug_profile"
)
DEFAULT_BROWSER_MODE = "desktop"
DEFAULT_WINDOW_TITLE_HINT = "歌曲流派标注"

REQUIRED_FIELDS = ["song_name", "artist_names", "album_name", "genre_label"]
JSON_SONG_NAME_RE = re.compile(r'"song_name"\s*:', re.IGNORECASE)
MARKDOWN_JSON_RE = re.compile(r"```(?:json)?\s*(.*?)```", re.IGNORECASE | re.DOTALL)


@dataclass(frozen=True)
class ChatDomSnapshot:
    download_count: int
    inline_json_count: int


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="全自动采集歌单 unknown 歌曲并通过 ChatGPT 回填流派训练样本。")
    parser.add_argument("playlist_ids", nargs="+", help="一个或多个歌单 ID，或一个形如 ['a','b'] 的列表字符串。")
    parser.add_argument(
        "--training-data",
        default=DEFAULT_TRAINING_DATA,
        help="当前总训练集路径。",
    )
    parser.add_argument(
        "--output-dir",
        default=DEFAULT_OUTPUT_DIR,
        help="ChatGPT 返回 JSON 的保存目录。",
    )
    parser.add_argument(
        "--report-path",
        default=DEFAULT_REPORT_PATH,
        help="批处理报告输出路径。",
    )
    parser.add_argument(
        "--chat-url",
        default=CHAT_URL,
        help="目标 ChatGPT 会话地址。",
    )
    parser.add_argument(
        "--browser-mode",
        choices=("desktop", "dom"),
        default=DEFAULT_BROWSER_MODE,
        help="desktop 只控制当前已打开窗口；dom 需要 remote-debugging。",
    )
    parser.add_argument(
        "--window-title-hint",
        default=DEFAULT_WINDOW_TITLE_HINT,
        help="桌面模式下用于定位当前已打开窗口的标题关键词。",
    )
    parser.add_argument(
        "--chrome-path",
        default="",
        help="Chrome 可执行文件路径，留空则自动探测。",
    )
    parser.add_argument(
        "--chrome-user-data-dir",
        default="",
        help="保留参数，当前不参与 debug 浏览器启动。",
    )
    parser.add_argument(
        "--chrome-debug-profile-dir",
        default=DEFAULT_CHROME_DEBUG_PROFILE_DIR,
        help="用于 remote debugging 的独立 profile 目录。",
    )
    parser.add_argument(
        "--chrome-debug-port",
        type=int,
        default=DEFAULT_CHROME_DEBUG_PORT,
        help="Chrome remote debugging 端口。",
    )
    parser.add_argument(
        "--response-timeout",
        type=int,
        default=DEFAULT_RESPONSE_TIMEOUT,
        help="等待 ChatGPT 回复的最长秒数。",
    )
    parser.add_argument(
        "--download-timeout",
        type=int,
        default=DEFAULT_DOWNLOAD_TIMEOUT,
        help="等待下载完成的最长秒数。",
    )
    parser.add_argument(
        "--poll-interval",
        type=float,
        default=DEFAULT_POLL_INTERVAL,
        help="轮询页面与下载目录的秒数间隔。",
    )
    parser.add_argument(
        "--force-relogin",
        action="store_true",
        help="首个歌单采集前强制重新扫码登录网易云。",
    )
    return parser


def _write_json(path: Path, payload: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def _read_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def _load_jsonl(path: Path) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    with path.open("r", encoding="utf-8") as file:
        for line in file:
            text = line.strip()
            if not text:
                continue
            rows.append(json.loads(text))
    return rows


def _remove_file_if_exists(path: Path) -> None:
    if path.exists():
        path.unlink()


def _allowed_genre_tags() -> set[str]:
    return {str(tag).strip() for tag in GENRE_TAGS if str(tag).strip() and str(tag).strip() != "未知"}


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


def extract_download_url(page_text: str) -> str | None:
    pattern = re.compile(r"https?://[^\s\"'<>]+", re.IGNORECASE)
    for raw_url in pattern.findall(str(page_text or "")):
        url = raw_url.rstrip(").,;]>\"'")
        lowered = url.lower()
        if ".json" in lowered or "download" in lowered:
            return url
    return None


def validate_song_rows(
    payload: Any,
    *,
    allowed_tags: set[str] | None = None,
) -> list[dict[str, Any]] | None:
    rows = payload if isinstance(payload, list) else [payload] if isinstance(payload, dict) else None
    if rows is None:
        return None

    cleaned: list[dict[str, Any]] = []
    for row in rows:
        if not isinstance(row, dict):
            return None
        item = {
            "song_name": str(row.get("song_name") or "").strip(),
            "artist_names": [str(value).strip() for value in (row.get("artist_names") or []) if str(value).strip()],
            "album_name": str(row.get("album_name") or "").strip(),
            "genre_label": str(row.get("genre_label") or "").strip(),
        }
        if not all(item[field] for field in REQUIRED_FIELDS):
            return None
        if allowed_tags is not None and item["genre_label"] not in allowed_tags:
            return None
        cleaned.append(item)
    return cleaned


def _strip_display_json_string(value: str) -> str:
    text = str(value or "").strip()
    if text.endswith(","):
        text = text[:-1].rstrip()
    if len(text) >= 2 and text.startswith('"') and text.endswith('"'):
        return text[1:-1]
    return text


def _extract_song_rows_from_display_text(
    page_text: str,
    *,
    allowed_tags: set[str] | None = None,
) -> list[dict[str, Any]]:
    lines = [str(line).rstrip() for line in str(page_text or "").splitlines()]
    rows: list[dict[str, Any]] = []
    current: dict[str, Any] | None = None
    inside_artists = False

    def _flush_current() -> None:
        nonlocal current
        if current is None:
            return
        validated = validate_song_rows([current], allowed_tags=allowed_tags)
        if validated:
            rows.extend(validated)
        current = None

    for raw_line in lines:
        line = raw_line.strip()
        if not line:
            continue

        if line.startswith('"song_name"'):
            _flush_current()
            _, _, value = line.partition(":")
            current = {
                "song_name": _strip_display_json_string(value),
                "artist_names": [],
                "album_name": "",
                "genre_label": "",
            }
            inside_artists = False
            continue

        if current is None:
            continue

        if line.startswith('"artist_names"'):
            inside_artists = True
            continue

        if inside_artists:
            if line.startswith("]"):
                inside_artists = False
                continue
            if line.startswith('"'):
                current["artist_names"].append(_strip_display_json_string(line))
            continue

        if line.startswith('"album_name"'):
            _, _, value = line.partition(":")
            current["album_name"] = _strip_display_json_string(value)
            continue

        if line.startswith('"genre_label"'):
            _, _, value = line.partition(":")
            current["genre_label"] = _strip_display_json_string(value)
            continue

        if line.startswith("}") or line.startswith("},"):
            _flush_current()
            inside_artists = False

    _flush_current()
    if rows:
        return rows
    raise ValueError("页面展示文本里未解析出有效歌曲记录。")


def extract_last_song_json(
    page_text: str,
    *,
    allowed_tags: set[str] | None = None,
) -> list[dict[str, Any]]:
    text = str(page_text or "")
    decoder = json.JSONDecoder()
    best_rows: list[dict[str, Any]] = []

    for match in MARKDOWN_JSON_RE.finditer(text):
        fragment = match.group(1).strip()
        try:
            payload = json.loads(fragment)
        except Exception:
            continue
        rows = validate_song_rows(payload, allowed_tags=allowed_tags)
        if rows and len(rows) > len(best_rows):
            best_rows = rows

    marker_positions = [match.start() for match in JSON_SONG_NAME_RE.finditer(text)]
    if marker_positions:
        last_marker = marker_positions[-1]
        candidate_starts: list[int] = []
        probe = last_marker
        while True:
            idx = text.rfind("[", 0, probe)
            if idx < 0:
                break
            candidate_starts.append(idx)
            probe = idx
        probe = last_marker
        while True:
            idx = text.rfind("{", 0, probe)
            if idx < 0:
                break
            candidate_starts.append(idx)
            probe = idx

        for start in sorted(set(candidate_starts), reverse=True):
            fragment = text[start:]
            trimmed = fragment.lstrip()
            actual_start = start + (len(fragment) - len(trimmed))
            try:
                payload, end_index = decoder.raw_decode(trimmed)
            except Exception:
                continue
            if actual_start + end_index < last_marker:
                continue
            rows = validate_song_rows(payload, allowed_tags=allowed_tags)
            if rows and len(rows) > len(best_rows):
                best_rows = rows

    try:
        display_rows = _extract_song_rows_from_display_text(text, allowed_tags=allowed_tags)
    except Exception:
        display_rows = []

    if len(display_rows) > len(best_rows):
        return display_rows
    if best_rows:
        return best_rows
    if display_rows:
        return display_rows
    raise ValueError("页面文本里未解析出有效歌曲 JSON。")


def dedupe_unknown_song_rows(rows: Iterable[dict[str, Any]]) -> list[dict[str, Any]]:
    deduped: list[dict[str, Any]] = []
    seen: set[str] = set()
    for row in rows:
        song_name = str(row.get("song_name") or "").strip()
        artist_names = [str(value).strip() for value in (row.get("artist_names") or []) if str(value).strip()]
        album_name = str(row.get("album_name") or "").strip()
        if not song_name or not artist_names:
            continue
        key = "::".join(
            [
                "|".join(sorted(name.lower() for name in artist_names)),
                album_name.lower(),
                song_name.lower(),
            ]
        )
        if key in seen:
            continue
        seen.add(key)
        deduped.append(
            {
                "song_name": song_name,
                "artist_names": artist_names,
                "album_name": album_name,
            }
        )
    return deduped


def build_chatgpt_prompt(rows: Iterable[dict[str, Any]]) -> str:
    json_block = json.dumps(list(rows), ensure_ascii=False, indent=2)
    instruction = (
        "找到这些歌曲的流派标注。"
        "做成一个 json 文件，只输出下载链接，不要解释，不要 Markdown，不要直接输出正文 JSON。"
        "字段必须是 song_name,artist_names,album_name,genre_label（按21流派）。"
    )
    return f"{json_block}\n\n{instruction}"


def _load_song_rows_from_text(text: str, *, allowed_tags: set[str]) -> list[dict[str, Any]]:
    try:
        payload = json.loads(text)
    except json.JSONDecodeError:
        return extract_last_song_json(text, allowed_tags=allowed_tags)
    rows = validate_song_rows(payload, allowed_tags=allowed_tags)
    if rows is None:
        raise ValueError("JSON 缺少必填字段，或包含非法流派标签。")
    return rows


def load_song_rows_from_file(path: Path, *, allowed_tags: set[str]) -> list[dict[str, Any]]:
    text = path.read_text(encoding="utf-8").strip()
    if not text:
        raise ValueError("JSON 文件为空。")
    return _load_song_rows_from_text(text, allowed_tags=allowed_tags)


def _resolve_default_chrome_path() -> Path:
    candidates = [
        Path(r"C:\Program Files\Google\Chrome\Application\chrome.exe"),
        Path(r"C:\Program Files (x86)\Google\Chrome\Application\chrome.exe"),
        Path.home() / r"AppData\Local\Google\Chrome\Application\chrome.exe",
    ]
    for path in candidates:
        if path.exists():
            return path
    raise RuntimeError("未找到 Chrome，可用 --chrome-path 显式传入 chrome.exe。")


def _wait_for_http_ready(url: str, *, timeout_seconds: int) -> None:
    deadline = time.time() + timeout_seconds
    while time.time() < deadline:
        try:
            response = requests.get(url, timeout=1.5)
            if response.ok:
                return
        except Exception:
            pass
        time.sleep(0.5)
    raise RuntimeError(f"等待 Chrome remote debugging 就绪超时：{url}")


class ChatGptDomBrowser:
    def __init__(
        self,
        *,
        chat_url: str,
        download_dir: Path,
        chrome_path: Path,
        chrome_debug_profile_dir: Path,
        debug_port: int,
        poll_interval: float,
    ) -> None:
        self.chat_url = str(chat_url)
        self.download_dir = Path(download_dir)
        self.chrome_path = Path(chrome_path)
        self.chrome_debug_profile_dir = Path(chrome_debug_profile_dir)
        self.debug_port = int(debug_port)
        self.poll_interval = float(poll_interval)
        self.chrome_process: subprocess.Popen[str] | None = None
        self.driver: Any = None
        self.webdriver: Any = None
        self.By: Any = None
        self.Keys: Any = None
        self.WebDriverWait: Any = None

    def _load_selenium(self) -> None:
        if self.webdriver is not None:
            return
        try:
            from selenium import webdriver
            from selenium.webdriver.chrome.options import Options
            from selenium.webdriver.common.by import By
            from selenium.webdriver.common.keys import Keys
            from selenium.webdriver.support.ui import WebDriverWait
        except ImportError as exc:  # pragma: no cover - environment dependent
            raise RuntimeError("未安装 selenium，请先执行：python -m pip install selenium") from exc

        self.webdriver = webdriver
        self.Options = Options
        self.By = By
        self.Keys = Keys
        self.WebDriverWait = WebDriverWait

    def _launch_debug_chrome(self) -> None:
        self.chrome_debug_profile_dir.mkdir(parents=True, exist_ok=True)
        creationflags = getattr(subprocess, "CREATE_NO_WINDOW", 0)
        command = [
            str(self.chrome_path),
            f"--remote-debugging-port={self.debug_port}",
            "--remote-debugging-address=127.0.0.1",
            f"--user-data-dir={self.chrome_debug_profile_dir}",
            "--no-first-run",
            "--no-default-browser-check",
            "--disable-popup-blocking",
            self.chat_url,
        ]
        self.chrome_process = subprocess.Popen(
            command,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.PIPE,
            creationflags=creationflags,
            text=True,
            encoding="utf-8",
            errors="replace",
        )
        endpoint = f"http://127.0.0.1:{self.debug_port}/json/version"
        try:
            _wait_for_http_ready(endpoint, timeout_seconds=CHROME_DEBUG_READY_TIMEOUT)
        except Exception as exc:
            stderr_text = ""
            if self.chrome_process is not None:
                try:
                    if self.chrome_process.poll() is not None and self.chrome_process.stderr is not None:
                        stderr_text = (self.chrome_process.stderr.read() or "").strip()
                except Exception:
                    stderr_text = ""
            extra = f"；chrome_path={self.chrome_path}；profile_dir={self.chrome_debug_profile_dir}"
            if stderr_text:
                extra += f"；stderr={stderr_text[:400]}"
            raise RuntimeError(f"等待 Chrome remote debugging 就绪超时：{endpoint}{extra}") from exc

    def _attach_driver(self) -> None:
        self._load_selenium()
        options = self.Options()
        options.add_experimental_option("debuggerAddress", f"127.0.0.1:{self.debug_port}")
        self.driver = self.webdriver.Chrome(options=options)
        self.driver.execute_cdp_cmd(
            "Page.setDownloadBehavior",
            {
                "behavior": "allow",
                "downloadPath": str(self.download_dir),
            },
        )
        self.driver.set_page_load_timeout(60)

    def start(self) -> None:
        self.download_dir.mkdir(parents=True, exist_ok=True)
        if not self._try_attach_existing_debug_session():
            self._launch_debug_chrome()
            self._attach_driver()
        self.open_chat()

    def _try_attach_existing_debug_session(self) -> bool:
        endpoint = f"http://127.0.0.1:{self.debug_port}/json/version"
        try:
            _wait_for_http_ready(endpoint, timeout_seconds=2)
        except Exception:
            return False
        try:
            self._attach_driver()
        except Exception:
            return False
        return True

    def _current_is_target_chat(self) -> bool:
        if self.driver is None:
            return False
        try:
            current_url = str(self.driver.current_url or "")
        except Exception:
            return False
        return current_url.startswith(self.chat_url)

    def open_chat(self) -> None:
        if self.driver is None:
            raise RuntimeError("浏览器驱动未初始化。")
        if not self._current_is_target_chat():
            self.driver.get(self.chat_url)
        self._wait_for_composer()
        self._scroll_to_bottom()

    def _scroll_to_bottom(self) -> None:
        if self.driver is None:
            return
        try:
            self.driver.execute_script("window.scrollTo(0, document.body.scrollHeight);")
        except Exception:
            pass

    def _wait_for_composer(self) -> Any:
        if self.driver is None:
            raise RuntimeError("浏览器驱动未初始化。")
        deadline = time.time() + 60
        last_error = "未找到输入框"
        while time.time() < deadline:
            for selector in ("#prompt-textarea", "textarea", "div[contenteditable='true']"):
                elements = self.driver.find_elements(self.By.CSS_SELECTOR, selector)
                for element in elements:
                    try:
                        if element.is_displayed() and element.is_enabled():
                            return element
                    except Exception as exc:
                        last_error = str(exc)
            time.sleep(0.5)
        raise RuntimeError(f"未找到 ChatGPT 输入框：{last_error}")

    def _find_send_button(self) -> Any | None:
        if self.driver is None:
            return None
        candidates = []
        selectors = [
            "button[data-testid='send-button']",
            "button[aria-label*='Send']",
            "button[aria-label*='send']",
            "button[aria-label*='发送']",
        ]
        for selector in selectors:
            for element in self.driver.find_elements(self.By.CSS_SELECTOR, selector):
                try:
                    if element.is_displayed() and element.is_enabled():
                        candidates.append(element)
                except Exception:
                    continue
        if candidates:
            return candidates[-1]

        for element in self.driver.find_elements(self.By.CSS_SELECTOR, "button"):
            try:
                if not (element.is_displayed() and element.is_enabled()):
                    continue
                text = " ".join(
                    filter(
                        None,
                        [
                            str(element.text or "").strip(),
                            str(element.get_attribute("aria-label") or "").strip(),
                            str(element.get_attribute("title") or "").strip(),
                        ],
                    )
                ).lower()
                if any(keyword in text for keyword in ("send", "发送")):
                    return element
            except Exception:
                continue
        return None

    def _set_prompt_text(self, composer: Any, prompt_text: str) -> None:
        tag_name = str(getattr(composer, "tag_name", "") or "").lower()
        self.driver.execute_script("arguments[0].focus();", composer)
        if tag_name == "textarea":
            self.driver.execute_script(
                """
                const element = arguments[0];
                const value = arguments[1];
                const setter = Object.getOwnPropertyDescriptor(
                    window.HTMLTextAreaElement.prototype,
                    'value'
                ).set;
                setter.call(element, value);
                element.dispatchEvent(new Event('input', { bubbles: true }));
                element.dispatchEvent(new Event('change', { bubbles: true }));
                """,
                composer,
                prompt_text,
            )
            return

        composer.click()
        composer.send_keys(self.Keys.CONTROL, "a")
        composer.send_keys(self.Keys.BACKSPACE)
        composer.send_keys(prompt_text)

    def _is_generating(self) -> bool:
        if self.driver is None:
            return False
        for element in self.driver.find_elements(self.By.CSS_SELECTOR, "button"):
            try:
                if not element.is_displayed():
                    continue
                text = " ".join(
                    filter(
                        None,
                        [
                            str(element.text or "").strip(),
                            str(element.get_attribute("aria-label") or "").strip(),
                            str(element.get_attribute("title") or "").strip(),
                        ],
                    )
                ).lower()
                if any(keyword in text for keyword in ("stop", "停止")):
                    return True
            except Exception:
                continue
        return False

    def capture_snapshot(self) -> ChatDomSnapshot:
        return ChatDomSnapshot(
            download_count=len(self._find_download_elements()),
            inline_json_count=len(self._find_inline_json_blocks()),
        )

    def send_prompt(self, prompt_text: str) -> ChatDomSnapshot:
        composer = self._wait_for_composer()
        baseline = self.capture_snapshot()
        self._set_prompt_text(composer, prompt_text)
        button = self._find_send_button()
        if button is not None:
            self.driver.execute_script("arguments[0].click();", button)
        else:
            composer.send_keys(self.Keys.ENTER)
        time.sleep(1.0)
        self._scroll_to_bottom()
        return baseline

    def _find_download_elements(self) -> list[Any]:
        if self.driver is None:
            return []
        scored_candidates: list[tuple[int, int, Any]] = []
        selectors = ["a[href]", "a[download]", "button", "[role='button']"]
        for selector in selectors:
            for element in self.driver.find_elements(self.By.CSS_SELECTOR, selector):
                try:
                    if not element.is_displayed():
                        continue
                    text_value = str(element.text or "").strip()
                    aria_label = str(element.get_attribute("aria-label") or "").strip()
                    title = str(element.get_attribute("title") or "").strip()
                    href = str(element.get_attribute("href") or "").strip()
                    download_attr = str(element.get_attribute("download") or "").strip()
                    text = " ".join(
                        filter(
                            None,
                            [
                                text_value,
                                aria_label,
                                title,
                                href,
                                download_attr,
                            ],
                        )
                    ).lower()
                    if any(keyword in text for keyword in ("retry", "重试", "search the web", "搜索网页", "提交")):
                        continue
                    score = 0
                    if text_value == "下载 JSON 文件":
                        score += 1000
                    if download_attr.lower().endswith(".json"):
                        score += 900
                    if href.lower().endswith(".json") or ".json?" in href.lower():
                        score += 800
                    if "/files/" in href.lower() or "/download" in href.lower():
                        score += 700
                    if "下载" in text and "json" in text:
                        score += 500
                    if ".json" in text:
                        score += 300
                    if score <= 0:
                        continue
                    y_score = 0
                    try:
                        y_score = int(element.location.get("y", 0))
                    except Exception:
                        y_score = 0
                    scored_candidates.append((score, y_score, element))
                except Exception:
                    continue
        scored_candidates.sort(key=lambda item: (item[0], item[1]))
        return [item[2] for item in scored_candidates]

    def _download_element_signature(self, element: Any) -> str:
        text_value = str(getattr(element, "text", "") or "").strip()
        aria_label = str(element.get_attribute("aria-label") or "").strip()
        title = str(element.get_attribute("title") or "").strip()
        href = str(element.get_attribute("href") or "").strip()
        download_attr = str(element.get_attribute("download") or "").strip()
        return "||".join([text_value, aria_label, title, href, download_attr]).lower()

    def _find_inline_json_blocks(self) -> list[str]:
        if self.driver is None:
            return []
        blocks: list[str] = []
        for element in self.driver.find_elements(self.By.CSS_SELECTOR, "pre, code"):
            try:
                if not element.is_displayed():
                    continue
                text = str(element.text or "").strip()
                if text and JSON_SONG_NAME_RE.search(text):
                    blocks.append(text)
            except Exception:
                continue
        return blocks

    def _wait_for_downloaded_file(
        self,
        previous_state: dict[str, tuple[float, int]],
        *,
        timeout_seconds: int,
    ) -> Path:
        deadline = time.time() + timeout_seconds
        stable_path: Path | None = None
        stable_count = 0

        while time.time() < deadline:
            pending = list(self.download_dir.glob("*.crdownload"))
            if pending:
                stable_path = None
                stable_count = 0
                time.sleep(self.poll_interval)
                continue

            candidates: list[Path] = []
            for path in sorted(self.download_dir.glob("*.json"), key=lambda item: item.stat().st_mtime):
                stat = path.stat()
                previous = previous_state.get(path.name)
                current = (stat.st_mtime, stat.st_size)
                if previous is None or previous != current:
                    candidates.append(path)
            if candidates:
                newest = candidates[-1]
                if stable_path == newest:
                    stable_count += 1
                else:
                    stable_path = newest
                    stable_count = 1
                if stable_count >= 2:
                    return newest
            time.sleep(self.poll_interval)

        raise RuntimeError("等待下载 JSON 文件超时。")

    def _download_dir_state(self) -> dict[str, tuple[float, int]]:
        state: dict[str, tuple[float, int]] = {}
        for path in self.download_dir.glob("*.json"):
            stat = path.stat()
            state[path.name] = (stat.st_mtime, stat.st_size)
        return state

    def _try_click_new_download(self, baseline: ChatDomSnapshot, *, timeout_seconds: int) -> Path | None:
        elements = self._find_download_elements()
        if len(elements) <= baseline.download_count:
            return None
        download_state = self._download_dir_state()
        target = elements[-1]
        self.driver.execute_script("arguments[0].scrollIntoView({block: 'center'});", target)
        self.driver.execute_script("arguments[0].click();", target)
        return self._wait_for_downloaded_file(download_state, timeout_seconds=timeout_seconds)

    def _try_extract_inline_json(
        self,
        baseline: ChatDomSnapshot,
        *,
        allowed_tags: set[str],
    ) -> list[dict[str, Any]] | None:
        blocks = self._find_inline_json_blocks()
        if len(blocks) <= baseline.inline_json_count:
            return None
        combined = "\n\n".join(blocks[-8:])
        return extract_last_song_json(combined, allowed_tags=allowed_tags)

    def wait_for_response_rows(
        self,
        baseline: ChatDomSnapshot,
        *,
        allowed_tags: set[str],
        response_timeout: int,
        download_timeout: int,
        target_output_dir: Path | None = None,
    ) -> tuple[list[dict[str, Any]], Path | None]:
        del target_output_dir
        deadline = time.time() + response_timeout
        last_error = "尚未拿到 ChatGPT 结果。"
        attempted_download_keys: set[str] = set()

        while time.time() < deadline:
            self._scroll_to_bottom()
            try:
                elements = self._find_download_elements()
                if len(elements) > baseline.download_count:
                    for target in reversed(elements):
                        signature = self._download_element_signature(target)
                        if not signature or signature in attempted_download_keys:
                            continue
                        attempted_download_keys.add(signature)
                        download_state = self._download_dir_state()
                        self.driver.execute_script("arguments[0].scrollIntoView({block: 'center'});", target)
                        self.driver.execute_script("arguments[0].click();", target)
                        downloaded = self._wait_for_downloaded_file(download_state, timeout_seconds=download_timeout)
                        return load_song_rows_from_file(downloaded, allowed_tags=allowed_tags), downloaded
            except Exception as exc:
                last_error = str(exc)

            time.sleep(self.poll_interval)

        raise RuntimeError(f"等待 ChatGPT 返回 JSON 超时：{last_error}")


def find_target_window(title_hint: str) -> gw.Win32Window:
    windows = [window for window in gw.getAllWindows() if window.title]
    hint = str(title_hint or "").strip().lower()
    candidates = [window for window in windows if hint and hint in window.title.lower()]
    if candidates:
        return candidates[0]

    chatgpt_windows = [window for window in windows if "chatgpt" in window.title.lower()]
    if len(chatgpt_windows) == 1:
        return chatgpt_windows[0]
    if len(chatgpt_windows) > 1:
        return chatgpt_windows[0]

    chrome_windows = [window for window in windows if "chrome" in window.title.lower()]
    if len(chrome_windows) == 1:
        return chrome_windows[0]
    if len(chrome_windows) > 1:
        return max(chrome_windows, key=lambda window: int(window.width or 0) * int(window.height or 0))

    raise RuntimeError(f"未能定位当前浏览器窗口，请检查窗口标题关键词：{title_hint}")


def activate_window(window: gw.Win32Window) -> None:
    hwnd = getattr(window, "_hWnd", None)
    try:
        if window.isMinimized:
            window.restore()
            time.sleep(0.5)
        window.activate()
    except Exception:
        if hwnd:
            try:
                import ctypes

                ctypes.windll.user32.ShowWindow(hwnd, 9)
                ctypes.windll.user32.SetForegroundWindow(hwnd)
                ctypes.windll.user32.BringWindowToTop(hwnd)
            except Exception:
                pass
    time.sleep(0.8)


def copy_page_text(window: gw.Win32Window) -> str:
    activate_window(window)
    safe_x = window.left + window.width // 2
    safe_y = window.top + max(120, int(window.height * 0.30))
    pyautogui.click(safe_x, safe_y)
    time.sleep(0.25)
    pyautogui.hotkey("ctrl", "a")
    time.sleep(0.2)
    pyautogui.hotkey("ctrl", "c")
    time.sleep(0.8)
    return pyperclip.paste()


def navigate_to_chat(window: gw.Win32Window, chat_url: str) -> None:
    activate_window(window)
    pyperclip.copy(chat_url)
    pyautogui.hotkey("ctrl", "l")
    time.sleep(0.2)
    pyautogui.hotkey("ctrl", "a")
    time.sleep(0.2)
    pyautogui.hotkey("ctrl", "v")
    time.sleep(0.2)
    pyautogui.press("enter")
    time.sleep(8.0)


def send_prompt_desktop(window: gw.Win32Window, prompt_text: str) -> None:
    activate_window(window)
    input_x = window.left + window.width // 2
    input_y = window.top + window.height - 70
    pyperclip.copy(prompt_text)
    pyautogui.click(input_x, input_y)
    time.sleep(0.3)
    pyautogui.hotkey("ctrl", "a")
    time.sleep(0.2)
    pyautogui.press("backspace")
    time.sleep(0.2)
    pyautogui.hotkey("ctrl", "v")
    time.sleep(0.4)
    pyautogui.press("enter")
    time.sleep(1.0)


class DesktopChatGptBrowser:
    def __init__(self, *, chat_url: str, window_title_hint: str, poll_interval: float) -> None:
        self.chat_url = str(chat_url)
        self.window_title_hint = str(window_title_hint)
        self.poll_interval = float(poll_interval)
        self.window: gw.Win32Window | None = None
        self.uia_window: Any = None

    def start(self) -> None:
        self.window = find_target_window(self.window_title_hint)
        self.uia_window = Desktop(backend="uia").window(title_re=re.escape(str(self.window.title or "")))

    def _iter_descendants_safe(self) -> list[Any]:
        if self.uia_window is None:
            self.start()
        if self.uia_window is None:
            return []

        attempts = [
            ("depth", lambda: list(self.uia_window.descendants(depth=25))),
            ("refresh_depth", self._refresh_and_list_descendants_with_depth),
            ("plain", lambda: list(self.uia_window.descendants())),
            ("refresh_plain", self._refresh_and_list_descendants_plain),
        ]
        last_error: Exception | None = None
        for _, loader in attempts:
            try:
                return loader()
            except Exception as exc:
                last_error = exc
                continue
        if last_error is not None:
            raise RuntimeError(f"ChatGPT桌面控件扫描失败：{last_error}")
        return []

    def _refresh_and_list_descendants_with_depth(self) -> list[Any]:
        self.start()
        if self.uia_window is None:
            return []
        return list(self.uia_window.descendants(depth=25))

    def _refresh_and_list_descendants_plain(self) -> list[Any]:
        self.start()
        if self.uia_window is None:
            return []
        return list(self.uia_window.descendants())

    def open_chat(self) -> None:
        if self.window is None:
            self.start()
        if self.window is None:
            raise RuntimeError("未找到当前浏览器窗口。")
        activate_window(self.window)

    def send_prompt(self, prompt_text: str) -> None:
        if self.window is None:
            self.start()
        if self.window is None:
            raise RuntimeError("未找到当前浏览器窗口。")
        if self.uia_window is None:
            self.start()
        edit = self._find_prompt_edit()
        if edit is not None:
            try:
                edit.set_focus()
                try:
                    edit.set_edit_text(prompt_text)
                except Exception:
                    pyperclip.copy(prompt_text)
                    edit.click_input()
                    time.sleep(0.2)
                    pyautogui.hotkey("ctrl", "a")
                    time.sleep(0.1)
                    pyautogui.press("backspace")
                    time.sleep(0.1)
                    pyautogui.hotkey("ctrl", "v")
                time.sleep(0.3)
                pyautogui.press("enter")
                time.sleep(1.0)
                return
            except Exception:
                pass
        send_prompt_desktop(self.window, prompt_text)

    def _find_prompt_edit(self) -> Any | None:
        if self.uia_window is None:
            self.start()
        if self.uia_window is None:
            return None

        candidates: list[Any] = []
        for child in self._iter_descendants_safe():
            info = child.element_info
            name = str(info.name or "").strip()
            if info.control_type != "Edit" or not name:
                continue
            lowered = name.lower()
            if "chatgpt" in lowered or "聊天" in lowered:
                candidates.append(child)
        if not candidates:
            return None
        return max(candidates, key=lambda item: int(item.element_info.rectangle.top or 0))

    def _scroll_page_to_bottom(self) -> None:
        if self.window is None:
            self.start()
        if self.window is None:
            return
        activate_window(self.window)
        content_x = self.window.left + self.window.width // 2
        content_y = self.window.top + int(self.window.height * 0.45)
        pyautogui.click(content_x, content_y)
        time.sleep(0.2)
        for _ in range(2):
            pyautogui.hotkey("ctrl", "end")
            time.sleep(0.2)
        pyautogui.press("end")
        time.sleep(0.2)
        self._move_mouse_away()

    def _move_mouse_away(self) -> None:
        if self.window is None:
            return
        try:
            pyautogui.moveTo(
                max(int(self.window.left + 16), 1),
                max(int(self.window.top + 16), 1),
                duration=0.05,
            )
        except Exception:
            pass

    def _click_download_text_point(self) -> bool:
        if self.window is None:
            self.start()
        if self.window is None:
            return False
        try:
            self._move_mouse_away()
            click_x = int(self.window.left + self.window.width * 0.34)
            click_y = int(self.window.top + self.window.height * 0.51)
            pyautogui.click(click_x, click_y)
            return True
        except Exception:
            return False

    def _download_button_signature(self, button: Any) -> str:
        info = button.element_info
        rect = info.rectangle
        return "||".join(
            [
                str(info.control_type or "").strip(),
                str(info.name or "").strip(),
                str(int(rect.left or 0)),
                str(int(rect.top or 0)),
                str(int(rect.width or 0)),
                str(int(rect.height or 0)),
            ]
        ).lower()

    def _click_download_button(self, button: Any) -> bool:
        if self.window is None:
            self.start()
        if self.window is None:
            return False
        try:
            try:
                button.click_input()
                self._move_mouse_away()
                return True
            except Exception:
                pass
            info = button.element_info
            rect = info.rectangle
            click_x = int(rect.left + max(int(rect.width or 0), 1) // 2)
            click_y = int(rect.top + max(int(rect.height or 0), 1) // 2)
            activate_window(self.window)
            pyautogui.click(click_x, click_y)
            self._move_mouse_away()
            return True
        except Exception:
            return False

    def _collect_accessible_text(self) -> str:
        if self.uia_window is None:
            self.start()
        if self.uia_window is None:
            raise RuntimeError("未找到当前浏览器窗口。")

        texts: list[str] = []
        for child in self._iter_descendants_safe():
            info = child.element_info
            name = str(info.name or "").strip()
            if not name:
                continue
            if info.control_type in {"Text", "Button", "Hyperlink", "Document", "ListItem"}:
                texts.append(name)
        return "\n".join(texts)

    def _find_latest_download_button(self) -> Any | None:
        if self.uia_window is None:
            self.start()
        if self.uia_window is None:
            return None

        candidates: list[tuple[int, int, int, Any]] = []
        top_bound = int(self.window.top if self.window is not None else 0)
        bottom_bound = int((self.window.top + self.window.height) if self.window is not None else 100000)
        for child in self._iter_descendants_safe():
            info = child.element_info
            name = str(info.name or "").strip()
            if not name:
                continue
            lowered = name.lower()
            rect = info.rectangle
            if rect.bottom < top_bound or rect.top > bottom_bound or rect.width <= 0 or rect.height <= 0:
                continue
            if "重试" in lowered:
                continue
            is_exact_label = name == "下载 JSON 文件"
            is_json_filename = bool(re.fullmatch(r"下载\s+.+\.json", name, re.IGNORECASE))
            is_download_label = "下载" in lowered and "json" in lowered
            if not (is_exact_label or is_json_filename or is_download_label):
                continue
            score = 0
            if is_exact_label:
                score += 1000
            if is_json_filename:
                score += 800
            if is_download_label:
                score += 500
            if info.control_type == "Hyperlink":
                score += 200
            if info.control_type in {"Button", "Link", "Text"}:
                score += 80
            if rect.width >= 72:
                score += 60
            score += min(int(rect.width or 0), 300)
            score += min(int(rect.top or 0), 300)
            candidates.append((score, int(rect.top or 0), int(rect.left or 0), child))
        if not candidates:
            return None
        return max(candidates, key=lambda item: (item[0], item[1], item[2]))[3]

    def _response_appears_complete(self, page_text: str) -> bool:
        text = str(page_text or "").strip().lower()
        if not text:
            return False
        if "下载 json 文件" in text:
            return True
        if "thought for" in text:
            return True
        completion_markers = ("复制", "点赞", "点踩", "重新生成", "重试", "分享")
        return sum(1 for marker in completion_markers if marker in text) >= 2

    def _extract_download_filename(self, button_name: str) -> str | None:
        match = re.search(r"下载\s+(.+\.json)$", str(button_name or "").strip(), re.IGNORECASE)
        if match:
            return match.group(1).strip()
        return None

    def _candidate_download_dirs(self, target_output_dir: Path) -> list[Path]:
        candidates = [
            Path.home() / "Downloads",
            Path.home() / "Desktop",
            Path.home() / "Downloads" / "ChatGPT",
            Path(target_output_dir),
        ]
        deduped: list[Path] = []
        seen: set[str] = set()
        for path in candidates:
            normalized = str(path.resolve()) if path.exists() else str(path)
            if normalized in seen:
                continue
            seen.add(normalized)
            deduped.append(path)
        return deduped

    def _snapshot_download_files(self, target_output_dir: Path) -> set[str]:
        baseline: set[str] = set()
        for base_dir in self._candidate_download_dirs(target_output_dir):
            if not base_dir.exists():
                continue
            for path in base_dir.glob("*.json"):
                baseline.add(str(path.resolve()))
        return baseline

    def _wait_for_downloaded_file(
        self,
        *,
        filename: str | None,
        target_output_dir: Path,
        baseline_files: set[str],
        timeout_seconds: int,
    ) -> Path:
        deadline = time.time() + timeout_seconds
        candidate_dirs = self._candidate_download_dirs(target_output_dir)
        last_seen: Path | None = None
        stable_count = 0

        while time.time() < deadline:
            for base_dir in candidate_dirs:
                if not base_dir.exists():
                    continue
                if filename:
                    direct = base_dir / filename
                    if direct.exists() and not direct.name.endswith(".crdownload") and str(direct.resolve()) not in baseline_files:
                        if last_seen and str(last_seen) == str(direct):
                            stable_count += 1
                        else:
                            last_seen = direct
                            stable_count = 1
                        if stable_count >= 2:
                            return direct
                for path in sorted(base_dir.glob("*.json"), key=lambda item: item.stat().st_mtime):
                    if path.name.endswith(".crdownload"):
                        continue
                    if str(path.resolve()) in baseline_files:
                        continue
                    if last_seen and str(last_seen) == str(path):
                        stable_count += 1
                    else:
                        last_seen = path
                        stable_count = 1
                    if stable_count >= 2:
                        return path
            time.sleep(self.poll_interval)

        raise RuntimeError("等待下载 JSON 文件超时。")

    def wait_for_response_rows(
        self,
        baseline: Any,
        *,
        allowed_tags: set[str],
        response_timeout: int,
        download_timeout: int,
        target_output_dir: Path,
    ) -> tuple[list[dict[str, Any]], Path | None]:
        del baseline
        if self.window is None:
            self.start()
        if self.window is None:
            raise RuntimeError("未找到当前浏览器窗口。")

        deadline = time.time() + response_timeout
        last_error = "尚未拿到返回内容。"
        attempted_download_keys: set[str] = set()
        self._scroll_page_to_bottom()

        while time.time() < deadline:
            self._scroll_page_to_bottom()
            try:
                button = self._find_latest_download_button()
                if button is not None:
                    signature = self._download_button_signature(button)
                    if signature not in attempted_download_keys:
                        attempted_download_keys.add(signature)
                        baseline_files = self._snapshot_download_files(target_output_dir)
                        filename = self._extract_download_filename(str(button.element_info.name or "").strip())
                        if not self._click_download_button(button):
                            raise RuntimeError("点击下载 JSON 文件失败。")
                        downloaded = self._wait_for_downloaded_file(
                            filename=filename,
                            target_output_dir=target_output_dir,
                            baseline_files=baseline_files,
                            timeout_seconds=download_timeout,
                        )
                        return load_song_rows_from_file(downloaded, allowed_tags=allowed_tags), downloaded
                page_text = self._collect_accessible_text()
                if self._response_appears_complete(page_text):
                    last_error = "检测到回复已完成，但没有定位到可点击的下载 JSON 控件。"
            except Exception as exc:
                last_error = str(exc)

            time.sleep(self.poll_interval)

        raise RuntimeError(f"等待 ChatGPT 返回 JSON 超时：{last_error}")


def _build_unknown_song_row(song: dict[str, Any]) -> dict[str, Any]:
    return {
        "song_name": str(song.get("song_name") or "").strip(),
        "artist_names": [str(item).strip() for item in (song.get("artist_names") or []) if str(item).strip()],
        "album_name": str(song.get("album_name") or "").strip(),
    }


def _build_tagged_song_row(song: dict[str, Any], prediction: dict[str, Any]) -> dict[str, Any]:
    return {
        "song_name": str(song.get("song_name") or "").strip(),
        "artist_names": [str(item).strip() for item in (song.get("artist_names") or []) if str(item).strip()],
        "album_name": str(song.get("album_name") or "").strip(),
        "publish_time": str(song.get("album_publish_time") or "").strip(),
        "genre_tags": prediction.get("genre_tags") or [{"tag": "未知", "confidence": 0.4}],
    }


def collect_and_tag_playlist(
    playlist_id: str,
    *,
    collector: PlaylistCollector,
    config_store: ConfigStore,
    tagger: SongTagger,
) -> dict[str, Any]:
    collection = collector.collect_playlist(playlist_id)
    songs = _load_jsonl(config_store.processed_data_dir / f"playlist_{playlist_id}_songs.jsonl")

    tagged_songs: list[dict[str, Any]] = []
    unknown_songs: list[dict[str, Any]] = []
    for song in songs:
        prediction = tagger.predict(song)
        tagged = _build_tagged_song_row(song, prediction)
        tagged_songs.append(tagged)
        if str((prediction.get("genre_tags") or [{}])[0].get("tag") or "") == "未知":
            unknown_songs.append(_build_unknown_song_row(tagged))

    tagged_path = config_store.output_data_dir / f"playlist_{playlist_id}_tagged.json"
    unknown_path = config_store.output_data_dir / f"playlist_{playlist_id}_unknown_songs.json"
    _write_json(
        tagged_path,
        {
            "playlist_name": str(collection.get("playlist_name") or "").strip(),
            "songs": tagged_songs,
        },
    )
    if unknown_songs:
        _write_json(unknown_path, unknown_songs)
    else:
        _remove_file_if_exists(unknown_path)

    return {
        "playlist_name": str(collection.get("playlist_name") or "").strip(),
        "tagged_path": tagged_path,
        "unknown_path": unknown_path,
        "unknown_count": len(unknown_songs),
    }


def _merge_report_path_for_training_data(training_data_path: Path) -> str:
    return str(training_data_path.with_name(f"{training_data_path.stem}_report.json"))


def merge_and_rebuild_mapping(
    *,
    backfill_path: Path,
    training_data_path: Path,
) -> None:
    merge_exit_code = add_genre_training_data_main(
        [
            str(backfill_path),
            "--merged",
            str(training_data_path),
            "--output",
            str(training_data_path),
            "--report",
            _merge_report_path_for_training_data(training_data_path),
        ]
    )
    if merge_exit_code != 0:
        raise RuntimeError(f"补充训练集并入失败：{backfill_path}")

    train_exit_code = train_genre_lightgbm_main([str(training_data_path)])
    if train_exit_code != 0:
        raise RuntimeError(f"重建映射表失败：{training_data_path}")


def save_backfill_rows(
    *,
    output_dir: Path,
    playlist_id: str,
    rows: Sequence[dict[str, Any]],
    downloaded_path: Path | None,
) -> Path:
    output_dir.mkdir(parents=True, exist_ok=True)
    target_path = output_dir / f"playlist_{playlist_id}_chatgpt_genre_backfill.json"
    if downloaded_path is None:
        _write_json(target_path, list(rows))
        return target_path

    _remove_file_if_exists(target_path)
    downloaded_path.replace(target_path)
    return target_path


def process_playlist(
    playlist_id: str,
    *,
    collector: PlaylistCollector,
    config_store: ConfigStore,
    tagger: SongTagger,
    browser: ChatGptDomBrowser,
    output_dir: Path,
    allowed_tags: set[str],
    training_data_path: Path,
    response_timeout: int,
    download_timeout: int,
) -> dict[str, Any]:
    tag_result = collect_and_tag_playlist(
        playlist_id,
        collector=collector,
        config_store=config_store,
        tagger=tagger,
    )
    unknown_count = int(tag_result["unknown_count"])
    if unknown_count <= 0:
        return {
            "playlist_id": str(playlist_id),
            "playlist_name": str(tag_result.get("playlist_name") or "").strip(),
            "status": "no_unknown",
            "unknown_count": 0,
            "added_row_count": 0,
            "error": "",
        }

    unknown_rows = dedupe_unknown_song_rows(_read_json(Path(tag_result["unknown_path"])))
    prompt_text = build_chatgpt_prompt(unknown_rows)
    browser.open_chat()
    baseline = browser.send_prompt(prompt_text)
    rows, downloaded_path = browser.wait_for_response_rows(
        baseline,
        allowed_tags=allowed_tags,
        response_timeout=response_timeout,
        download_timeout=download_timeout,
        target_output_dir=output_dir,
    )
    saved_path = save_backfill_rows(
        output_dir=output_dir,
        playlist_id=str(playlist_id),
        rows=rows,
        downloaded_path=downloaded_path,
    )
    merge_and_rebuild_mapping(
        backfill_path=saved_path,
        training_data_path=training_data_path,
    )
    return {
        "playlist_id": str(playlist_id),
        "playlist_name": str(tag_result.get("playlist_name") or "").strip(),
        "status": "merged",
        "unknown_count": len(unknown_rows),
        "added_row_count": len(rows),
        "error": "",
        "output_path": str(saved_path),
    }


def run_batch(
    playlist_ids: Iterable[str],
    *,
    process_playlist_fn: Any,
) -> list[dict[str, Any]]:
    results: list[dict[str, Any]] = []
    for playlist_id in [str(item).strip() for item in playlist_ids if str(item).strip()]:
        try:
            results.append(process_playlist_fn(playlist_id))
        except Exception as exc:
            results.append(
                {
                    "playlist_id": str(playlist_id),
                    "status": "error",
                    "unknown_count": 0,
                    "added_row_count": 0,
                    "error": str(exc),
                }
            )
    return results


def _print_results(results: Sequence[dict[str, Any]], report_path: Path) -> None:
    print("\n=== 自动回填结果 ===")
    for item in results:
        if item["status"] == "merged":
            print(
                f"{item['playlist_id']} | merged | unknown {item['unknown_count']} | "
                f"新增样本 {item['added_row_count']}"
            )
        elif item["status"] == "no_unknown":
            print(f"{item['playlist_id']} | no_unknown")
        else:
            print(f"{item['playlist_id']} | error | {item['error']}")
    print(f"报告已写入：{report_path}")


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    config_store = ConfigStore()
    allowed_tags = _allowed_genre_tags()
    output_dir = Path(args.output_dir)
    report_path = config_store.resolve_workspace_path(args.report_path)
    training_data_path = config_store.resolve_workspace_path(args.training_data)
    playlist_ids = _flatten_playlist_id_inputs(args.playlist_ids)
    if not training_data_path.exists():
        print(f"未找到总训练集：{training_data_path}")
        return 1
    if not playlist_ids:
        print("没有可处理的 playlist_id。")
        return 1

    bootstrap = StartupBootstrap(config_store)
    try:
        profile = bootstrap.ensure_authenticated(force_relogin=bool(args.force_relogin))
    except StartupBootstrapError as exc:
        print(f"采集前认证失败：{exc}")
        return 1

    collector = PlaylistCollector(bootstrap.api_client, config_store)
    tagger = SongTagger(config_store=config_store)
    if str(args.browser_mode).strip().lower() == "dom":
        chrome_path = Path(args.chrome_path).expanduser() if str(args.chrome_path).strip() else _resolve_default_chrome_path()
        chrome_debug_profile_dir = Path(args.chrome_debug_profile_dir).expanduser()
        browser: Any = ChatGptDomBrowser(
            chat_url=str(args.chat_url),
            download_dir=output_dir,
            chrome_path=chrome_path,
            chrome_debug_profile_dir=chrome_debug_profile_dir,
            debug_port=int(args.chrome_debug_port),
            poll_interval=float(args.poll_interval),
        )
    else:
        browser = DesktopChatGptBrowser(
            chat_url=str(args.chat_url),
            window_title_hint=str(args.window_title_hint),
            poll_interval=float(args.poll_interval),
        )
    browser.start()

    def _processor(playlist_id: str) -> dict[str, Any]:
        nonlocal tagger
        result = process_playlist(
            playlist_id,
            collector=collector,
            config_store=config_store,
            tagger=tagger,
            browser=browser,
            output_dir=output_dir,
            allowed_tags=allowed_tags,
            training_data_path=training_data_path,
            response_timeout=int(args.response_timeout),
            download_timeout=int(args.download_timeout),
        )
        if result["status"] == "merged":
            tagger = SongTagger(config_store=config_store)
        return result

    print(f"API 已就绪，当前账号：{profile.get('nickname') or '未知用户'}")
    results = run_batch(playlist_ids, process_playlist_fn=_processor)
    report_payload = {
        "playlist_count": len(playlist_ids),
        "results": results,
    }
    _write_json(report_path, report_payload)
    _print_results(results, report_path)
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
