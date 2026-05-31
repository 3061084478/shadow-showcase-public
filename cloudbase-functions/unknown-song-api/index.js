'use strict';

const cloudbase = require('@cloudbase/node-sdk');

const app = cloudbase.init({ env: cloudbase.SYMBOL_CURRENT_ENV });
const db = app.database();

const COLLECTION_NAME = 'unknown_song_submissions';
const MAX_SONG_NAME_LENGTH = 200;
const MAX_ALBUM_NAME_LENGTH = 200;
const MAX_ARTIST_COUNT = 10;
const MAX_ARTIST_NAME_LENGTH = 100;
const MAX_BATCH_ITEMS = Number(process.env.MAX_BATCH_ITEMS || 100);
const MAX_REQUEST_BYTES = Number(process.env.MAX_REQUEST_BYTES || 131072);
const RATE_LIMIT_PER_MINUTE = Number(process.env.RATE_LIMIT_PER_MINUTE || 20);
const REPEAT_SUPPRESSION_MINUTES = Number(process.env.REPEAT_SUPPRESSION_MINUTES || 10);
const ADMIN_TOKEN = String(process.env.ADMIN_TOKEN || '').trim();
const RATE_LIMIT_COLLECTION = String(process.env.RATE_LIMIT_COLLECTION || 'shadow_unknown_limits').trim();

const CONTROL_CHAR_PATTERN = /[\x00-\x1F\x7F]/g;
const MULTI_SPACE_PATTERN = /\s+/g;
const EDGE_PUNCTUATION = " \t\r\n\"'“”‘’`~!@#$%^&*()_+-=[]{}|\\:;,./<>?，。！？、；：（）【】《》";

function nowText() {
  return new Date().toISOString();
}

function jsonResponse(statusCode, payload) {
  return {
    statusCode,
    headers: {
      'Content-Type': 'application/json; charset=utf-8',
      'Access-Control-Allow-Origin': '*',
      'Access-Control-Allow-Methods': 'GET, POST, OPTIONS',
      'Access-Control-Allow-Headers': 'Content-Type, Authorization, X-Admin-Token'
    },
    body: JSON.stringify(payload)
  };
}

function textToHalfWidth(value) {
  return String(value || '').normalize('NFKC');
}

function sanitizeText(value, maxLength) {
  return textToHalfWidth(value)
    .replace(CONTROL_CHAR_PATTERN, '')
    .replace(MULTI_SPACE_PATTERN, ' ')
    .trim()
    .slice(0, maxLength);
}

function normalizeText(value) {
  return sanitizeText(value, 500).toLowerCase().replace(new RegExp(`^[${escapeForRegExp(EDGE_PUNCTUATION)}]+|[${escapeForRegExp(EDGE_PUNCTUATION)}]+$`, 'g'), '');
}

function escapeForRegExp(value) {
  return value.replace(/[.*+?^${}()|[\]\\]/g, '\\$&');
}

function cleanArtistNames(input) {
  const values = Array.isArray(input) ? input : [];
  const result = [];
  const seen = new Set();
  for (const item of values.slice(0, MAX_ARTIST_COUNT)) {
    const artist = sanitizeText(item, MAX_ARTIST_NAME_LENGTH);
    if (!artist) continue;
    const normalized = normalizeText(artist);
    if (!normalized || seen.has(normalized)) continue;
    seen.add(normalized);
    result.push(artist);
  }
  return result;
}

function buildNormalizedKey(songName, artistNames, albumName) {
  const artists = artistNames
    .map((item) => normalizeText(item))
    .filter(Boolean)
    .sort();
  return `${normalizeText(songName)}::${normalizeText(artists.join('|'))}::${normalizeText(albumName)}`;
}

function cleanUnknownItem(item) {
  const song_name = sanitizeText(item.song_name, MAX_SONG_NAME_LENGTH);
  const album_name = sanitizeText(item.album_name, MAX_ALBUM_NAME_LENGTH);
  const artist_names = cleanArtistNames(item.artist_names);
  if (!song_name) {
    throw new Error('song_name 不能为空');
  }
  if (!artist_names.length) {
    throw new Error('artist_names 至少需要 1 个歌手');
  }
  return {
    song_name,
    artist_names,
    album_name,
    normalized_key: buildNormalizedKey(song_name, artist_names, album_name)
  };
}

function parseBody(event) {
  if (!event.body) return {};
  if (typeof event.body === 'object') return event.body;
  try {
    return JSON.parse(event.body);
  } catch (error) {
    throw new Error('请求体不是合法 JSON');
  }
}

function getPath(event) {
  return String(event.path || event.requestContext?.path || '').trim();
}

function getMethod(event) {
  return String(event.httpMethod || event.requestContext?.httpMethod || 'GET').toUpperCase();
}

