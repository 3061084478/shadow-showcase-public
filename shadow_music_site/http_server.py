from __future__ import annotations

import json
import threading
from dataclasses import dataclass
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any, Dict
from urllib.parse import parse_qs, urlparse

from .admin_unknown import AdminUnknownService
from .bootstrap import StartupBootstrap, StartupBootstrapError
from .chat_query import ChatQueryService
from .config_store import ConfigStore
from .friend_directory import FriendDirectoryService
from .genre_retagger import GenreRetaggerService
from .initial_sync import InitialSyncService
from .mapping_sync import MappingSyncService
from .message_archive import MessageArchiveService
from .music_relation import MusicRelationService
from .prompt_export import PromptExportService
from .shadow_playlist import ShadowPlaylistService
from .song_enrichment import SongEnrichmentService
from .song_tagger import SongTagger
from .storage import SiteRepository
from .unknown_contribution import RateLimitError, UnknownContributionService


@dataclass
class AppContext:
    config_store: ConfigStore
    repository: SiteRepository
    bootstrap: StartupBootstrap
    mapping_sync: MappingSyncService
    friend_directory: FriendDirectoryService
    message_archive: MessageArchiveService
    chat_query: ChatQueryService
    shadow_playlist: ShadowPlaylistService
    music_relation: MusicRelationService
    prompt_export: PromptExportService
    admin_unknown: AdminUnknownService
    genre_retagger: GenreRetaggerService
    initial_sync: InitialSyncService
    unknown_contribution: UnknownContributionService


def build_app_context() -> AppContext:
    config_store = ConfigStore()
    repository = SiteRepository(config_store.db_path)
    bootstrap = StartupBootstrap(config_store)
    mapping_sync = MappingSyncService(config_store)
    mapping_status = mapping_sync.sync_latest_mapping_if_enabled()
    song_tagger = SongTagger(config_store=config_store)
    enrichment = SongEnrichmentService(bootstrap.api_client, repository, song_tagger)
    unknown_contribution = UnknownContributionService(config_store, repository)
    friend_directory = FriendDirectoryService(bootstrap, repository)
    message_archive = MessageArchiveService(bootstrap.api_client, repository, enrichment, unknown_contribution)
    genre_retagger = GenreRetaggerService(repository, song_tagger, config_store)
    genre_retagger.auto_reindex_for_mapping(mapping_status)
    return AppContext(
        config_store=config_store,
        repository=repository,
        bootstrap=bootstrap,
        mapping_sync=mapping_sync,
        friend_directory=friend_directory,
        message_archive=message_archive,
        chat_query=ChatQueryService(repository),
        shadow_playlist=ShadowPlaylistService(config_store, bootstrap, repository),
        music_relation=MusicRelationService(repository, bootstrap),
        prompt_export=PromptExportService(repository),
        admin_unknown=AdminUnknownService(config_store, repository),
        genre_retagger=genre_retagger,
        initial_sync=InitialSyncService(friend_directory, message_archive, repository, genre_retagger),
        unknown_contribution=unknown_contribution,
    )


class JsonHttpServer(ThreadingHTTPServer):
    def __init__(self, server_address: tuple[str, int], context: AppContext):
        super().__init__(server_address, JsonRequestHandler)
        self.context = context


