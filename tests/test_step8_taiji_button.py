# -*- coding: utf-8 -*-
"""
需求 6 验收测试：太极式启动/关闭控件（TaijiLaunchButton）。

覆盖：
  1. 几何：圆内左右两半分别命中 run / close，圆外不命中
  2. 点击左半 → 发出 run_requested；点击右半 → 发出 close_requested
  3. 左半禁用（启动中）时点击不发出信号，右半仍可用
  4. 按下后移到圆外松开 → 不触发（防止拖拽误触）
  5. 悬停状态随鼠标移动切换，离开后清空
  6. 主窗口接线：clicked 信号确实连到 launch_all / close_all_programs

offscreen 平台在本机不渲染文字，但绘制与命理逻辑不依赖字形，可正常验证。
"""
import os
import shutil
import sys

BASE = os.path.dirname(os.path.abspath(__file__))
SANDBOX = os.path.join(BASE, "_t8_appdata")

shutil.rmtree(SANDBOX, ignore_errors=True)
os.makedirs(SANDBOX, exist_ok=True)
os.environ["LOCALAPPDATA"] = SANDBOX
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")


def _find_src():
    root = os.path.dirname(BASE)
    for cand in (os.path.join(root, "src"), os.path.join(BASE, "src"),
                 root, BASE, os.path.dirname(root)):
        if os.path.isfile(os.path.join(cand, "launchforge.py")):
            return cand
    return os.path.join(root, "src")


sys.path.insert(0, os.environ.get("LF_SRC", _find_src()))

from PyQt5.QtCore import QPoint, Qt  # noqa: E402
from PyQt5.QtTest import QTest  # noqa: E402
from PyQt5.QtWidgets import QApplication  # noqa: E402

import launchforge  # noqa: E402

app = QApplication(sys.argv)

btn = launchforge.TaijiLaunchButton(132)
btn.show()
app.processEvents()

events = []
btn.run_requested.connect(lambda: events.append("run"))
btn.close_requested.connect(lambda: events.append("close"))

D = 132
M = btn._margin
CENTER = QPoint(M + D // 2, M + D // 2)
LEFT = QPoint(M + int(D * 0.25), M + D // 2)     # 左半圆中部
RIGHT = QPoint(M + int(D * 0.75), M + D // 2)    # 右半圆中部
OUTSIDE = QPoint(1, 1)

print("[0] 控件尺寸 = %dx%d，半径=%d，圆心=%s"
      % (btn.width(), btn.height(), D // 2, (CENTER.x(), CENTER.y())))

# ---------- 1. 命中判定 ----------
assert btn._side_at(LEFT) == "run"
assert btn._side_at(RIGHT) == "close"
assert btn._side_at(OUTSIDE) is None
assert btn._side_at(QPoint(CENTER.x(), M - 2)) is None, "圆外上方不应命中"
print("[1] 命中判定：左=%s 右=%s 圆外=%s"
      % (btn._side_at(LEFT), btn._side_at(RIGHT), btn._side_at(OUTSIDE)))

# ---------- 2. 点击左右两半 ----------
QTest.mouseClick(btn, Qt.LeftButton, pos=LEFT)
QTest.mouseClick(btn, Qt.LeftButton, pos=RIGHT)
print("[2] 点击左右半 → %s" % events)
assert events == ["run", "close"], "左右半未分别触发"

# ---------- 3. 左半禁用 ----------
events.clear()
btn.set_run_enabled(False)
QTest.mouseClick(btn, Qt.LeftButton, pos=LEFT)
print("[3] 左半禁用后点击左侧 → %s（应为空）" % events)
assert events == [], "禁用状态仍触发了启动"

QTest.mouseClick(btn, Qt.LeftButton, pos=RIGHT)
assert events == ["close"], "右半不应受左半禁用影响"
btn.set_run_enabled(True)
print("    解除禁用后右半仍可用 = True")

# ---------- 4. 按下后移出再松开 ----------
events.clear()
QTest.mousePress(btn, Qt.LeftButton, pos=LEFT)
QTest.mouseRelease(btn, Qt.LeftButton, pos=OUTSIDE)
print("[4] 左按下→圆外松开 → %s（应为空）" % events)
assert events == [], "拖拽到圆外松开仍然触发了"

# ---------- 5. 悬停 ----------
QTest.mouseMove(btn, LEFT)
assert btn._hover == "run", "悬停左半未生效"
QTest.mouseMove(btn, RIGHT)
assert btn._hover == "close"
QTest.mouseMove(btn, OUTSIDE)
assert btn._hover is None, "移出圆外后悬停未清空"
print("[5] 悬停状态切换正常，移出后清空")

# ---------- 6. 主窗口接线 ----------
# 先销毁独立的测试控件：offscreen 平台下同时存在两个顶层窗口时，
# 二次 show + processEvents 会崩溃（Qt offscreen 的已知不稳定点），与本控件逻辑无关。
btn.close()
btn.deleteLater()
app.processEvents()

# 在构造窗口前替换槽函数，才能验证 __init__ 里的 connect 确实指向这两个方法
calls = []
orig_launch = launchforge.LauncherWindow.launch_all
orig_close = launchforge.LauncherWindow.close_all_programs
launchforge.LauncherWindow.launch_all = lambda self: calls.append("launch")
launchforge.LauncherWindow.close_all_programs = lambda self: calls.append("close")
try:
    win = launchforge.LauncherWindow()
    win.show()
    app.processEvents()
    win.taiji.run_requested.emit()
    win.taiji.close_requested.emit()
finally:
    launchforge.LauncherWindow.launch_all = orig_launch
    launchforge.LauncherWindow.close_all_programs = orig_close

print("[6] 主窗口信号接线 → %s" % calls)
assert calls == ["launch", "close"], "信号未接到 launch_all / close_all_programs"

# 启动中禁用、结束后恢复
win.taiji.set_run_enabled(False)
assert not win.taiji.is_run_enabled()
win.taiji.set_run_enabled(True)
assert win.taiji.is_run_enabled()
print("[7] set_run_enabled 开关正常")

# 日志句柄仍占用目录，删除失败不影响结论
try:/n    shutil.rmtree(SANDBOX, ignore_errors=True)
except Exception:/n    pass
print("\n需求 6 验收通过：太极控件左右半独立响应，禁用与误触保护生效。")
