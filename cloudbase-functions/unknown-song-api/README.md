# unknown-song-api

用于 CloudBase 的最小 unknown 歌曲收集与导出函数。

## 提供接口

- `POST /api/unknown-song/batch-submit`
- `GET /api/admin/unknown-song/export`
- `GET /api/admin/unknown-song/stats`
- `GET /api/admin/unknown-song/top`
- `POST /api/admin/unknown-song/mark-exported`
- `POST /api/admin/unknown-song/ignore`
- `POST /api/admin/unknown-song/cleanup-exported`

## 环境变量

- `ADMIN_TOKEN`
- `REPEAT_SUPPRESSION_MINUTES=10`
- `MAX_BATCH_ITEMS=100`
- `MAX_REQUEST_BYTES=131072`
- `RATE_LIMIT_PER_MINUTE=20`
- `RATE_LIMIT_COLLECTION=shadow_unknown_limits`

## 数据集合

- `unknown_song_submissions`
- `shadow_unknown_limits`

## 提交格式

```json
{
  "items": [
    {
      "song_name": "Lonely is the Night",
      "artist_names": ["陶喆", "黄丽玲"],
      "album_name": "STUPID POP SONGS"
    }
  ],
  "client_version": "1.0.0"
}
```

## 导出格式

```json
[
  {
    "song_name": "Lonely is the Night",
    "artist_names": ["陶喆", "黄丽玲"],
    "album_name": "STUPID POP SONGS"
  }
]
```
