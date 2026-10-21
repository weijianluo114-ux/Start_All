# 变更日志

版本号采用语义化版本。`v1.0.0` 是「从 exe 反汇编还原出的原始程序」，作为基线；
此后每完成一项需求递增次版本号（`v1.x.0`），修复缺陷递增修订号（`v1.x.y`）。

## [1.15.0] - 2026-10-21

### Changed
- **换用最终品牌图标**（REQ-015 / FEAT-015 / T-019）：黑框 + SA + 黄色箭头
  - `assets/logo.png`：780×780 母版，由 1024×1024 源稿按主体包围盒裁剪，
    下沿 898 < 水印起点 930，**源稿右下角的「AI生成 WORKBUDDY」水印被整体裁掉**
  - `assets/logo.ico`：单文件七档（16/24/32/48/64/128/256），75,607 B；
    256 档为 PNG 压缩，其余为 32bpp BMP
  - 覆盖 exe 文件图标、窗口标题栏、任务栏、资源管理器、桌面快捷方式——
    三条路径（`--icon` / `_MEIPASS` 运行时 / 快捷方式）引用同一份 ico
- README 顶部加居中 logo，构建命令与测试清单同步到 v1.15.0

### Notes
- 图标本身沿用用户定稿，未重绘；七档均由同一张母版缩放，
  未做 16px 手工像素对齐（16px 下笔画有轻微抗锯齿，仍可辨认 SA 与箭头）
- Windows 的 `IconCache.db` 可能短暂显示旧图标；产物名带版本号，正常不会命中缓存

## [1.14.2] - 2026-10-21

### Fixed
- **批处理脚本的伴生进程会把无关程序算进去**（BUG-007 / T-018）：`.bat` / `.cmd` 之前用
  "启动前后全局 PID 差集 + 固定 2 秒"猜子进程，这两秒内用户手动打开的任何程序都会被记成
  脚本的伴生进程，点「关闭全部」时被强制结束。实测一次差集收进 7 个 PID，其中 5 个是系统噪声
  - 归属判据改为**父子链**：新增 `process_snapshot()`（WMI 取 `ParentProcessId` 等）与
    `descendants_of()`，只收父链可达脚本进程的 PID；同样场景只收 2 个（脚本真正启动的
    ping 与它的 conhost）
  - 关闭前用 `_spawn_still_same()` 核对 **镜像名 + 创建时间**，PID 被系统复用后不再闭眼 taskkill
  - 拿不到 cmd PID / 快照读取失败 / 缺 pywin32 时一律**不记录**（原来会退化成差集照用）
  - 新增 `PROTECTED_IMAGES` 黑名单：explorer 等外壳进程即使被误归也绝不结束
  - 代价：经 `explorer` 中转打开的程序（`start "" "某文档"`）父链断开，不再被关闭——
    按"宁可少关，不可错杀"取舍，已写进 BUG-007 的行为差异表
- 删除已无调用者的 `_get_all_pids()`，避免将来又有人拿它做差集

## [1.14.1] - 2026-10-21

### Fixed
- **点击「设置」后胶囊残留金色虚线**（BUG-006 / T-017）。焦点环的判据只有 `hasFocus()`，
  而鼠标点击同样会把焦点交给 `StrongFocus` 控件，于是"点过就一直挂着"。
  现在按 `event.reason()` 区分来源，只有 `Tab` / `Shift+Tab` / 快捷键导航才画环；
  鼠标点击、切回窗口、下拉关闭后回焦一律不画
- 虚线段（`Qt.DashLine` / `Qt.DotLine`）全部移除，改为 alpha 130 的实线细内环：
  键盘用户仍能定位焦点，但不再有刺眼的断续线
- 同一问题在设置面板里也修了：点过「开机自启动」开关（点线框）、
  拖过「字号」滑块（虚线框）之后都不再留框

## [1.14.0] - 2026-10-21

