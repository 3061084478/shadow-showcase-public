# 映射模型与 Delta 发布流程

## 总体原则

Shadow 当前走的是“映射优先”的轻量分类路线：

- 本地应用依赖 `genre_mapping.json` 做快速识别
- 模型补充与数据集扩展仍沿用现有脚本
- unknown 数据只是原料，不在云端自动 GPT 标注

## 管理员工作流

1. 从云端导出 pending unknown JSON
2. 在本地完成标注
3. 使用现有训练与映射更新脚本生成新的 full mapping
4. 对比旧 mapping 与新 mapping，计算出 delta
5. 将 delta 发布到 CloudBase
6. 客户端自动从自己的 base version 衔接到最新 delta version

## Full Mapping 与 Delta 的关系

- 每个客户端自带一个 base mapping
- 云端保存从某个 base 起逐步追加的 delta 链
- 新用户从内置 base 开始
- 老用户只获取自己尚未应用的 delta
- 发新版本时可以更换新的 base，同时保留后续增量链

## 仓库中的相关脚本

- `tools/prepare_mapping_delta_release.py`
- `tools/publish_mapping_delta.ps1`
- `tools/check_labeled_against_mapping.py`
- `shadow_music_models/scripts/update_genre_training_and_mapping.py`

## 不在云端做的事情

- 不在云端跑 GPT 标注
- 不在云端做聊天数据处理
- 不在云端做训练流程全自动化
- 不把本地完整数据集直接暴露给客户端

