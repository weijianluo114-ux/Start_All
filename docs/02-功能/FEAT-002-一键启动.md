# FEAT-002 · 一键启动

- **状态**：可用
- **首次版本**：v1.0.0（还原基线）
- **关联需求**：REQ-001（取消自动启动）
- **代码位置**：`launch_program()`、`LauncherWindow.launch_all()` / `_launch_worker()`

## 它做什么

按顺序启动当前预设里的全部条目；`.bat/.cmd` 会额外捕获其拉起的子进程，便于之后一并关闭。

## 入口

| 入口 | 结果 |
|---|---|
| 🚀 一键启动 | 后台线程顺序启动整个列表 |
| 双击某条目 | 只启动该项（`on_item_double_clicked`） |

> 注意：**启动器打开时不会自动启动任何东西**（REQ-001）。必须点击按钮。

## 行为细节

- **防重入**：`_launching` 为真时再次点击只弹提示，不重复启动。
- **空列表**：直接返回。
- **串行**：`_launch_worker` 逐个启动；`.bat/.cmd` 之间会 `sleep(2)` 等进程起来。
- **收尾**：`try/finally` 中 `QTimer.singleShot(0, _launch_finished)` 回主线程恢复按钮；若配置了全局宏且依赖齐全，还会自动回放宏。

## 启动策略（`launch_program`）

| 情况 | 做法 |
|---|---|
| **文件夹** | `os.startfile(目录)`（macOS/Linux 用 `open`/`xdg-open`）；返回 `None`，不产生待关闭进程 |
| `.exe` | `subprocess.Popen(resolved, cwd=临时目录)` |
| `.bat` / `.cmd` | `Popen(..., cwd=脚本所在目录, creationflags=CREATE_NEW_CONSOLE)`，避免子进程随启动器退出 |
| `.lnk` | 先经 `WScript.Shell` 解析真实目标，再按扩展名走上面两支 |
| 其他扩展名 + Windows | `WScript.Shell.Run(target,1,False)`，用 `ShellProc` 包装 PID；失败回退 `os.startfile` |
| macOS / Linux | `open` / `xdg-open` |

> 路径已失效（`⚠`）的条目在启动前被跳过，不会中断整批启动。详见 FEAT-005。

## 批处理的子进程捕获

`.bat/.cmd` 的直接子进程是 `cmd.exe`，真正的业务进程在它下面。做法是记录启动前后的 `tasklist` PID **差集**，
存进 `launched_items` 的第 4 个字段，供关闭时精确 `/pid` 终止。

## 已知限制

- 部分程序（如 Steam 中转的启动脚本）会派生"关不掉"的伴生进程，靠 `special_kill_map` 手工补刀。
- 并发线程只保证"不重复启动"，不保证启动顺序的时序精确。