class JsonRequestHandler(BaseHTTPRequestHandler):
    server: JsonHttpServer

    def _frontend_dist_dir(self) -> Path:
        package_root = self.server.context.config_store.workspace_root
        candidates = [
            package_root / "web" / "dist",
            package_root / "shadow (2)" / "dist",
        ]
        for candidate in candidates:
            if candidate.exists():
                return candidate
        return candidates[0]

    def log_message(self, format: str, *args: Any) -> None:
        return

    def do_OPTIONS(self) -> None:
        self.send_response(HTTPStatus.NO_CONTENT)
        self._send_common_headers()
        self.end_headers()

    def do_GET(self) -> None:
        self._dispatch("GET")

    def do_POST(self) -> None:
        self._dispatch("POST")

    def _send_common_headers(self, content_type: str = "application/json; charset=utf-8") -> None:
        self.send_header("Content-Type", content_type)
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type, Authorization, X-Admin-Token")

    def _read_json_body(self) -> Dict[str, Any]:
        length = int(self.headers.get("Content-Length") or 0)
        if length <= 0:
            return {}
        body = self.rfile.read(length)
        if not body:
            return {}
        try:
            payload = json.loads(body.decode("utf-8"))
        except json.JSONDecodeError as exc:
            raise ValueError(f"璇锋眰浣撲笉鏄悎娉?JSON: {exc}") from exc
        if not isinstance(payload, dict):
            raise ValueError("璇锋眰浣撳繀椤绘槸 JSON 瀵硅薄銆?")
        return payload

    def _json_response(self, status: int, payload: Dict[str, Any]) -> None:
        body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self._send_common_headers()
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _json_list_response(self, status: int, payload: list[Any]) -> None:
        body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self._send_common_headers()
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _send_static_file(self, path: Path, content_type: str) -> None:
        body = path.read_bytes()
        self.send_response(HTTPStatus.OK)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _serve_frontend_asset(self, path: str) -> bool:
        dist_dir = self._frontend_dist_dir()
        normalized = path.lstrip("/") or "index.html"
        asset_path = (dist_dir / normalized).resolve()
        if not str(asset_path).startswith(str(dist_dir.resolve())) or not asset_path.exists() or not asset_path.is_file():
            return False
        suffix = asset_path.suffix.lower()
        if suffix == ".html":
            content_type = "text/html; charset=utf-8"
        elif suffix == ".js":
            content_type = "application/javascript; charset=utf-8"
        elif suffix == ".css":
            content_type = "text/css; charset=utf-8"
        elif suffix == ".png":
            content_type = "image/png"
        elif suffix in {".jpg", ".jpeg"}:
            content_type = "image/jpeg"
        elif suffix == ".svg":
            content_type = "image/svg+xml"
        elif suffix == ".json":
            content_type = "application/json; charset=utf-8"
        else:
            content_type = "application/octet-stream"
        self._send_static_file(asset_path, content_type)
        return True

    def _dispatch(self, method: str) -> None:
        parsed = urlparse(self.path)
        path = parsed.path.rstrip("/") or "/"
        query = {key: values[-1] for key, values in parse_qs(parsed.query).items() if values}
        try:
            if method == "GET" and (path == "/" or path.startswith("/assets/") or path in {"/shadow-home-collage.png", "/shadow-login-background.jpg", "/placeholder.txt", "/index.html"}):
                asset_target = "index.html" if path == "/" else path.lstrip("/")
                if self._serve_frontend_asset(asset_target):
                    return
            if method == "POST" and path == "/admin/recent-friends/clear":
                return self._json_response(200, {"friends": self.server.context.friend_directory.clear_recent_friends()})
            if method == "POST" and path == "/auth/api/start":
                self.server.context.bootstrap.ensure_api_ready()
                return self._json_response(200, {"ok": True})
            if method == "GET" and path == "/auth/status":
                return self._json_response(200, self._auth_status())
            if method == "POST" and path == "/auth/qr/start":
                payload = self.server.context.bootstrap.create_qr_session()
                return self._json_response(200, payload)
            if method == "GET" and path == "/auth/qr/poll":
                key = str(query.get("key") or "").strip()
                if not key:
                    raise ValueError("缂哄皯 key銆?")
                return self._json_response(200, self.server.context.bootstrap.check_qr_session(key))
            if method == "GET" and path == "/friends":
                return self._json_response(200, {"friends": self.server.context.friend_directory.list_friends()})
            if method == "GET" and path == "/friends/recent":
                return self._json_response(200, {"friends": self.server.context.friend_directory.list_recent_friends()})
            if method == "POST" and path == "/friends/sync":
                return self._json_response(200, self.server.context.friend_directory.sync_friends())
            if method == "POST" and path == "/sync/bootstrap":
                return self._json_response(200, self.server.context.initial_sync.start())
            if method == "GET" and path == "/sync/bootstrap/status":
                return self._json_response(200, self.server.context.initial_sync.status())
            if method == "POST" and path == "/sync/archive/all":
                pages = int(query.get("pages") or 1)
                limit = int(query.get("limit") or 50)
                return self._json_response(200, self.server.context.initial_sync.archive_all_from_cursors(initial_pages=pages, limit=limit))
            if method == "POST" and path == "/sync/archive/rebuild-all":
                limit = int(query.get("limit") or 50)
                return self._json_response(200, self.server.context.initial_sync.rebuild_all_full(limit=limit))
            if method == "GET" and path == "/settings/privacy":
                return self._json_response(200, self.server.context.unknown_contribution.get_privacy_settings())
            if method == "POST" and path == "/settings/privacy":
                payload = self._read_json_body()
                return self._json_response(
                    200,
                    self.server.context.unknown_contribution.update_privacy_settings(
                        bool(payload.get("allow_unknown_song_contribution", False))
                    ),
                )
            if method == "GET" and path == "/mapping/update/status":
                return self._json_response(
                    200,
                    {
                        **self.server.context.mapping_sync.load_status(),
                        "auto_reindex_state": self.server.context.genre_retagger.load_state(),
                    },
                )
            if method == "POST" and path == "/mapping/update/check":
                mapping_status = self.server.context.mapping_sync.force_sync()
                reindex_result = self.server.context.genre_retagger.auto_reindex_for_mapping(mapping_status)
                return self._json_response(
                    200,
                    {
                        **mapping_status,
                        "auto_reindex": reindex_result,
                    },
                )
            if method == "POST" and path == "/unknown-song/flush":
                return self._json_response(200, self.server.context.unknown_contribution.flush_pending_uploads())
            if method == "POST" and path == "/api/unknown-song/batch-submit":
                status, response = self.server.context.unknown_contribution.handle_batch_submit(
                    self._read_json_body(),
                    client_ip=self.client_address[0] if self.client_address else "unknown",
                )
                return self._json_response(status, response)
            if path.startswith("/api/admin/unknown-song/"):
                return self._handle_admin_unknown_song_routes(method, path, query)
            if path.startswith("/friends/"):
                return self._handle_friend_routes(method, path, query)
            if path.startswith("/shadow/"):
                return self._handle_shadow_routes(method, path)
            if path.startswith("/relation/"):
                return self._handle_relation_routes(method, path)
            if method == "GET" and path == "/health":
                return self._json_response(
                    200,
                    {
                        "service": "shadow_music_site",
                        "status": "ok",
                        "db_path": str(self.server.context.config_store.db_path),
                    },
                )
            if method == "GET" and path == "/admin/unknown":
                return self._json_response(200, {"rows": self.server.context.admin_unknown.list_unknown()})
            if method == "POST" and path == "/admin/unknown/rebuild":
                return self._json_response(200, self.server.context.admin_unknown.rebuild_unknown_file())
            if method == "POST" and path == "/admin/genre/reindex-unknown":
                return self._json_response(200, self.server.context.genre_retagger.reindex_unknown())
            if method == "POST" and path == "/admin/genre/reindex-all":
                return self._json_response(200, self.server.context.genre_retagger.reindex_all())
            if method == "GET" and not path.startswith("/api/"):
                if self._serve_frontend_asset("index.html"):
                    return
            self._json_response(404, {"error": f"鏈壘鍒拌矾鐢? {path}"})
        except RateLimitError as exc:
            self._json_response(429, {"error": str(exc)})
        except (ValueError, RuntimeError, StartupBootstrapError) as exc:
            self._json_response(400, {"error": str(exc)})
        except PermissionError as exc:
            self._json_response(403, {"error": str(exc)})
        except Exception as exc:
            self._json_response(500, {"error": str(exc)})

    def _auth_status(self) -> Dict[str, Any]:
        context = self.server.context
        context.bootstrap.reload()
        api_ready = context.bootstrap.is_api_http_responding()
        cookie_valid = context.bootstrap.is_cookie_valid() if api_ready else False
        account: Dict[str, Any] = {}
        if api_ready and cookie_valid:
            account = context.bootstrap.ensure_authenticated()
        return {
            "api_ready": api_ready,
            "cookie_valid": cookie_valid,
            "account": account,
        }

    def _handle_friend_routes(self, method: str, path: str, query: Dict[str, str]) -> None:
        context = self.server.context
        parts = path.strip("/").split("/")
        if len(parts) < 2:
            raise ValueError("濂藉弸璺敱缂哄皯 uid銆?")
        uid = parts[1]
        tail = parts[2:]

        if method == "POST" and tail == ["archive", "rebuild"]:
            return self._json_response(200, context.message_archive.rebuild_friend_archive(uid))
        if method == "POST" and tail == ["remember"]:
            return self._json_response(200, {"friends": context.friend_directory.remember_friend(uid)})
        if method == "POST" and tail == ["recent", "pin"]:
            return self._json_response(200, {"friends": context.friend_directory.pin_recent_friend(uid)})
        if method == "POST" and tail == ["recent", "unpin"]:
            return self._json_response(200, {"friends": context.friend_directory.unpin_recent_friend(uid)})
        if method == "POST" and tail == ["recent", "delete"]:
            return self._json_response(200, {"friends": context.friend_directory.delete_recent_friend(uid)})
        if method == "GET" and tail == ["archive", "summary"]:
            return self._json_response(200, context.message_archive.get_archive_summary(uid))
        if method == "POST" and tail == ["archive", "sync-recent"]:
            pages = int(query.get("pages") or 3)
            limit = int(query.get("limit") or 50)
            return self._json_response(200, context.message_archive.sync_recent_history_delta(uid, initial_pages=pages, limit=limit))
        if method == "POST" and tail == ["archive", "sync-incremental"]:
            pages = int(query.get("pages") or 3)
            limit = int(query.get("limit") or 50)
            return self._json_response(200, context.message_archive.sync_recent_history_delta(uid, initial_pages=pages, limit=limit))
        if method == "POST" and tail == ["archive", "backfill"]:
            limit = int(query.get("limit") or 50)
            return self._json_response(200, context.message_archive.sync_full_history_backfill(uid, limit=limit))
        if method == "GET" and tail == ["shared-songs"]:
            return self._json_response(200, context.chat_query.query_shared_songs(uid, dict(query)))
        if method == "POST" and tail == ["shared-songs", "query"]:
            return self._json_response(200, context.chat_query.query_shared_songs(uid, self._read_json_body()))
        if method == "GET" and tail == ["shared-songs", "active-dates"]:
            return self._json_response(200, {"dates": context.chat_query.shared_song_active_dates(uid)})
        if method == "GET" and tail == ["chat-messages"]:
            return self._json_response(200, context.chat_query.query(uid, dict(query)))
        if method == "POST" and tail == ["chat-messages", "query"]:
            return self._json_response(200, context.chat_query.query(uid, self._read_json_body()))
        if method == "GET" and tail == ["chat-messages", "active-dates"]:
            return self._json_response(200, {"dates": context.chat_query.active_dates(uid)})
        if method == "POST" and tail == ["shadow", "candidates", "query"]:
            return self._json_response(200, context.shadow_playlist.query_candidates(uid, self._read_json_body()))
        if method == "POST" and tail == ["shadow", "build"]:
            return self._json_response(200, context.shadow_playlist.build(uid, self._read_json_body()))
        if method == "GET" and tail == ["relation"]:
            return self._json_response(200, context.music_relation.friend_relation(uid))
        if method == "GET" and tail == ["relation", "annual"]:
            return self._json_response(200, context.music_relation.friend_annual_relation(uid))
        if method == "GET" and tail == ["relation", "similarity"]:
            return self._json_response(200, context.music_relation.friend_similarity(uid))
        if method == "GET" and tail == ["genre-stats"]:
            relation = context.music_relation.friend_relation(uid)
            return self._json_response(
                200,
                {
                    "my_genre_distribution": relation.get("my_top_genres", []),
                    "friend_genre_distribution": relation.get("friend_top_genres", []),
                    "overall_top_genres": relation.get("overall_top_genres", []),
                    "genre_overlap": relation.get("genre_overlap", {}),
                },
            )
        if method == "POST" and tail == ["relation", "export"]:
            return self._json_response(200, context.prompt_export.export_friend_relation(uid))
        if method == "GET" and tail == ["relation", "export", "latest"]:
            payload = context.repository.get_latest_relation_export("friend", uid)
            return self._json_response(200, payload or {})
        raise ValueError(f"鏈敮鎸佺殑濂藉弸璺敱: {path}")

    def _handle_shadow_routes(self, method: str, path: str) -> None:
        context = self.server.context
        if method == "GET" and path == "/shadow/targets":
            return self._json_response(200, context.shadow_playlist.list_targets())
        if method == "GET" and path == "/shadow/state":
            return self._json_response(200, context.shadow_playlist.get_playlist_state())
        if method == "GET" and path == "/shadow/build/latest":
            return self._json_response(200, context.shadow_playlist.get_last_build_record() or {})
        if method == "POST" and path == "/shadow/target":
            return self._json_response(200, context.shadow_playlist.set_target(self._read_json_body()))
        raise ValueError(f"鏈敮鎸佺殑褰卞瓙姝屽崟璺敱: {path}")

    def _handle_relation_routes(self, method: str, path: str) -> None:
        context = self.server.context
        if method == "GET" and path == "/relation/self":
            return self._json_response(200, context.music_relation.self_relation())
        if method == "GET" and path == "/relation/annual":
            return self._json_response(200, context.music_relation.annual_relation())
        if method == "GET" and path == "/relation/similarity":
            return self._json_response(200, context.music_relation.similarity())
        if method == "GET" and path == "/relation/self/genre-stats":
            relation = context.music_relation.self_relation()
            return self._json_response(
                200,
                {
                    "my_genre_distribution_global": relation.get("my_genre_distribution_global", []),
                    "friends_genre_distribution_global": relation.get("friends_genre_distribution_global", []),
                    "overall_top_genres_global": relation.get("overall_top_genres_global", []),
                    "genre_overlap_summary_global": relation.get("genre_overlap_summary_global", {}),
                },
            )
        if method == "POST" and path == "/relation/self/export":
            return self._json_response(200, context.prompt_export.export_self_relation())
        if method == "GET" and path == "/relation/self/export/latest":
            payload = context.repository.get_latest_relation_export("self", "global")
            return self._json_response(200, payload or {})
        raise ValueError(f"鏈敮鎸佺殑闊充箰鍏崇郴璺敱: {path}")

    def _admin_token(self) -> str:
        auth_header = str(self.headers.get("Authorization") or "").strip()
        if auth_header.lower().startswith("bearer "):
            return auth_header[7:].strip()
        return str(self.headers.get("X-Admin-Token") or "").strip()

    def _handle_admin_unknown_song_routes(self, method: str, path: str, query: Dict[str, str]) -> None:
        context = self.server.context
        token = self._admin_token()
        if method == "GET" and path == "/api/admin/unknown-song/export":
            status = str(query.get("status") or "pending")
            rows = context.unknown_contribution.export_unknown_songs(token, status=status)
            return self._json_list_response(200, rows)
        if method == "GET" and path == "/api/admin/unknown-song/stats":
            return self._json_response(200, context.unknown_contribution.get_admin_stats(token))
        if method == "GET" and path == "/api/admin/unknown-song/top":
            limit = int(query.get("limit") or 100)
            return self._json_response(200, {"rows": context.unknown_contribution.get_top_unknown_songs(token, limit=limit)})
        if method == "POST" and path == "/api/admin/unknown-song/mark-exported":
            payload = self._read_json_body()
            return self._json_response(200, context.unknown_contribution.mark_exported(token, status=str(payload.get("status") or "pending")))
        if method == "POST" and path == "/api/admin/unknown-song/ignore":
            payload = self._read_json_body()
            return self._json_response(200, context.unknown_contribution.ignore_unknown_keys(token, list(payload.get("normalized_keys") or [])))
        if method == "POST" and path == "/api/admin/unknown-song/cleanup-exported":
            return self._json_response(200, context.unknown_contribution.cleanup_exported(token))
        raise ValueError(f"鏈敮鎸佺殑 unknown 绠＄悊璺敱: {path}")


def run_http_server(host: str = "127.0.0.1", port: int = 8787) -> JsonHttpServer:
    context = build_app_context()
    server = JsonHttpServer((host, port), context)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    return server
