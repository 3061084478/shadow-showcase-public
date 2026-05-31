# 本地架构与数据流

## 运行形态

Shadow 的核心逻辑运行在本地：

- 前端负责界面与交互
- Python 后端负责归档、查询、分析、unknown 队列与 mapping 更新
- Node API 网关负责连接网易云能力
- SQLite 负责保存本地归档数据

## 本地数据流

1. 用户启动应用并扫码登录网易云
2. 本地后端通过 API 网关拉取好友、消息与歌曲元数据
3. 归档服务将消息写入 SQLite
4. 歌曲分类服务根据本地 mapping 做识别
5. unknown 结果进入本地待上传队列
6. 用户授权后，再批量上传最小三字段到云端
7. 客户端定期检查云端 delta manifest，必要时拉取增量并更新本地 mapping

## 主要模块

- `shadow-web`：前端页面、组件、样式与 API 适配
- `shadow_music_site`：HTTP 服务、数据访问、归档、查询、影子歌单、unknown 贡献、mapping sync
- `shadow_music_models`：映射数据结构、delta 计算与训练更新脚本

## 本地存储原则

- 运行产物应只保留在应用数据目录
- 数据库存储在本地 SQLite
- 日志仅记录接口、状态、耗时和错误类型
- unknown 上传只携带 `song_name`、`artist_names`、`album_name`

