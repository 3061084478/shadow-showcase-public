from __future__ import annotations

import json
import os
import re
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime
from typing import Any, Dict, List

ADMIN_TOKEN = str(os.environ.get("ADMIN_TOKEN") or "").strip()
CLOUDBASE_ENV_ID = str(os.environ.get("CLOUDBASE_ENV_ID") or os.environ.get("TCB_ENV") or "").strip()
CLOUDBASE_API_KEY = str(os.environ.get("CLOUDBASE_API_KEY") or "").strip()
HTTP_TIMEOUT_SECONDS = int(os.environ.get("HTTP_TIMEOUT_SECONDS") or "30")

CLOUDBASE_LABELED_INPUT_PREFIX = str(
    os.environ.get("CLOUDBASE_LABELED_INPUT_PREFIX") or "genre-pipeline/admin/labeled-inputs"
).strip().strip("/")
CLOUDBASE_LATEST_LABELED_META_OBJECT = str(
    os.environ.get("CLOUDBASE_LATEST_LABELED_META_OBJECT") or "genre-pipeline/admin/latest_labeled_input.json"
).strip()
CLOUDBASE_MANIFEST_PREFIX = str(
    os.environ.get("CLOUDBASE_MANIFEST_PREFIX") or "genre-pipeline/manifests"
).strip().strip("/")
CLOUDBASE_DELTA_PREFIX = str(
    os.environ.get("CLOUDBASE_DELTA_PREFIX") or "genre-pipeline/deltas"
).strip().strip("/")
CLOUDBASE_STORAGE_BUCKET = str(os.environ.get("CLOUDBASE_STORAGE_BUCKET") or "").strip()

MAX_SONG_NAME_LENGTH = 200
MAX_ALBUM_NAME_LENGTH = 200
MAX_ARTIST_COUNT = 10
MAX_ARTIST_NAME_LENGTH = 100
MAX_GENRE_LABEL_LENGTH = 60
MAX_ROWS_PER_UPLOAD = 5000
MAX_DELTA_ITEMS_PER_RESPONSE = 20
CONTROL_CHAR_PATTERN = re.compile(r"[\x00-\x1F\x7F]")
MULTI_SPACE_PATTERN = re.compile(r"\s+")
EDGE_PUNCTUATION = " \t\r\n\"'`~!@#$%^&*()_+-=[]{}|\\:;,./<>?，。！？、；：（）【】《》"


def _now_text() -> str:
    return datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S UTC")


def _timestamp() -> str:
    return datetime.utcnow().strftime("%Y%m%d_%H%M%S")


def _json_response(status_code: int, payload: Any) -> Dict[str, Any]:
    return {
        "statusCode": status_code,
        "headers": {
            "Content-Type": "application/json; charset=utf-8",
            "Access-Control-Allow-Origin": "*",
            "Access-Control-Allow-Methods": "GET, POST, OPTIONS",
            "Access-Control-Allow-Headers": "Content-Type, Authorization, X-Admin-Token",
        },
        "body": json.dumps(payload, ensure_ascii=False),
    }


def _parse_body(event: Dict[str, Any]) -> Any:
    body = event.get("body")
    if body in (None, ""):
        return {}
    if isinstance(body, (dict, list)):
        return body
    try:
        return json.loads(str(body))
    except json.JSONDecodeError as exc:
        raise ValueError("请求体不是合法 JSON。") from exc


def _get_path(event: Dict[str, Any]) -> str:
    return str(event.get("path") or event.get("requestContext", {}).get("path") or "").strip()


def _get_method(event: Dict[str, Any]) -> str:
    return str(event.get("httpMethod") or event.get("requestContext", {}).get("httpMethod") or "GET").upper()


def _get_header(event: Dict[str, Any], key: str) -> str:
    headers = event.get("headers") or {}
    key_lower = key.lower()
    for header_key, header_value in headers.items():
        if str(header_key).lower() == key_lower:
            return str(header_value or "")
    return ""


def _get_query(event: Dict[str, Any]) -> Dict[str, Any]:
    return event.get("queryStringParameters") or {}


def _require_admin(event: Dict[str, Any]) -> None:
    if not ADMIN_TOKEN:
        raise PermissionError("服务端未配置 ADMIN_TOKEN。")
    auth_header = _get_header(event, "Authorization").strip()
    if auth_header.lower().startswith("bearer "):
        token = auth_header[7:].strip()
    else:
        token = _get_header(event, "X-Admin-Token").strip()
    if token != ADMIN_TOKEN:
        raise PermissionError("管理员令牌无效。")


