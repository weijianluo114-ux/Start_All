# FEAT-015 · 品牌图标

- **状态**：可用（v1.15.0）
- **范围**：`assets/logo.ico`（七档）、`assets/logo.png`（母版）、exe / 窗口 / 任务栏 / 快捷方式
- **关联**：REQ-015、T-019
- **代码**：`LauncherWindow.__init__` 的 `setWindowIcon(QIcon(icon_path))`；
  打包参数 `--icon=assets/logo.ico` + `--add-data "assets/logo.ico;."`

![品牌图标与七档尺寸](logo-v1.15.0.png)

## 资源

| 文件 | 规格 | 用途 |
|---|---|---|
| `assets/logo.ico` | 75,607 B，7 帧（16–256） | exe 文件图标；打包进 `_MEIPASS`，运行时设窗口图标 |
| `assets/logo.png` | 780×780 RGB | 母版，供重新生成 ico、README 引用、文档配图 |

## 从源稿到成品

源图 1024×1024，主体（方框 + 箭头）占 `x 184..873, y 193..827`，
右下角 `y ≥ 930` 是「AI生成 WORKBUDDY」水印。

取正方形裁剪框 `(138, 118, 918, 898)`（边长 780）：

- 以主体中心 `(528, 508)` 为中心，方框约占画面 84%——既保留了原稿留白，
  又让 16px 下的主体不至于太小；
- 下沿 898 < 930，**水印被整体裁掉**，不需要修补像素；
- 四边各留约 30px 背景，避免主体顶边导致小尺寸发糊。

```python
im = Image.open(src).convert('RGB')
crop = im.crop((138, 118, 918, 898))          # 780×780，避开右下角水印
crop.save('assets/logo.png')
crop.save('assets/logo.ico', format='ICO',
          sizes=[(s, s) for s in (16, 24, 32, 48, 64, 128, 256)])
```

## 七档尺寸各自的场景

| 档位 | 典型场景 |
|---|---|
| 16 | 标题栏、列表小图标视图 |
| 24 | 任务栏（100% 缩放） |
| 32 | 桌面、Alt+Tab（100%） |
| 48 | 中等图标视图、开始菜单 |
| 64 | 大图标视图（100%） |
| 128 | 大图标（150% 缩放） |
| 256 | 超大图标、高 DPI 桌面 |

256 档在 ICO 内以 **PNG** 存储（Pillow 自动处理）；其余档为 32bpp BMP。
`tests/test_step18_brand_icon.py` 会逐帧校验：正方形、字节数非零、
偏移不越界，并断言 256 帧的签名是 `\x89PNG`。

## 生效路径

三条路径共用同一份 ico，避免"界面换了、exe 没换"：

1. **exe 文件图标**：PyInstaller `--icon=assets/logo.ico`，写入 PE 的 `RT_GROUP_ICON`；
2. **窗口 / 任务栏图标**：`--add-data "assets/logo.ico;."` 把它放进 `_MEIPASS`，
   启动时 `QIcon(icon_path)` → `setWindowIcon()`；源码运行时读仓库的 `assets/logo.ico`；
3. **桌面快捷方式**：`scripts/update_shortcut.py` 指向当前 exe，图标随 exe 走。

## 验证方式

| 层次 | 方法 |
|---|---|
| 资源文件 | 解析 ICO 目录，核对七档与每帧合法性 |
| 母版 | 断言 780×780、外圈 3px 是浅色（主体没顶边） |
| 界面 | `window.windowIcon().availableSizes()` 含 16–256 七档 |
| exe | `LoadLibraryExW(AS_DATAFILE)` + 枚举 `RT_ICON`，实测 7 个 |
| 真实窗口 | 启动 exe，`WM_GETICON` 的 `ICON_SMALL` / `ICON_BIG` 均非 0 |

## 已知限制

- **系统图标缓存**：Windows 会把图标缓存进 `IconCache.db`，替换同名 exe 后
  资源管理器可能仍显示旧图。本项目产物名带版本号，正常情况下不会命中缓存；
- **小尺寸手工优化**：七档都由同一张母版缩放，没有针对 16px 做手工像素对齐。
  若将来要求 16px 绝对锐利，需要单独绘制一份 16px 版本并塞进 ICO。
