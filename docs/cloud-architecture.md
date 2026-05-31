# CloudBase 云端链路

## 云端只承担两条最小职责

## 1. unknown 歌曲最小字段收集

- 接收匿名客户端提交的 unknown 歌曲
- 云端按标准化 key 去重
- 只保存：
  - `song_name`
  - `artist_names`
  - `album_name`
  - `normalized_key`
  - `submit_count`
  - 状态与时间字段
- 不保存聊天原文、好友 UID、Cookie、完整歌单

## 2. mapping delta 分发

- 管理员在本地完成标注与构建
- 生成新的 full mapping 与对应 delta
- 将 delta 与 manifest 发布到 CloudBase 云存储 / 云函数接口
- 客户端只负责拉取增量并更新本地 mapping

## 云函数目录

- `cloudbase-functions/unknown-song-api`
  - unknown 批量提交
  - 管理员导出、忽略、标记已导出
- `cloudbase-functions/mapping-build-admin`
  - manifest / delta 对外读取
  - 管理端发布 delta 所需接口

## 权限边界

- 普通客户端只能提交 unknown 与获取公开 mapping delta
- 管理员才能导出 unknown、标记状态、发布 delta
- 管理令牌只放在服务端环境变量，不写入前端

