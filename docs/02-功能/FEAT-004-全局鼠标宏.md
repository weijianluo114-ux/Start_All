# FEAT-004 · 全局鼠标宏

- **状态**：**已封存（v1.9.0）** —— 界面上已无入口，源码保留但不参与编译与打包
- **首次版本**：v1.0.0（还原基线）
- **封存版本**：v1.9.0（原因与恢复步骤见 `REQ-007`）
- **关联**：`src/legacy/macro_feature.py` 中的 `MacroRecorderDialog` / `play_macro`

> **本文档自 v1.9.0 起转为历史参考。**
> 宏的完整实现已搬到 `src/legacy/macro_feature.py`，主程序不再 import，
> 因此既不显示入口也不打进 exe。下文描述的是封存前的行为，
> 恢复该功能时按模块文档字符串里的三步接回即可。

## 它做什么

录制一段鼠标/键盘操作（移动、点击、滚轮），存进配置；之后可手动回放，或在「一键启动」完成后自动回放，
用于给刚启动的程序做固定的初始点击。

## 入口

| 入口 | 结果 |
|---|---|
| 🎬 录制总宏 | 打开录制对话框，ESC 或「停止录制」结束 |
| ▶ 播放总宏 | 新线程中回放已录制的宏 |
| 🗑 清除总宏 | 二次确认后清空 |

## 事件格式

```json
{"type": "move",   "x": 100, "y": 200, "time": 0.42}
{"type": "click",  "x": 100, "y": 200, "button": "left", "pressed": true, "time": 0.51}
{"type": "scroll", "x": 100, "y": 200, "dx": 0, "dy": -1, "time": 0.63}
```

`time` 为相对录制起点的秒数（`time.perf_counter()` 差值）。

## 实现要点

- **录制**：`pynput` 的 `Listener` 采集；独立 `KeyboardListener` 监听 ESC 停止；`threading.Event` 作停止标志。
- **回放**：`_play_macro` 遍历事件，`delta = t - last_time` 决定 `sleep`，用 `MouseController` 复现。
- **自动回放**：`_launch_worker` 在启动完成后，若 `global_macro` 非空且 `HAS_PYNPUT and HAS_WIN32GUI`，
  `QTimer.singleShot(0, _auto_play_global_macro)` 回到主线程再起线程回放（`sleep(2)` 给程序留启动时间）。

## 已知限制

- 依赖 `pynput`；缺失时按钮只弹提示，不崩溃（`HAS_PYNPUT` 降级）。
- 回放是**绝对屏幕坐标**，分辨率或多屏布局变化后可能点偏。
- 播放期间没有"中断"入口，长宏需要等它跑完。
- 宏是**全局唯一**一份，不区分预设（与原版一致，未改动）。