### Added
- **界面多语言**（REQ-014 / FEAT-014）：设置面板新增「界面语言」，
  支持 简体中文（默认）/ English / 日本語 / 繁體中文，切换即时生效并写入 `settings.language`
  - 文案层独立成 `src/lf_i18n.py`：`LANGUAGES` + `STRINGS`（117 条 × 4 语）+ `Lang` + `t()`
  - 回落链：当前语言 → 简体中文 → 键名；缺一条译文只露中文，不白屏、不抛错
  - 语言下拉用**原生写法**（English / 日本語），不随当前界面语言翻译
  - 覆盖主窗口、设置面板、全部提示框 / 确认框 / 文件选择框、列表类型提示；
    日志与预设名称不翻译（前者排障用，后者是用户数据）
  - 新增 `tests/test_step15_i18n.py`（四语言 × 11/17px 的几何、排法、持久化断言）
- **`ThemedCombo`**：自绘金色雪佛龙箭头。此前 QSS 清掉 `::drop-down` 边框后
  Qt 不再画系统箭头，下拉框看起来像普通输入框
- **README 英文说明**：顶部加语言切换指引，正文补一整节 English

### Changed
- **换语言不重建窗口**：`Lang.set()` 之后走 `retranslate_ui()` / `retranslate()`
  就地换文案并重算胶囊宽度与窗口最小尺寸——重建会丢 `launched_items` 里
  文件类条目的承载 PID，表现为"换完语言关不掉刚打开的文件"
- **圆盘文字按语言换排法**：中日文逐字竖排，英文横排整词
  （`START` 竖排要 5 个字高，必然顶出鱼身）；横排离中线留 `0.10R`，两词不在盘心贴成一行
- 设置面板的卡片改用 `QGridLayout`（标签 / 控件 / 数值三列），
  语言与字体两个下拉框左边缘严格对齐；说明与预览跨满三列，17px 下不再被挤窄裁字
- `SettingRow.sync_height()` 支持按真实可用宽度折行算行高（英文说明比中文长一截）

### Fixed
- 设置面板「字体搭配」下拉在英文下把文字顶到箭头位置（文案收短，并去掉冗余的"（默认）"后缀）
- 字体说明在 17px 下最后一行压在卡片边框上（跨列 + `heightForWidth` 未生效）

## [1.13.0] - 2026-10-21

### Fixed
- **圆盘文字跨过中间缝隙**（REQ-013 / FEAT-013）
  - 根因：文字框按"圆心偏移 + 固定宽度"摆放，而 S 形边界在 `y = cy` 处从
    `cx + 0.5R` 跳到 `cx - 0.5R`；17px 全局字号下第二个字必然压到另一条鱼身上
  - 改为按鱼身实际轮廓算可用区间：`_fish_span()` 对文字纵向区间取 9 条扫描线的交集，
    两字共用区间中线，左鱼整块在中线以上、右鱼在中线以下
  - 字号自适应：从目标字号逐档缩小，直到字盒四角都在鱼身内、离盘沿 ≥5px、且不压鱼眼

### Changed
- **圆盘放大**：160 → 184（控件 216×216），字不再贴着盘沿
- **盘面字体换成圆体幼圆**（`YouYuan`），缺字体退 MiSans → 界面字体；不跟随「字体搭配」
- **文字配色**：纯白改为暖金 `#FFD79A` + 深可可描边 `#5B2C00`，字芯做竖向渐变
- **悬停时文字也高亮**：字芯转亮到 `#FFF0C4`、描边转暖、8 向柔光淡入，只作用于被悬停的一半
- 布局按 (直径, 全局倍率, 字族) 缓存，悬停帧不再重算几何

### Added
- `tests/test_step14_taiji_text.py`（9 组断言：三档字号下的越界检测、配色、悬停像素变化）
- `docs/images/ui-taiji-v1.13.0.png`（常态 / 悬停启动 / 悬停关闭）

## [1.12.0] - 2026-10-21

### Added
- **全局字体设置**（REQ-012 / FEAT-012）
  - 设置面板新增「字体搭配」下拉与「字号」滑块，改动即时生效，无需重启
  - 5 套推荐搭配：雅黑 × 思源（默认）、雅黑经典、等线清朗、中英分排、书卷衬线；
    每套是「标题家族 + 正文字族」的候选链，只取本机已安装的，缺失时自动回退
  - 字号范围 11–17px（基准 13px），其余角色按同一倍率缩放；说明文字 10px 为硬下限
  - 偏好写入 `settings.font_key` / `settings.font_size`；坏值收敛到合法档位，不阻断启动
  - 新增 `SizeSlider`（自绘：刻度点 + 金色进度 + 悬停光晕）与 `CardFrame`（设置卡片容器）
  - 新增 `tests/test_step13_font_settings.py`（16 项，含 11/17px 两端几何断言）

