# FEAT-011 · 字体层级与微交互动效

- **状态**：可用（v1.11.0）
- **范围**：主窗口（预设行、胶囊按钮、程序列表）、启停圆盘、设置面板
- **关联**：REQ-011、REQ-006、REQ-009
- **代码**：`Theme` / `ui_font()` / `_resolve_family()` / `PillButton` / `ListRowDelegate` / `AnimatedList`

## 设计令牌

```python
class Theme:
    INK        = '#2B2721'   # 主文字
    INK_SOFT   = '#5C5446'   # 次级文字（标签）
    MUTED      = '#8A8170'   # 辅助说明
    PANEL      = '#EDE7DB'   # 面板底
    CARD       = '#FFFDF8'   # 卡片/胶囊底
    CARD_EDGE  = '#E2DACB'
    GOLD       = '#BEAD86'
    GOLD_DEEP  = '#A8873F'
    GREEN      = '#4CC38A'
    BLOOD      = '#C1121F'
    HOVER_MS   = 110
    PRESS_MS   = 90
    ANIMATIONS = True        # 读系统「动画效果」开关
```

新增控件一律从这里取色与时长的原因：v1.9–v1.10 期间出现过"每加一个控件就随手取一个颜色"
导致的色值漂移（面板底先后出现过 `#F4F1EA` / `#EDE7DB` 两种）。

## 字体层级

| 角色 | 家族（首选 → 回退） | 字号 | 字重 | 字距 | 用在哪 |
|---|---|---|---|---|---|
| display | Noto Sans SC → 雅黑 UI → 雅黑 → Segoe UI | 17 | 700 | +0.3 | 设置面板标题 |
| title | 同上 | 14 | 600 | +0.3 | 设置卡片标题 |
| pill | 雅黑 UI → 雅黑 → Segoe UI → Arial | 13 | 500 | +0.3 | 六枚操作胶囊 |
| pill-compact | 同上 | 12 | 600 | +0.3 | 预设行「新建 / 删除」 |
| label | 同上 | 12 | 600 | +0.4 | 「预设方案」 |
| body | 同上 | 13 | 400 | +0.2 | 列表行、下拉框 |
| small | 同上 | 11 | 400 | 0 | 设置说明与提示 |

本机实测解析结果：胶囊/正文 = `Microsoft YaHei UI` 13px（weight 57），标题 = `Noto Sans SC` 17px（weight 75），辅助 = `Microsoft YaHei UI` 11px。

> Qt 会把绝对字距量化到 1/64 px（0.2 实际存为 0.1875），这是平台行为，不是实现偏差。

## 动效规格

| 交互 | 时长 | 缓动 | 变化内容 |
|---|---|---|---|
| 胶囊悬停 | 110ms | OutCubic | 底色下半由米金转暖白、边框转深金、内高光增强、底缘反光出现、文字转近黑 |
| 胶囊按下 | 90ms | OutQuad | 整体压暗、内阴影增强、顶部高光消失、**文字下沉 0.9px** |
| 列表行悬停 | ≈110ms（指数 0.30） | 指数逼近 | 暖白底色淡入，文字加深 |
| 列表行选中 | ≈110ms（指数 0.35） | 指数逼近 | 暖金底色 + 左侧 3px 强调条 |
| 圆盘悬停 | 130ms | OutCubic | 半圆外三圈发光淡入、鱼身提亮 10%、外圈高光增强 |
| 设置项悬停 | 属性直读 | — | 底色/边框/竖条/开关发光环四处联动 |

动效只改绘制参数、不改几何：`PillButton` 只 `update()`；列表只 `viewport().update()`；
圆盘只重绘自身。因此窗口布局在整个交互过程中不会重排。

### 尊重系统"减少动画"

启动时读 `SystemParametersInfoW(SPI_GETCLIENTAREAANIMATION)`：

```python
Theme.ANIMATIONS = _system_animations_enabled()
Theme.hover_ms()   # 110 或 1
```

关闭系统动画效果后，过渡时长压到 1ms——界面立刻响应，最终视觉状态完全一致。

## 列表行绘制

| 元素 | 规格 |
|---|---|
| 行高 | 34px（`ListRowDelegate.ROW_HEIGHT`） |
| 行块 | 左右内缩 2px、圆角 8px |
| 悬停底 | `#FBF6EC`，强度 0.85 |
| 选中底 | `#EFE2C4`，强度 0.95；左侧强调条 `#B08E4F` 3×（行高−16） |
| 类型图形 | 18×18 矢量：文件夹（金）/ 可执行（方框+三角）/ 普通文件（页）/ 失效（红三角+!） |
| 文字 | 13px，缺省 `#33302A`；失效行 `#A8543C`；悬停/选中加深到 `#14120E` |
| 省略 | `ElideMiddle`，路径名中间省略（比尾部省略更能保留扩展名） |

类型在 `add_to_list()` 时算一次存进 `Qt.UserRole + 1`，delegate 每帧只读缓存——
避免每帧对每行做 `os.path.isdir/isfile`。

## 已知限制

- **字体依赖本机安装**：Noto Sans SC 不随 Windows 预装，缺失时标题回退到雅黑 UI，
  层级会变粗一档，但不会错版。
- **字重 500 可能被合成**：雅黑 UI 只有 Regular/Bold，`QFont.Medium` 在部分字号下
  由系统合成，视觉接近 Regular。这是字体家族的固有限制，不额外用伪加粗弥补。
- **列表滚动时悬停会短暂清空**：滚动后行号不再可信，先清空再由 `itemEntered` 重新点亮，
  避免高亮停在错误的行上。
- 动效时长不可在界面内调整（要改只能改 `Theme`），本版不做"动画速度"设置项。

## 测试

`tests/test_step12_typography_motion.py`（16 项）：字体解析与字距量化、动效时长区间、
系统动画开关退化、胶囊悬停/按下补间与像素差、列表 hover/select 补间、类型分类与 emoji 剥离、
圆盘发光补间。

回归：T-001～T-012。其中 T-010 的圆角断言已从"查 QSS 字符串"改为"查 `corner_radii()`"。

真实产物截图：`docs/images/real-window-v1.11.0.png`（exe + PrintWindow，含四种条目类型）、
`docs/images/hover-states.png`（源码渲染的交互三态放大图）。