def _require_cloudbase_config() -> None:
    if not CLOUDBASE_ENV_ID or not CLOUDBASE_API_KEY:
        raise ValueError("未配置 CLOUDBASE_ENV_ID / CLOUDBASE_API_KEY。")


def _clean_text(value: Any, max_length: int) -> str:
    text = str(value or "").replace("\ufeff", "").replace("\u3000", " ")
    text = CONTROL_CHAR_PATTERN.sub("", text)
    text = MULTI_SPACE_PATTERN.sub(" ", text).strip()
    return text[:max_length]


def _normalize_edge_text(value: str) -> str:
    return value.strip(EDGE_PUNCTUATION).strip()


def _clean_artist_names(values: Any) -> List[str]:
    if not isinstance(values, list):
        return []
    result: List[str] = []
    seen: set[str] = set()
    for item in values[:MAX_ARTIST_COUNT]:
        artist = _normalize_edge_text(_clean_text(item, MAX_ARTIST_NAME_LENGTH))
        if not artist:
            continue
        key = artist.lower()
        if key in seen:
            continue
        seen.add(key)
        result.append(artist)
    return result


def _validate_labeled_rows(rows: Any) -> List[Dict[str, Any]]:
    if not isinstance(rows, list):
        raise ValueError("rows 必须是 JSON 数组。")
    if len(rows) > MAX_ROWS_PER_UPLOAD:
        raise ValueError(f"单次最多上传 {MAX_ROWS_PER_UPLOAD} 条标注数据。")

    result: List[Dict[str, Any]] = []
    for item in rows:
        if not isinstance(item, dict):
            continue
        song_name = _normalize_edge_text(_clean_text(item.get("song_name"), MAX_SONG_NAME_LENGTH))
        album_name = _normalize_edge_text(_clean_text(item.get("album_name"), MAX_ALBUM_NAME_LENGTH))
        genre_label = _normalize_edge_text(_clean_text(item.get("genre_label"), MAX_GENRE_LABEL_LENGTH))
        artist_names = _clean_artist_names(item.get("artist_names") or [])
        if not song_name or not artist_names or not genre_label:
            continue
        result.append(
            {
                "song_name": song_name,
                "artist_names": artist_names,
                "album_name": album_name,
                "genre_label": genre_label,
            }
        )
    if not result:
        raise ValueError("没有可用的已标注数据。")
    return result


def _cloudbase_api_request(
    method: str,
    path: str,
    payload: Any | None = None,
    headers: Dict[str, str] | None = None,
    raw_body: bytes | None = None,
) -> tuple[int, bytes]:
    _require_cloudbase_config()
    url = f"https://{CLOUDBASE_ENV_ID}.api.tcloudbasegateway.com{path}"
    request_headers = {"Authorization": f"Bearer {CLOUDBASE_API_KEY}"}
    if headers:
        request_headers.update(headers)

    body = raw_body
    if payload is not None:
        body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        request_headers.setdefault("Content-Type", "application/json; charset=utf-8")

    request = urllib.request.Request(url=url, data=body, headers=request_headers, method=method.upper())
    try:
        with urllib.request.urlopen(request, timeout=HTTP_TIMEOUT_SECONDS) as response:
            return response.getcode(), response.read()
    except urllib.error.HTTPError as exc:
        message = exc.read().decode("utf-8", errors="replace")
        raise RuntimeError(f"CloudBase HTTP API 调用失败：{path} -> {exc.code} {message}") from exc
    except urllib.error.URLError as exc:
        raise RuntimeError(f"CloudBase HTTP API 网络错误：{path} -> {exc}") from exc


def _cloudbase_json_post(path: str, payload: Any) -> Any:
    status_code, body = _cloudbase_api_request("POST", path, payload=payload)
    if status_code < 200 or status_code >= 300:
        raise RuntimeError(f"CloudBase HTTP API 返回异常状态码：{status_code}")
    text = body.decode("utf-8", errors="replace")
    return json.loads(text) if text else None