### Changed
- **字体不再写死**：`set_ui_font()` 把基准 spec 记在控件上，`restyle_widgets()` 遍历重建，
  所以改字号不会重建窗口——`launched_items` 里的文件类条目 PID 得以保留
- `SettingRow` 高度由 `sync_height()` 按行数实算（13px 基准下仍是 90），
  设置面板改为「宽固定 420、高按内容算」，17px 下不再裁字
- 列表行高改为 `max(34, 字高 + 17)`；预设下拉的最小高度随字高
- 圆盘文字只跟随 0.94–1.16 倍字号：圆盘是插画，等比跟随会压到 S 形缝隙

### Fixed
- 类型图标里的 `!` 不再跟随全局字号（固定 9px），否则会顶出 18×18 的三角

## [1.11.0] - 2026-10-21

### Changed
- **字体层级重做**（REQ-011 / FEAT-011）
  - 新增 `Theme` 令牌（颜色 / 时长 / 动画开关）与 `ui_font()` 统一入口
  - 选定家族按"首选 → 回退"解析：标题优先 Noto Sans SC，正文用雅黑 UI，缺失时安全降级
  - 字重收敛到 400 / 600 / 700 三档；胶囊 15px → 13px 并加 0.3 字距，观感更紧致
- **所有悬停改为逐帧过渡**，不再是 QSS 瞬时切换
  - `PillButton` 改为 `QPainter` 自绘：悬停 110ms（底色/边框/内高光/底缘反光/文字色联动），
    按下 90ms（整体压暗 + 文字下沉 0.9px 模拟键程）
  - 程序列表改为 `ListRowDelegate` + `AnimatedList` 补间器：逐行悬停 ≈110ms 淡入、
    选中改为暖金底 + 左侧强调条；行高 34px、行块圆角 8px
  - 启停圆盘悬停 130ms：半圆外三圈发光淡入、鱼身按强度提亮，取代原来的瞬间高亮
  - 尊重系统「动画效果」开关（`SPI_GETCLIENTAREAANIMATION`），关闭后时长压到 1ms
- **列表类型改为矢量图形**：文件夹 / 可执行 / 普通文件 / 失效 各画 18×18 图形，
  不再依赖 `📁` / `⚠` emoji 的彩色渲染；`entry_label()` 文本保持不变以兼容配置与测试

### Added
- `tests/test_step12_typography_motion.py`（16 项：字体解析、时长区间、补间过程、像素差、类型分类）
- `docs/images/hover-states.png`：胶囊三态、列表悬停/选中、圆盘悬停对比图

## [1.10.0] - 2026-10-21

### Added
- **设置面板 + 开机自启动**（REQ-010 / FEAT-010）
  - 「设置」胶囊不再弹"尚未实现"，打开 400×224 的实际面板；改动即时生效，无保存按钮
  - 新增 `ToggleSwitch`（52×28，纯 `QPainter`）与 `SettingRow`（90 高卡片，**整行可点**）
  - 悬停反馈四处联动：底色提亮、边框转金加粗、左侧状态竖条加长、开关出现发光环
  - 写注册表 `HKCU\...\CurrentVersion\Run`，只需当前用户权限，不触发 UAC
  - `heal_autostart_path()`：升级后旧 exe 被清理时，自启动项自动改写到当前版本
  - 写入失败会回滚开关并说明原因，不留下"看起来开了其实没开"的状态
  - 新增 `tests/test_step11_settings_autostart.py`（18 项，全程使用注册表沙箱键）

### Changed
- `open_settings()` 从占位提示改为打开 `SettingsDialog`
- `tests/test_step9_pill_layout.py` 第 7 项按新语义改写：点设置应打开面板且不改配置

## [1.9.1] - 2026-10-20

