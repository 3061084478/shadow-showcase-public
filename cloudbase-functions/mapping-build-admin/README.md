# mapping-build-admin

这是当前 Shadow 的 CloudBase mapping delta 管理函数。

它现在不再负责：

- 云端执行训练/构建
- 云端重建完整 `genre_mapping.json`
- 发布 full latest mapping 整包

它现在只负责：

1. 保存管理员上传的标注 JSON
2. 发布管理员本地构建后生成的 `delta`
3. 维护 `manifest`
4. 提供客户端下载缺失 delta 的接口

## 支持接口

管理员接口：

- `POST /api/admin/mapping/upload-labeled`
- `GET /api/admin/mapping/latest-labeled`
- `POST /api/admin/mapping/publish-delta`

客户端公开接口：

- `GET /api/mapping/latest-manifest`
- `GET /api/mapping/delta-manifest?base_version=2`
- `GET /api/mapping/deltas?base_version=2&from_delta=9&limit=20`

## 已标注 JSON 规范

每条必须包含：

- `song_name`
- `artist_names`
- `album_name`
- `genre_label`

推荐主格式仍然是顶层纯 JSON 数组。

## 环境变量

- `ADMIN_TOKEN`
- `CLOUDBASE_ENV_ID`
- `CLOUDBASE_API_KEY`
- `CLOUDBASE_LABELED_INPUT_PREFIX=genre-pipeline/admin/labeled-inputs`
- `CLOUDBASE_LATEST_LABELED_META_OBJECT=genre-pipeline/admin/latest_labeled_input.json`
- `CLOUDBASE_MANIFEST_PREFIX=genre-pipeline/manifests`
- `CLOUDBASE_DELTA_PREFIX=genre-pipeline/deltas`

## 部署方式

先运行：

```powershell
powershell -ExecutionPolicy Bypass -File .\tools\create_cloudbase_mapping_bundle.ps1
```

然后上传：

- `build/cloudbase-mapping-build-admin`

这个新 bundle 不再包含完整 `shadow_music_models` 训练运行包，只包含 CloudBase 分发函数本身。
