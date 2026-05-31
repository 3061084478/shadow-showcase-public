# Shadow

Shadow 是一个围绕网易云音乐私信与歌曲分享场景构建的本地化 Web 应用。它把聊天归档、音乐关系分析、影子歌单生成、未知歌曲最小字段贡献、公共映射增量更新串成一条完整体验，重点放在真实数据、隐私边界和可持续迭代上。

## 项目亮点

- 本地优先：聊天归档、好友数据、SQLite 数据库、运行日志都落在本地目录，不依赖完整 SaaS 后台。
- 真实链路：前端、后端、网易云 API 网关、CloudBase unknown 收集、mapping delta 更新已经串通。
- 视觉统一：业务页采用深蓝夜景、暗色玻璃、冷色微光的产品化界面体系。
- 可维护：unknown 收集、mapping 发布、便携包打包、公共展示导出都拆成独立脚本和文档。

## 功能概览

- 二维码登录网易云音乐
- 好友同步与消息归档
- 聊天记录查询与筛选
- 音乐关系分析与可视化
- 影子歌单生成
- unknown 歌曲最小字段贡献
- 公共 `genre_mapping` 增量更新

## 目录说明

- `shadow (2)`：前端源码。公开导出时会统一重命名为 `shadow-web`
- `shadow_music_site`：本地 Python 后端
- `shadow_music_models`：歌曲标签模型、映射与增量逻辑
- `cloudbase-functions`：CloudBase 云函数
- `tools`：导出 unknown、构建 mapping delta、打包便携包等脚本
- `docs`：面对外部读者整理后的项目说明
- `portable`：Windows 便携包模板

## 文档入口

- [产品总览](docs/overview.md)
- [前端设计与页面分区](docs/frontend-design.md)
- [本地架构与数据流](docs/local-architecture.md)
- [CloudBase 云端链路](docs/cloud-architecture.md)
- [映射模型与 Delta 发布流程](docs/mapping-pipeline.md)
- [隐私、安全与发布方式](docs/privacy-and-release.md)

## 公开仓库与发行物

- 源码展示建议使用独立公开仓库目录 `shadow-showcase-public`
- Windows 客户版便携包建议只放在 GitHub Releases，不进入源码仓库历史
- 当前仓库提供脚本用于导出公开展示目录和校验便携包结构

## 相关脚本

- `tools/export_public_showcase.ps1`：导出公开展示版目录
- `tools/validate_portable_release.ps1`：校验便携包是否被运行残留污染
- `tools/create_shadow_web_portable_bundle.ps1`：构建 Windows 便携包