### Fixed
- **文档类条目（.drawio / .md / .docx …）关不掉**（BUG-005）
  - 根因一：启动走 `WScript.Shell.Run`，实测它对"文件关联"返回 **0**，拿不到 PID，
    启动记录里没有这一项（日志：`启动完成但未取得 PID`）
  - 根因二：`_close_targets()` 只对 `.exe/.com` 生成镜像名，文档条目一律 `None`，
    于是被判为"脚本类且非本次启动，无法判定"直接跳过
  - 修法：打开改用 `ShellExecuteExW`（`SEE_MASK_NOCLOSEPROCESS`）取真实 PID；
    关闭时新增两层——**命令行含文件路径的精确匹配**（`draw.io.exe "…\x.drawio"`），
    以及**文件关联解析出的宿主程序名**兜底（`AssocQueryString`）
  - 精确命中时不再按镜像名兜底，避免"关一个文件却关掉该程序所有窗口"
  - 统计口径同步修正：精确关闭成功的条目直接算成功，不再拿关联程序名复核
    （否则 `.py` 的关联程序 `Code.exe` 还在运行，会被误报为"关闭失败"）
  - 过滤系统兜底宿主（`OpenWith.exe` / `ApplicationFrameHost.exe` 等），
    否则未知扩展名会被当成"有关联程序"
  - 新增 `tests/test_step10_document_entries.py`

## [1.9.0] - 2026-10-20

### Changed
- **UI 重排：六项操作移到圆的左右两侧**（REQ-008 / FEAT-009）
  - 新增 `PillButton`（象牙白 + 灰金胶囊，宽度按字数算出：2 字 86px、4 字 96px、5 字 111px）
    与 `PillColumn`（绝对定位，三枚中心距 66px，中间那枚与圆心严格齐平）
  - 左列：添加文件夹 / **添加程序** / 输入路径；右列：删除选中 / 日志 / 设置
  - 长条靠圆的上下两端，短条靠近中间；左列右缘贴圆、右列左缘贴圆
  - 预设行「新建 / 删除」改用同款小号胶囊，避免风格割裂
  - 面板改暖白 `#EDE7DB`，与象牙白胶囊、纯白列表形成三层明度
  - 圆盘配色按要求调整：绿色更浅（`#4CC38A`），红色改为鲜血红（`#C1121F`）
- 窗口 520×680 → 560×700，为"侧列 + 圆 + 侧列"让出宽度
- **胶囊边框、对齐与内外圆角修正**（REQ-009）
  - 去掉上沿白色描边（`border-top-color`），四边统一 `#BEAD86`
  - 左列改为左边缘对齐、右列改为右边缘对齐（原先是朝圆一侧对齐，导致外侧参差）
  - 宽度改为成对给定：上/下排 111px、中排 96px，左右逐排等长、上下镜像
  - 四角独立设置：朝外一侧 8px 小圆角、朝圆一侧 19px 大圆角，左右反向，形成内外呼应

### Added
- **「设置」占位入口**：按需求只留按钮与调用路径，点击提示"尚未实现"，不改任何配置
- `tests/test_step9_pill_layout.py`：宽度递增、三枚对齐、贴圆不重叠、设置无副作用、宏已封存

### Removed
- **全局鼠标宏整体封存**（REQ-007）
  - 界面三个按钮（录制 / 播放 / 清除）全部下线，启动后不再自动回放
  - 实现搬到 `src/legacy/macro_feature.py`；主程序不 import，PyInstaller 不会收集
  - `requirements.txt` 移除 `pynput`，`global_macro` 配置字段移除（旧配置仍可正常加载）

## [1.8.0] - 2026-10-20

### Added
- **顶部太极式启动 / 关闭控件**（REQ-006 / FEAT-008）
  - 新增 `TaijiLaunchButton`：按太极图几何构造绘制两条鱼（S 形分割），左绿=一键启动、右红=关闭全部
  - 两条鱼之间用 `QPainterPathStroker` 真实切出 4 px 缝隙，缝内**只透面板底色**（不加投影，
    避免出现一道发黑的深沟）；点缝隙/圆外均不响应
  - 鱼眼：左鱼嵌红点、右鱼嵌绿点；文字「启动」「关闭」逐字**竖排**，不做旋转
  - 凹凸感：对角渐变 + 顶部高光 + 底部内阴影 + **沿轮廓的对角渐变浮雕描边** + 外圈包边 + 多层落影
  - **盘心发光**：两条鱼各自叠一层「自身颜色提亮版」的径向渐变 + 一层跨缝白色柔光，
    中心亮、向外衰减，做出「光从圆盘内部透出」的观感（不用叠纯白，避免绿色被冲成灰绿）
  - 交互细节：按下后拖出鱼身松开不触发、悬停高亮、启动中绿鱼置灰（文字转深灰）而红鱼保持可用
  - 圆盘单独占据顶部一行并居中，不再与添加/宏等功能按钮混排；直径 160 px