def _storage_upload_bytes(object_id: str, content_bytes: bytes, content_type: str) -> Dict[str, Any]:
    rows = _cloudbase_json_post("/v1/storages/get-objects-upload-info", [{"objectId": object_id}])
    if not isinstance(rows, list) or not rows:
        raise RuntimeError("CloudBase 未返回对象上传信息。")
    row = rows[0]
    if not isinstance(row, dict):
        raise RuntimeError("CloudBase 返回的对象上传信息格式异常。")
    if row.get("code"):
        raise RuntimeError(f"获取对象上传信息失败：{row.get('code')} {row.get('message') or ''}".strip())

    upload_url = str(row.get("uploadUrl") or "").strip()
    if not upload_url:
        raise RuntimeError("CloudBase 未返回 uploadUrl。")

    upload_headers = {
        "Authorization": str(row.get("authorization") or "").strip(),
        "Content-Type": content_type,
        "Content-Length": str(len(content_bytes)),
    }
    token = str(row.get("token") or "").strip()
    meta = str(row.get("cloudObjectMeta") or "").strip()
    if token:
        upload_headers["X-Cos-Security-Token"] = token
    if meta:
        upload_headers["X-Cos-Meta-Fileid"] = meta

    request = urllib.request.Request(url=upload_url, data=content_bytes, headers=upload_headers, method="PUT")
    try:
        with urllib.request.urlopen(request, timeout=HTTP_TIMEOUT_SECONDS):
            pass
    except urllib.error.HTTPError as exc:
        message = exc.read().decode("utf-8", errors="replace")
        raise RuntimeError(f"上传对象失败：{exc.code} {message}") from exc
    except urllib.error.URLError as exc:
        raise RuntimeError(f"上传对象网络失败：{exc}") from exc
    return row


def _storage_get_download_info(object_ids: List[str]) -> List[Dict[str, Any]]:
    rows = _cloudbase_json_post(
        "/v1/storages/get-objects-download-info",
        [{"cloudObjectId": _to_cloud_object_id(object_id)} for object_id in object_ids],
    )
    if not isinstance(rows, list):
        raise RuntimeError("CloudBase 未返回对象下载信息。")
    return rows


def _to_cloud_object_id(object_id: str) -> str:
    value = str(object_id or "").strip()
    if value.startswith("cloud://"):
        return value
    if not CLOUDBASE_ENV_ID:
        raise ValueError("未配置 CLOUDBASE_ENV_ID。")
    bucket = CLOUDBASE_STORAGE_BUCKET
    if not bucket:
        prefix = value.split("/", 1)[0]
        if prefix.startswith("cloud://"):
            return value
        raise ValueError("未配置 CLOUDBASE_STORAGE_BUCKET，无法拼接 cloudObjectId。")
    return f"cloud://{CLOUDBASE_ENV_ID}.{bucket}/{value.lstrip('/')}"


def _storage_pick_download_url(row: Dict[str, Any]) -> str:
    for key in ("downloadUrl", "downloadUrlEncoded", "tempFileURL", "url"):
        value = str(row.get(key) or "").strip()
        if value:
            return value
    raise RuntimeError("CloudBase 未返回可用下载地址。")


def _storage_fetch_json(object_id: str) -> Dict[str, Any]:
    rows = _storage_get_download_info([object_id])
    if not rows:
        raise RuntimeError("未获取到对象下载信息。")
    row = rows[0]
    if row.get("code"):
        raise RuntimeError(f"获取对象下载信息失败：{row.get('code')} {row.get('message') or ''}".strip())
    url = _storage_pick_download_url(row)
    request = urllib.request.Request(url=url, method="GET")
    try:
        with urllib.request.urlopen(request, timeout=HTTP_TIMEOUT_SECONDS) as response:
            body = response.read().decode("utf-8", errors="replace")
            return json.loads(body)
    except urllib.error.HTTPError as exc:
        message = exc.read().decode("utf-8", errors="replace")
        raise RuntimeError(f"下载对象失败：{exc.code} {message}") from exc
    except urllib.error.URLError as exc:
        raise RuntimeError(f"下载对象网络失败：{exc}") from exc


def _build_labeled_input_object_id(file_name: str) -> str:
    return f"{CLOUDBASE_LABELED_INPUT_PREFIX}/{file_name}"


def _base_manifest_object(base_version: int) -> str:
    return f"{CLOUDBASE_MANIFEST_PREFIX}/base-{base_version}.json"


def _latest_manifest_object() -> str:
    return f"{CLOUDBASE_MANIFEST_PREFIX}/latest.json"


def _delta_object(base_version: int, delta_version: int) -> str:
    return f"{CLOUDBASE_DELTA_PREFIX}/base-{base_version}/delta-{delta_version}.json"


