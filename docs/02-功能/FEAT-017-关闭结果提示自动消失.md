# FEAT-017 · 关闭结果提示自动消失

- **状态**：可用（v1.16.0）
- **范围**：`close_all_programs` 的收尾提示；新增 `AutoCloseNotice` 控件
- **关联**：REQ-017、FEAT-003、T-021

![关闭结果轻提示](close-notice-v1.16.0.png)

## 外观

- 卡片四周留 **16px 透明空隙**（`AutoCloseNotice.GAP`），圆角与描边不会被窗口边界切掉；
- 卡片本体：米白竖向渐变（`#FFFDF9 → #F6EFE0`）+ 12px 圆角 + 1.5px 渐变描边
  （左上暖金 `#F3D89C` → 浅棕 `#CCB388` → 右下回金 `#F0CA80`）；
- 卡片外 3px 处一圈**渐变细环**（暖金，alpha 72–130），形成明确的"外框"边界；
- 环外再叠三层由内向外变淡的金色柔光（`alpha 50/30/18`，上亮下淡），
  在深色背景上也不发脏。
- 不用 `QGraphicsDropShadowEffect`：它在中文渲染上会发虚（v1.9.0 起弃用），
  柔光全部自绘，尺寸与透明度可控。

## 行为

| 场景 | 提示方式 |
|---|---|
| 全部关闭成功（程序 + 文件夹窗口） | 米白圆角轻提示，正文 + 「N 秒后自动关闭」，**无按钮**，5 秒后自己消失；点一下可立即关掉；非模态，主界面全程可用 |
| 有失败项 | 原样的 `QMessageBox.information`（带 OK），列出失败项与原因、日志路径——需要用户看到并处理 |
| 没有可关的内容 | 维持原「无需关闭」提示（不受本改动影响） |

## 实现要点

- `NoticeCard(QWidget)`：自绘卡片（渐变底 / 渐变描边 / 3px 外环 / 三层柔光），
  与 `CardFrame` 同族但带外框，供提示专用；
- `AutoCloseNotice(QDialog)`（`src/launchforge.py`）：
  `FramelessWindowHint | Tool | WindowStaysOnTopHint` + 半透明背景，
  内部放一张 `CardFrame`（与设置面板同族的米白渐变圆角卡片）；
  `QTimer` 每秒递减并刷新文案，到 0 `close()`；`WA_DeleteOnClose` 自清理，
  `LauncherWindow._close_notice` 持引用防 GC。
- **为什么不是 `QMessageBox`**：即便构造传 `NoButton`，Qt 在 `exec_()` 阶段仍会
  自动补一个 OK 按钮（e2e 实测抓到过），"不用点"就落空了。
- 文案键：`close.auto_close_hint`（四语）；常量 `CLOSE_NOTICE_SECONDS = 5`。
- 提示居中于主窗口；倒计时只换文字不重新 `adjustSize()`，窗口不会随秒数抖动。

## 已知限制

- 失败分支的真实进程验证成本高（需要造一个拒绝被结束的进程），
  由脚本级 `test_step20_close_notice.py` 用 mock 覆盖；成功分支有真实进程端到端。
- 提示是置顶的 Tool 窗口，5 秒内会浮在其它应用上方（保证可见性，属预期）。