function getHeader(event, key) {
  const headers = event.headers || {};
  const lowerKey = key.toLowerCase();
  for (const headerKey of Object.keys(headers)) {
    if (String(headerKey).toLowerCase() === lowerKey) {
      return String(headers[headerKey] || '');
    }
  }
  return '';
}

function getAdminTokenFromRequest(event) {
  const authHeader = getHeader(event, 'Authorization').trim();
  if (authHeader.toLowerCase().startsWith('bearer ')) {
    return authHeader.slice(7).trim();
  }
  return getHeader(event, 'X-Admin-Token').trim();
}

function requireAdmin(event) {
  if (!ADMIN_TOKEN) {
    throw Object.assign(new Error('服务端未配置 ADMIN_TOKEN'), { statusCode: 500 });
  }
  if (getAdminTokenFromRequest(event) !== ADMIN_TOKEN) {
    throw Object.assign(new Error('管理员令牌无效'), { statusCode: 403 });
  }
}

function parseQuery(event) {
  return event.queryStringParameters || {};
}

async function enforceRateLimit(event) {
  const ip = getHeader(event, 'x-forwarded-for').split(',')[0].trim() || getHeader(event, 'x-real-ip').trim() || 'unknown';
  const minuteBucket = new Date().toISOString().slice(0, 16);
  const collection = db.collection(RATE_LIMIT_COLLECTION);
  const now = nowText();
  const existing = await collection.where({ client_ip: ip }).limit(1).get();
  if (!existing.data.length) {
    await collection.add({
      client_ip: ip,
      minute_bucket: minuteBucket,
      request_count: 1,
      updated_at: now
    });
    return;
  }
  const row = existing.data[0];
  if (row.minute_bucket !== minuteBucket) {
    await collection.doc(row._id).update({
      minute_bucket: minuteBucket,
      request_count: 1,
      updated_at: now
    });
    return;
  }
  if (Number(row.request_count || 0) >= RATE_LIMIT_PER_MINUTE) {
    throw Object.assign(new Error('提交过于频繁，请稍后再试'), { statusCode: 429 });
  }
  await collection.doc(row._id).update({
    request_count: Number(row.request_count || 0) + 1,
    updated_at: now
  });
}

async function handleBatchSubmit(event) {
  await enforceRateLimit(event);
  const payload = parseBody(event);
  const rawBytes = Buffer.byteLength(JSON.stringify(payload || {}), 'utf8');
  if (rawBytes > MAX_REQUEST_BYTES) {
    throw Object.assign(new Error('请求体过大'), { statusCode: 400 });
  }

  const items = payload.items;
  if (!Array.isArray(items)) {
    throw Object.assign(new Error('items 必须是数组'), { statusCode: 400 });
  }
  if (items.length > MAX_BATCH_ITEMS) {
    throw Object.assign(new Error(`单次最多提交 ${MAX_BATCH_ITEMS} 条`), { statusCode: 400 });
  }

  const deduped = new Map();
  for (const item of items) {
    if (!item || typeof item !== 'object') continue;
    try {
      const cleaned = cleanUnknownItem(item);
      if (!deduped.has(cleaned.normalized_key)) {
        deduped.set(cleaned.normalized_key, cleaned);
      }
    } catch (_) {
      continue;
    }
  }

  let inserted_count = 0;
  let submit_count_incremented = 0;
  let suppressed_count = 0;
  const now = nowText();
  const cutoff = Date.now() - REPEAT_SUPPRESSION_MINUTES * 60 * 1000;
  const collection = db.collection(COLLECTION_NAME);

  for (const row of deduped.values()) {
    const existing = await collection.where({ normalized_key: row.normalized_key }).limit(1).get();
    if (!existing.data.length) {
      await collection.add({
        song_name: row.song_name,
        artist_names_json: JSON.stringify(row.artist_names),
        album_name: row.album_name,
        normalized_key: row.normalized_key,
        submit_count: 1,
        status: 'pending',
        first_seen_at: now,
        last_seen_at: now,
        last_submitted_at: now,
        created_at: now,
        updated_at: now
      });
      inserted_count += 1;
      continue;
    }

    const current = existing.data[0];
    const lastSubmitted = current.last_submitted_at ? new Date(current.last_submitted_at).getTime() : 0;
    if (lastSubmitted && lastSubmitted >= cutoff) {
      await collection.doc(current._id).update({
        last_submitted_at: now,
        updated_at: now
      });
      suppressed_count += 1;
      continue;
    }

    await collection.doc(current._id).update({
      submit_count: Number(current.submit_count || 0) + 1,
      last_seen_at: now,
      last_submitted_at: now,
      updated_at: now
    });
    submit_count_incremented += 1;
  }

  return jsonResponse(200, {
    ok: true,
    received_count: items.length,
    batch_deduped_count: deduped.size,
    accepted_count: deduped.size,
    inserted_count,
    submit_count_incremented,
    suppressed_count
  });
}