def _handle_upload_labeled(event: Dict[str, Any]) -> Dict[str, Any]:
    _require_admin(event)
    payload = _parse_body(event)
    rows = _validate_labeled_rows(payload if isinstance(payload, list) else payload.get("rows"))

    file_name = f"labeled_{_timestamp()}.json"
    object_id = _build_labeled_input_object_id(file_name)
    content = json.dumps(rows, ensure_ascii=False, indent=2).encode("utf-8")
    _storage_upload_bytes(object_id, content, "application/json; charset=utf-8")
    latest_meta = {
        "latest_input_name": file_name,
        "latest_input_object": object_id,
        "input_count": len(rows),
        "uploaded_at": _now_text(),
    }
    _storage_upload_bytes(
        CLOUDBASE_LATEST_LABELED_META_OBJECT,
        json.dumps(latest_meta, ensure_ascii=False, indent=2).encode("utf-8"),
        "application/json; charset=utf-8",
    )
    return _json_response(
        200,
        {
            "ok": True,
            "message": "已接收管理员标注数据。",
            "input_count": len(rows),
            "latest_input_name": file_name,
            "latest_input_object": object_id,
        },
    )


def _handle_latest_labeled(event: Dict[str, Any]) -> Dict[str, Any]:
    _require_admin(event)
    payload = _storage_fetch_json(CLOUDBASE_LATEST_LABELED_META_OBJECT)
    return _json_response(200, payload)


def _handle_publish_delta(event: Dict[str, Any]) -> Dict[str, Any]:
    _require_admin(event)
    payload = _parse_body(event)
    if not isinstance(payload, dict):
        raise ValueError("请求体必须是 JSON 对象。")

    base_version = int(payload.get("base_version") or 0)
    delta_version = int(payload.get("delta_version") or 0)
    previous_delta_version = int(payload.get("previous_delta_version") or 0)
    sections = payload.get("sections") or {}
    bundle_updates = payload.get("bundle_updates") or {}
    entry_count = int(payload.get("entry_count") or 0)
    section_entry_counts = payload.get("section_entry_counts") or {}
    released_at = str(payload.get("released_at") or _now_text())

    if base_version <= 0 or delta_version <= 0:
        raise ValueError("base_version 和 delta_version 必须为正整数。")
    if not isinstance(sections, dict):
        raise ValueError("sections 必须是 JSON 对象。")
    if not isinstance(bundle_updates, dict):
        raise ValueError("bundle_updates 必须是 JSON 对象。")
    if not isinstance(section_entry_counts, dict):
        raise ValueError("section_entry_counts 必须是 JSON 对象。")

    delta_payload = {
        "base_version": base_version,
        "delta_version": delta_version,
        "previous_delta_version": previous_delta_version,
        "released_at": released_at,
        "entry_count": entry_count,
        "section_entry_counts": section_entry_counts,
        "sections": sections,
        "bundle_updates": bundle_updates,
    }

    delta_object = _delta_object(base_version, delta_version)
    _storage_upload_bytes(
        delta_object,
        json.dumps(delta_payload, ensure_ascii=False, indent=2).encode("utf-8"),
        "application/json; charset=utf-8",
    )

    base_manifest_object = _base_manifest_object(base_version)
    try:
        manifest = _storage_fetch_json(base_manifest_object)
    except Exception:
        manifest = {
            "base_version": base_version,
            "embedded_delta_version": previous_delta_version,
            "latest_delta_version": 0,
            "deltas": [],
        }

    deltas = manifest.get("deltas") or []
    if not isinstance(deltas, list):
        deltas = []
    deltas = [row for row in deltas if int((row or {}).get("delta_version") or 0) != delta_version]
    deltas.append(
        {
            "delta_version": delta_version,
            "previous_delta_version": previous_delta_version,
            "entry_count": entry_count,
            "size_bytes": len(json.dumps(delta_payload, ensure_ascii=False).encode("utf-8")),
            "object_id": delta_object,
        }
    )
    deltas = sorted(deltas, key=lambda row: int((row or {}).get("delta_version") or 0))
    manifest = {
        "base_version": base_version,
        "embedded_delta_version": int(manifest.get("embedded_delta_version") or previous_delta_version),
        "latest_delta_version": max([0] + [int((row or {}).get("delta_version") or 0) for row in deltas]),
        "deltas": deltas,
        "updated_at": _now_text(),
    }
    _storage_upload_bytes(
        base_manifest_object,
        json.dumps(manifest, ensure_ascii=False, indent=2).encode("utf-8"),
        "application/json; charset=utf-8",
    )

    try:
        latest_manifest = _storage_fetch_json(_latest_manifest_object())
    except Exception:
        latest_manifest = {
            "latest_release_at": "",
            "base_version": base_version,
            "latest_delta_version": 0,
            "delta_count": 0,
            "manifest_object": base_manifest_object,
        }

    latest_manifest = {
        "latest_release_at": _now_text(),
        "base_version": base_version,
        "latest_delta_version": manifest["latest_delta_version"],
        "delta_count": len(deltas),
        "manifest_object": base_manifest_object,
    }
    _storage_upload_bytes(
        _latest_manifest_object(),
        json.dumps(latest_manifest, ensure_ascii=False, indent=2).encode("utf-8"),
        "application/json; charset=utf-8",
    )

    return _json_response(
        200,
        {
            "ok": True,
            "message": "delta 已发布到 CloudBase。",
            "base_version": base_version,
            "delta_version": delta_version,
            "embedded_delta_version": previous_delta_version,
            "manifest_object": base_manifest_object,
            "delta_object": delta_object,
        },
    )