### Changed
- 移除原「🚀 一键启动」「⏹ 关闭全部」两个按钮，功能并入顶部圆盘（确认流程与关闭范围不变）
- 默认窗口尺寸 500×500 → 520×680，给圆盘留出呼吸空间
- 新增 `tests/test_step8_taiji_button.py`；README 主截图替换为新版界面

### Changed（构建）
- 新增 `scripts/clean_artifacts.py`：清理非当前版本的 exe 与 `build/`、`dist/`、`*.spec`，
  **保证仓库根只保留一个可用的 exe**；被运行时占用会明确报错退出，不再静默失败
- `scripts/build.bat` 构建后改为调用该脚本（原批处理 `del` 在被占用时静默失败，
  v1.7.0 发布后因此残留了 `LaunchForge_v1.6.1.exe`）
- 反汇编依据的原始程序移出仓库：`reference/一键多启_original_v1.0.0.exe` → 分析工作区
  `LaunchForge_Reverse\original\`（保留证据，但仓库目录不再有任何历史 exe）

### Fixed
- **Release 正文只剩一行 `Full Changelog`**（BUG-004）
  - `append_body` 是布尔开关，不承载正文；改为 `Prepare release body` 步骤生成
    `release_body.md`，再由 `body_path` 提供给发布动作
  - 顺带修掉两个语法坑：YAML 块标量里 here-string 结束符被缩进、正文中的中文引号
    被当作字符串定界符

### Changed（工程化，不改行为）
- 仓库按主流布局重组：`src/` 放源码、`assets/` 放图标、`scripts/` 放构建脚本、
  `docs/` 放文档、版本级日志提到根 `CHANGELOG.md`
- 新增 `.gitignore` / `.gitattributes` / `LICENSE`（MIT）/ 英文 README 徽章
- 新增 `.github/workflows/build.yml`：推送 `v*` 标签自动在 Windows 上构建并创建 Release
  - 发布资产统一为 `LaunchForge_vX.Y.Z.exe`（ASCII）；GitHub Actions 会丢失非 ASCII 文件名字符
  - Release 正文追加「下载与使用」固定说明块
- `scripts/build.bat` 改为从 `APP_VERSION` 读版本号，产物同时落到 `dist/` 与仓库根
- 构建后自动重建桌面快捷方式（`scripts/update_shortcut.py`）并清理旧版本 exe：
  `.lnk` 存的是绝对路径，版本号一变就会失效，此前需要手工改
- 本地产物改用 ASCII 名 `LaunchForge_vX.Y.Z.exe`（与 Release 资产一致），
  避免 `.bat` 在非 UTF-8 代码页下的解析问题
- 清理历史 exe 与 `.spec`：仓库根只保留当前可用版本，原始程序移入 `reference/`（已 gitignore）

---

## [1.7.0] - 2026-10-20

### Added
- **「关闭全部」同时关闭列表内文件夹对应的资源管理器窗口**（REQ-005 / FEAT-007）
  - `list_explorer_windows()`：用 `Shell.Application.Windows()` 枚举窗口，同一窗口的多个标签
    合并为一条记录（各带自己的路径）
  - `_folder_window_plan()`：按路径把列表条目对应到窗口，分为"可整窗关闭"与"混有列表外标签"
  - `_close_folder_window()`：按标签数循环发送 `WM_CLOSE` 并逐次复查，失败即停并记日志
  - `_window_label()`：生成「Alpha、Bravo（2 个标签）」这类可读标识
- 混有列表外标签的窗口：**单独询问**——同意则整窗关闭，不同意则跳过这些窗口、其余照常关闭

### Changed
- 按钮「⏹ 关闭所有程序」→「⏹ 关闭全部」，确认框分区列出"程序 N 个 / 文件夹窗口 M 个"
- 结果汇总拆分为两段：`已关闭 N 个程序` / `已关闭 M 个文件夹窗口`
- 关闭文件夹窗口不用 `Quit()`：实测多标签窗口下 `Quit()` 无效，`WM_CLOSE` 才是关标签的正确动作

### Notes
- **不记录打开时的 HWND**：用户把窗口拖进另一窗口合并成标签后原 HWND 消失，
  改为关闭时现场枚举、按路径判定（详见 `docs/04-问题/Q-003`）
- 不结束 `explorer.exe`，只关窗口；任务栏与其他窗口不受影响
- 测试：新增 `tests/test_step7_close_folders.py`；`test_step3_folders.py` 第 9 项按新语义更新

---

## [1.6.1] - 2026-10-20

### Fixed
- **关闭程序时连续闪现控制台黑框**（BUG-003）
  - 新增 `hidden_subprocess_kwargs()`：`CREATE_NO_WINDOW` + `STARTUPINFO(SW_HIDE)`
  - 应用于 `ShellProc.kill` / `_get_all_pids` / `_get_process_map` / `_taskkill` / `_pid_info` 共 5 处
  - 两处 `shell=True` 改为参数列表，不再额外拉起 `cmd.exe`
- 验收：`tests/test_step6_no_console_flash.py`（pythonw 宿主下对照组 +2 个控制台窗口、实验组 +0）

---

## [1.6.0] - 2026-10-19

### Removed（回退）
- **移除 v1.5.0 的自建多标签文件夹窗口**（REQ-004 回退，见 Q-002）
  - 删除 `FolderTab`、`FolderTabsWindow`、`LauncherWindow.folders_requested` 信号、
    `open_folders_in_tabs()`、`_on_folder_window_destroyed()`、`self._folder_window`
  - 清理不再使用的导入：`QTabWidget`、`QTreeView`、`QFileSystemModel`、`QLineEdit`、
    `QHeaderView`、`pyqtSignal`
  - 源码行数 1583 → 1320

### Changed
- 预设中的**每个文件夹**恢复由系统资源管理器打开（一次启动 N 个文件夹 = N 个资源管理器窗口）
- `_launch_worker()`：程序启动完成后逐个调用 `launch_program(folder)`，不再分流到自建窗口

### 原因
用户在 REQ-004 中明确要求"只需要在资源管理器中打开，不要新建窗口"。
经三项实测确认资源管理器无法通过命令行/COM/Shell 动词接收"在已有窗口开新标签"
（详见 `04-问题/Q-002`），因此自建窗口方案整体作废并回退。

### 验证
- `tests/test_step3_folders.py` 第 8 项断言改为「文件夹必须经 `launch_program` 打开」，
  并断言 `_folder_window` 不再存在
- 打包产物端到端验证：预设两个文件夹 → 点击「🚀 一键启动」→
  `EXPLORER_TEST_WINDOWS=2`（两个资源管理器窗口）、`OWN_FOLDER_WINDOWS=0`（无自建窗口）

---

## [1.5.0] - 2026-10-19

### Added
- **多标签文件夹窗口**（REQ-004）：一次启动中的多个文件夹合并到**一个窗口**的多个标签页，
  不再逐个弹出资源管理器窗口
  - 标签可关闭、可拖动排序；每个标签可进入子目录、后退、上级、地址栏跳转
  - 每个标签提供「资源管理器」按钮，窗口底部提供「全部用资源管理器打开」
  - 已存在窗口时追加标签而不是新建窗口；重复目录不重复添加
- `FolderTab` / `FolderTabsWindow`；`LauncherWindow.folders_requested` 信号（后台线程 → 主线程）

### Changed
- `_launch_worker()` 不再逐个打开文件夹：先收集，程序启动完成后统一处理
  - 1 个文件夹仍由系统资源管理器打开（原生体验不变）
  - ≥2 个文件夹交给多标签窗口

### Notes
- 实现中发现：`QFileSystemModel` 未调用 `setRootPath()` 时不会扫描目录（`rowCount` 恒为 0），
  因此每个标签使用独立模型并在每次导航时重设根目录；验收测试已加入"可见条目数"断言。

---

## [1.4.1] - 2026-10-19

### Fixed
- **BUG-002：部分程序「能打开、关不掉」**（`dsh-tauri-app.exe`、`WorkBuddy.exe`）
  - 根因：单实例应用重复启动时新进程立即退出，启动记录中的 PID 已失效；
    旧实现 `elif image` 使镜像名关闭成为互斥分支，导致永远走不到兜底
  - 修复：镜像名关闭改为**无条件执行**；运行状态判定改为 `_pid_info()`（PID 存活且镜像匹配）

### Added
- 文件日志：`%LOCALAPPDATA%\MultiLauncher\logs\launcher.log`，1 MB 轮转保留 3 份
  - 记录启动结果（PID / 解析路径）、关闭判定与跳过理由、每条 `taskkill` 的命令/退出码/原始输出
  - 未捕获异常与线程异常一并入库
- 「🗒 日志」按钮，直接打开日志目录
- 权限不足识别与「以管理员身份重试」（`ShellExecuteW runas`，一次 UAC）
- 关闭后轮询复查（≤3 秒），避免多进程应用退出滞后被误判为失败

### Changed
- 结果框改为列出「程序名 —— 失败原因」并附日志路径
- 判定「路径已不存在」的条目单独给出跳过理由（原归入"脚本类"）

---

## [1.4.0] - 2026-10-19

### Added
- **文件夹条目**（REQ-003）：列表可加入文件夹，一键启动时由资源管理器打开；拖拽、目录选择、手动输入三种方式均可
- 「📁 添加文件夹」与「✏ 输入路径」两个按钮；按钮区改为两行（添加 / 删除 / 启动 / 关闭）
- `settings.last_folder`：记住上次使用的文件夹，供选择框定位与手动输入默认值
- `normalize_input_path()`：去引号、展开 `%VAR%` 与 `~`、统一分隔符
- `entry_kind()` / `entry_label()` / `entry_tooltip()`：文件夹显示 `📁`，失效路径显示 `⚠`
- 失效路径不再在加载时被静默丢弃，避免预设被下一次保存永久清空

### Changed
- `launch_program()` 增加目录分支：Windows 用 `os.startfile`，macOS/Linux 用 `open`/`xdg-open`
- `dropEvent()` 接收范围由 `os.path.isfile` 放宽为 `os.path.exists`
- `add_to_list()` 去重改为按 `normcase(normpath())` 比较，并返回是否新增成功
- 「关闭所有程序」先剔除文件夹条目；列表只有文件夹时直接提示，不进入确认流程
- 「添加程序」对话框标题与过滤器改为「程序或文件」，起始目录为上次使用的文件夹

---

## [1.3.0] - 2026-10-19

### Changed
- 「⏹ 关闭所有程序」改为**先确认 → 检测运行状态 → 未运行跳过 → 结果汇总**（REQ-002）
- 关闭范围从"本次会话启动的进程"扩大到"列表内全部正在运行的程序"
- `terminate_all_and_exit()` 重命名为 `close_all_programs()`；**关闭后不再退出启动器**

### Added
- `_get_process_map()`：解析 `tasklist /fo csv /nh` 得到"镜像名 → PID 集合"（用 `csv` 而非 `split(',')`，兼容带逗号的路径）
- `_close_targets()` / `_find_launched()` / `_kill_target()` / `_taskkill()`：关闭流程拆分，便于单独测试
- 关闭后的二次校验与失败清单；未运行时直接提示"无需关闭"
- 确认框默认按钮为「否」，正文列出将被关闭的程序名

### Known Issues
- `.bat/.cmd` 条目若不是本次启动的，无法按镜像名判定，会被跳过（见 Q-001）

---

## [1.2.0] - 2026-10-19

### Removed
- 「打开即启动」整条通路（REQ-001）：
  - `__init__` 末尾的 `QTimer.singleShot(300, self.auto_launch_last_preset)`
  - 「设置」菜单与 `QAction('启动程序自动启动列表应用')`
  - 方法 `toggle_auto_launch()`、`auto_launch_last_preset()`
  - 配置字段 `settings.auto_launch`（**旧配置中的该字段一律忽略**）
  - 已无引用的 `QAction` 导入

### Changed
- `settings` 容器保留为空对象 `{}`，预留给界面偏好（如"上次浏览的文件夹"）

---

## [1.0.0] - 2026-10-19

### Added
- 从 `一键多启.exe` 还原的完整源码 `launchforge.py`（769 行 / 49 个 code object / 指令级 100% 等价）
- 逆向工具链：CArchive 解包、PYZ 解析、反汇编清单、字节码等价校验、行号对齐、冒烟测试
- 构建脚本 `build.bat`、`requirements.txt`、`version.txt`、`logo.ico`

### Notes
- 本版本行为与原始 exe 完全一致，作为后续改动的对照基线（`baseline/launchforge.py`）