async function handleExport(event) {
  requireAdmin(event);
  const query = parseQuery(event);
  const status = String(query.status || 'pending').trim();
  const collection = db.collection(COLLECTION_NAME);
  const result = status === 'all'
    ? await collection.get()
    : await collection.where({ status }).get();
  const rows = result.data || [];
  return {
    statusCode: 200,
    headers: {
      'Content-Type': 'application/json; charset=utf-8',
      'Access-Control-Allow-Origin': '*',
      'Access-Control-Allow-Methods': 'GET, POST, OPTIONS',
      'Access-Control-Allow-Headers': 'Content-Type, Authorization, X-Admin-Token'
    },
    body: JSON.stringify(
      rows.map((row) => ({
        song_name: row.song_name || '',
        artist_names: JSON.parse(row.artist_names_json || '[]'),
        album_name: row.album_name || ''
      }))
    )
  };
}

async function handleStats(event) {
  requireAdmin(event);
  const collection = db.collection(COLLECTION_NAME);
  const rows = await collection.get();
  const stats = { total: 0, pending: 0, exported: 0, ignored: 0 };
  for (const row of rows.data || []) {
    stats.total += 1;
    const status = String(row.status || 'pending');
    stats[status] = Number(stats[status] || 0) + 1;
  }
  return jsonResponse(200, stats);
}

async function handleTop(event) {
  requireAdmin(event);
  const query = parseQuery(event);
  const limit = Math.max(1, Math.min(Number(query.limit || 100), 200));
  const rows = await db.collection(COLLECTION_NAME).orderBy('submit_count', 'desc').limit(limit).get();
  return jsonResponse(200, {
    rows: (rows.data || []).map((row) => ({
      song_name: row.song_name || '',
      artist_names: JSON.parse(row.artist_names_json || '[]'),
      album_name: row.album_name || '',
      normalized_key: row.normalized_key || '',
      submit_count: Number(row.submit_count || 0),
      status: row.status || 'pending',
      last_seen_at: row.last_seen_at || ''
    }))
  });
}

async function handleMarkExported(event) {
  requireAdmin(event);
  const body = parseBody(event);
  const fromStatus = String(body.status || 'pending').trim();
  const collection = db.collection(COLLECTION_NAME);
  const result = fromStatus === 'all'
    ? await collection.get()
    : await collection.where({ status: fromStatus }).get();
  const now = nowText();
  let updated = 0;
  for (const row of result.data || []) {
    await collection.doc(row._id).update({ status: 'exported', updated_at: now });
    updated += 1;
  }
  return jsonResponse(200, { ok: true, updated_count: updated });
}

async function handleIgnore(event) {
  requireAdmin(event);
  const body = parseBody(event);
  const keys = Array.isArray(body.normalized_keys) ? body.normalized_keys.map((item) => String(item || '').trim()).filter(Boolean) : [];
  const now = nowText();
  let updated = 0;
  for (const key of keys) {
    const result = await db.collection(COLLECTION_NAME).where({ normalized_key: key }).limit(1).get();
    if (!result.data.length) continue;
    await db.collection(COLLECTION_NAME).doc(result.data[0]._id).update({ status: 'ignored', updated_at: now });
    updated += 1;
  }
  return jsonResponse(200, { ok: true, updated_count: updated });
}

async function handleCleanupExported(event) {
  requireAdmin(event);
  const rows = await db.collection(COLLECTION_NAME).where({ status: 'exported' }).get();
  let deleted = 0;
  for (const row of rows.data || []) {
    await db.collection(COLLECTION_NAME).doc(row._id).remove();
    deleted += 1;
  }
  return jsonResponse(200, { ok: true, deleted_count: deleted });
}

exports.main = async (event = {}) => {
  const method = getMethod(event);
  const path = getPath(event);

  if (method === 'OPTIONS') {
    return jsonResponse(204, {});
  }

  try {
    if (method === 'POST' && path === '/api/unknown-song/batch-submit') {
      return await handleBatchSubmit(event);
    }
    if (method === 'GET' && path === '/api/admin/unknown-song/export') {
      return await handleExport(event);
    }
    if (method === 'GET' && path === '/api/admin/unknown-song/stats') {
      return await handleStats(event);
    }
    if (method === 'GET' && path === '/api/admin/unknown-song/top') {
      return await handleTop(event);
    }
    if (method === 'POST' && path === '/api/admin/unknown-song/mark-exported') {
      return await handleMarkExported(event);
    }
    if (method === 'POST' && path === '/api/admin/unknown-song/ignore') {
      return await handleIgnore(event);
    }
    if (method === 'POST' && path === '/api/admin/unknown-song/cleanup-exported') {
      return await handleCleanupExported(event);
    }
    return jsonResponse(404, { error: `未找到路由: ${path}` });
  } catch (error) {
    const statusCode = Number(error.statusCode || 500);
    return jsonResponse(statusCode, { error: error.message || '服务器内部错误' });
  }
};
