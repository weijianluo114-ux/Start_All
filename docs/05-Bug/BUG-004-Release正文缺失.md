# BUG-004 · Release 正文只剩一行「Full Changelog」

- **状态**：已修复（工作流，v1.7.0 之后生效）
- **发现日期**：2026-10-20
- **影响版本**：v1.7.0 的 Release 正文
- **关联**：`.github/workflows/build.yml`

## 现象

推送 `v1.7.0` 标签后，Actions 构建成功、资产 `LaunchForge_v1.7.0.exe` 正常上传，但
Release 正文只有一行：

```
**Full Changelog**: https://github.com/.../compare/v1.6.1...v1.7.0
```

工作流里写好的「下载与使用 / 已知限制 / SmartScreen」说明块完全没有出现。

## 根因

`softprops/action-gh-release@v2` 的 `append_body` 是**布尔开关**（默认 `false`），
不是正文载体。之前把它当字符串塞了整段 Markdown：

```yaml
append_body: |
  ## 下载与使用
  ...
```

YAML 把它解析成非空字符串 → 被当作"真值"处理，但动作并没有把它拼进正文；
正文由 `generate_release_notes: true` 生成，于是只剩自动生成的 `Full Changelog` 一行。

> 为什么 v1.6.1 看起来正常：那次发布后是用 PAT 手工重写了 Release 正文，
> 掩盖了工作流的缺陷。

## 修复

1. 新增 `Prepare release body` 步骤：用 PowerShell **数组拼正文**，写到 `release_body.md`；
2. `Publish release` 改用 `body_path: release_body.md`，并移除 `generate_release_notes`；
3. 正文模板包含：版本号、CHANGELOG 链接、下载与使用、SmartScreen 提示、已知限制。

## 踩到的两个坑（写进注释）

| 坑 | 现象 | 处理 |
|---|---|---|
| PowerShell here-string 在 YAML 块标量里 | 结束符 `"@` 被缩进 → 解析报错 | 改用 `@( ... )` 数组 + `-join "\`n"` |
| 正文里用中文引号 “…” | PowerShell 把 `“ ”` 当字符串定界符 → 语法错误 | 全部改用 `「」` |

## 验证

把工作流里的 PowerShell 步骤抽出来本地试跑（Windows PowerShell 5.1）：

```
$ver = "1.7.0" ...
release_body.md 生成成功（502 字节，19 个换行）
```

实测正文首段：

```
## 一键多启 v1.7.0

### 本次变更
完整变更见 [CHANGELOG](.../CHANGELOG.md)。

### 下载与使用

1. 下载下方 **LaunchForge_v1.7.0.exe**；
...
```

## 遗留

v1.7.0 这一次的 Release 正文仍是自动生成的单行，修复只对**后续发布**生效。
补正文需要 `Contents: write` 的 PAT（`PATCH /repos/{o}/{r}/releases/{id}`）或在网页上编辑。
