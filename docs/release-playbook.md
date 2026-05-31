# 公开展示与便携包发布路线

## 一、公开源码目录

使用下面的脚本从当前开发仓库导出一个干净的公开展示目录：

```powershell
pwsh -ExecutionPolicy Bypass -File .\tools\export_public_showcase.ps1
```

导出结果会生成在：

```text
shadow-showcase-public/
```

这个目录只保留适合公开展示的源码、文档、云函数和工具脚本，不会带入本地数据库、日志、缓存和 release 污染物。

## 二、Windows 便携包

建议不要直接在最终发布目录上做测试，而是走三阶段：

1. `release-showcase-build`
2. `release-showcase-verify`
3. `release-showcase-final`

执行脚本：

```powershell
pwsh -ExecutionPolicy Bypass -File .\tools\create_showcase_release.ps1
```

脚本会完成：

- 构建便携包到 build 目录
- 复制一份到 verify 目录
- 在 verify 目录做结构校验
- 校验通过后，从未运行过的 build 目录复制到 final 目录
- 最终只从 final 目录打出 zip

## 三、GitHub 发布建议

- 公开仓库上传 `shadow-showcase-public` 中的源码
- Windows 客户版压缩包只放在 GitHub Releases
- 不要把 zip、数据库、日志、tmp、运行态 `data/` 提交进源码仓库历史

## 四、发布前检查

- 没有个人绝对路径
- 没有本地 Cookie 或配置文件
- 没有 `.db`、`.log`、`tmp` 运行残留
- 便携包内 `data/` 只有空目录骨架
- README 面向普通用户，不出现管理员维护内容

