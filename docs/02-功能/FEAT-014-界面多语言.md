# FEAT-014 · 界面多语言

- **状态**：可用（v1.14.0）
- **范围**：设置面板的语言选择、四语文案、圆盘盘面文字排法、README 英文说明
- **关联**：REQ-014、REQ-012、T-015
- **代码**：`src/lf_i18n.py`（`LANGUAGES` / `STRINGS` / `Lang` / `t()`）、
  `SettingsDialog.lang_combo` / `SettingsDialog.retranslate()` /
  `LauncherWindow.retranslate_ui()` / `TaijiLaunchButton._is_vertical_text()`

## 入口

主界面 →「设置」→ 面板第一行「界面语言」下拉。切换即时生效，无需重启，也不用点保存。

| 语言码 | 显示名（原生） | 说明 |
|---|---|---|
| `zh-Hans` | 简体中文 | 默认语言，也是译文表的源语言 |
| `en` | English | 圆盘改横排 `START` / `CLOSE` |
| `ja` | 日本語 | 圆盘竖排 `起動` / `終了` |
| `zh-Hant` | 繁體中文 | 圆盘竖排 `啟動` / `關閉` |

## 文案层

```python
from lf_i18n import Lang, t
Lang.set('en')                      # 只改语言码；界面刷新由调用方负责
label.setText(t('main.log'))        # → "Logs"
label.setText(t('msg.path_missing', path=p))
```

- 表结构：`STRINGS[键][语言码]`，共 117 条，键名点分层级；
- 回落链：**当前语言 → 简体中文 → 键名**。漏翻一条只会露出中文，不会抛异常、不会白屏；
- 占位符统一 `{}` + 关键字；`%USERPROFILE%` 这类百分号是普通字符；
- `Lang.set()` 对非法语言码直接收敛到 `zh-Hans`（配置可能被手改坏）；
- `missing_keys(code)` / 占位符一致性由 `tests/test_step15_i18n.py` 断言。

## 覆盖范围

| 位置 | 处理 |
|---|---|
| 窗口标题、预设行、六个胶囊、圆盘悬停提示 | `retranslate_ui()` |
| 设置面板标题、语言/字体/字号、自启动卡片、状态提示、关闭按钮 | `retranslate()` |
| 列表类型提示（文件夹 / 文件 / 路径不存在） | `entry_tooltip()`，换语言时逐项重设 |
| 提示框 / 确认框 / 文件选择框 / 关闭确认长文 | 全部走 `t()` |
| 圆盘盘面文字 | `t('main.taiji_run')` / `t('main.taiji_close')`，排法按语言切换 |
| 日志文件 | **不翻译**，保持中文（排障用） |
| 预设方案名称 | **不翻译**，属于用户数据 |

## 换语言时发生了什么

```
lang_combo.currentIndexChanged
  → Lang.set(code)
  → SettingsDialog.retranslate()      面板就地换文案 + 重算高度
  → LauncherWindow.retranslate_ui()   主窗口换文案 + 重算胶囊宽度 + 撑窗口
  → LauncherWindow.save_config()      写入 settings.language
```

**不重建窗口**是硬约束：`launched_items` 里记着"文件类条目 → 承载进程 PID"，
重建窗口会丢这份状态，表现是"换完语言之后关不掉刚打开的文件"。
设置面板同理就地重译，避免窗口闪一下。

主窗口文案换完后，英文/日文比中文长，胶囊要重新定宽：

```python
widths = self._pill_widths()          # 按新文案的 sizeHint 重算
self.left_pills.set_widths(widths)
self.right_pills.set_widths(widths)
hint = self.minimumSizeHint()
self.resize(max(self.width(), hint.width()), max(self.height(), hint.height()))
```

只放大不缩小：用户拖好的窗口不会因为切一次语言就缩回去。

## 圆盘：竖排 / 横排自动切换

| 语言 | 排法 | 字径 | 最小盘沿余量 |
|---|---|---|---|
| 简体中文 | 逐字竖排 启动 / 关闭 | 29px | 5.2px |
| 繁體中文 | 逐字竖排 啟動 / 關閉 | 29px | 5.2px |
| 日本語 | 逐字竖排 起動 / 終了 | 29px | 5.2px |
| English | 横排整词 START / CLOSE | 20px | 16.4px |

判据是 `_is_vertical_text()`：全角（汉字 / 假名）才竖排，出现拉丁字母就横排。
`START` 竖排要占 5 个字高（约 130px），而半条鱼只有约 70px 高，必须换排法。

横排的落地规则：

1. 在理想高度（中线上下 `0.17R`）附近按"离理想高度最近"扫描候选行；
2. 每一行用 `_fish_span()` 取鱼身可用区间，扣掉 4px 内边距；
3. 离中线留 `0.10R`：不留这段间距，`START` 和 `CLOSE` 会在盘心贴成一行；
4. 字盒四角必须在鱼身内、离盘沿 ≥5px、不与鱼眼相交；都不满足就把字号减 1 重来。

## 设置面板的布局

改为 `QGridLayout`（三列：标签 / 控件 / 数值）：

| 行 | 内容 |
|---|---|
| 0 | 界面语言 → 语言下拉（跨列 1） |
| 1 | 字体搭配 → 字体下拉 |
| 2 | 字体说明（跨满 3 列，自动折行） |
| 3 | 字体预览（跨满 3 列） |
| 4 | 字号 → 滑块 → `13 px` |

两个下拉框因此左边缘严格对齐；跨列是必须的——只跨两列会被右侧 `13 px` 那一列挤窄，
17px 字号下说明文字多折一行就压在边框上（v1.13.0 之前没暴露，是因为当时只有一行控件）。

## 顺带修掉的一个小问题

QSS 里给 `::drop-down` 设了宽度 + `border: none` 之后，Qt 就不再画系统箭头，
下拉框看上去和普通输入框一样。新增 `ThemedCombo` 自绘一枚金色雪佛龙（chevron），
主界面的预设下拉与设置里两个下拉都换用它。

## 已知限制

- 未做系统语言自动识别：首次启动固定简体中文，之后记住用户选择；
- 日志文件仍是中文；
- 预设方案名称不随语言变化（用户数据）；
- 英文圆盘字径比中日文小（20px vs 29px），是"横排整词 + 盘沿约束"的必然结果；
- exe 文件属性里的描述仍是中文（version.txt 的 StringTable 只有一份语言）。