def _handle_manifest(event: Dict[str, Any]) -> Dict[str, Any]:
    query = _get_query(event)
    base_version = int(query.get("base_version") or 0)
    if base_version <= 0:
        raise ValueError("base_version 必须是正整数。")
    payload = _storage_fetch_json(_base_manifest_object(base_version))
    return _json_response(
        200,
        {
            "base_version": base_version,
            "embedded_delta_version": int(payload.get("embedded_delta_version") or 0),
            "latest_delta_version": int(payload.get("latest_delta_version") or 0),
            "delta_count": len(payload.get("deltas") or []),
            "manifest_object": _base_manifest_object(base_version),
        },
    )


def _handle_latest_manifest(event: Dict[str, Any]) -> Dict[str, Any]:
    del event
    payload = _storage_fetch_json(_latest_manifest_object())
    return _json_response(200, payload)


def _handle_deltas(event: Dict[str, Any]) -> Dict[str, Any]:
    query = _get_query(event)
    base_version = int(query.get("base_version") or 0)
    from_delta = int(query.get("from_delta") or 0)
    limit = int(query.get("limit") or 10)
    if base_version <= 0:
        raise ValueError("base_version 必须是正整数。")
    limit = max(1, min(limit, MAX_DELTA_ITEMS_PER_RESPONSE))

    manifest = _storage_fetch_json(_base_manifest_object(base_version))
    deltas = manifest.get("deltas") or []
    if not isinstance(deltas, list):
        raise RuntimeError("base manifest 中 deltas 格式异常。")

    pending = [row for row in deltas if int((row or {}).get("delta_version") or 0) > from_delta]
    pending = sorted(pending, key=lambda row: int((row or {}).get("delta_version") or 0))
    selected = pending[:limit]

    object_ids = [str((row or {}).get("object_id") or "").strip() for row in selected if str((row or {}).get("object_id") or "").strip()]
    items: List[Dict[str, Any]] = []
    for object_id in object_ids:
        items.append(_storage_fetch_json(object_id))

    next_from = from_delta
    if items:
        next_from = int(items[-1].get("delta_version") or from_delta)

    request_url = ""
    if query:
        request_url = f"/api/mapping/deltas?{urllib.parse.urlencode(query)}"

    return _json_response(
        200,
        {
            "base_version": base_version,
            "from_delta_version": from_delta,
            "latest_delta_version": int(manifest.get("latest_delta_version") or base_version),
            "items": items,
            "has_more": len(pending) > len(selected),
            "next_from_delta_version": next_from,
            "request_url": request_url,
        },
    )


def main(event: Dict[str, Any], context: Any = None) -> Dict[str, Any]:
    del context
    method = _get_method(event)
    path = _get_path(event)

    if method == "OPTIONS":
        return _json_response(204, {})

    try:
        if method == "POST" and path == "/api/admin/mapping/upload-labeled":
            return _handle_upload_labeled(event)
        if method == "GET" and path == "/api/admin/mapping/latest-labeled":
            return _handle_latest_labeled(event)
        if method == "POST" and path == "/api/admin/mapping/publish-delta":
            return _handle_publish_delta(event)
        if method == "GET" and path == "/api/mapping/latest-manifest":
            return _handle_latest_manifest(event)
        if method == "GET" and path == "/api/mapping/delta-manifest":
            return _handle_manifest(event)
        if method == "GET" and path == "/api/mapping/deltas":
            return _handle_deltas(event)
        return _json_response(404, {"error": f"未找到路由：{path}"})
    except PermissionError as exc:
        return _json_response(403, {"error": str(exc)})
    except ValueError as exc:
        return _json_response(400, {"error": str(exc)})
    except FileNotFoundError as exc:
        return _json_response(404, {"error": str(exc)})
    except Exception as exc:
        return _json_response(500, {"error": str(exc)})
