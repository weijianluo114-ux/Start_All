# 变更日志

版本号采用语义化版本。`v1.0.0` 是「从 exe 反汇编还原出的原始程序」，作为基线；
此后每完成一项需求递增次版本号（`v1.x.0`），修复缺陷递增修订号（`v1.x.y`）。

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
