# -*- coding: utf-8 -*-
"""
需求 2 验收测试：关闭列表内所有正在运行的程序（先确认、检测运行状态、未运行跳过、不退出启动器）。

做法：把系统 ping.exe 复制成两个唯一名字的副本
  · lf_probe_alive.exe —— 真实启动并常驻（ping -t）
  · lf_probe_idle.exe  —— 只加入列表，不启动
再用假 QMessageBox 控制「取消 / 确认」，观察进程是否被真正关闭。
"""
import os
import shutil
import subprocess
import sys
import time

BASE = os.path.dirname(os.path.abspath(__file__))
SANDBOX = os.path.join(BASE, "_t2_appdata")
WORK = os.path.join(BASE, "_t2_bin")
ALIVE = os.path.join(WORK, "lf_probe_alive.exe")
IDLE = os.path.join(WORK, "lf_probe_idle.exe")

os.makedirs(SANDBOX, exist_ok=True)
os.makedirs(WORK, exist_ok=True)
os.environ["LOCALAPPDATA"] = SANDBOX
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

def _find_src():
    """兼容多种位置：项目 src/、分析工作区 src/，以及旧的平铺目录。"""
    root = os.path.dirname(BASE)
    for cand in (os.path.join(root, "src"), os.path.join(BASE, "src"),
                 root, BASE, os.path.dirname(root)):
        if os.path.isfile(os.path.join(cand, "launchforge.py")):
            return cand
    return os.path.join(root, "src")


sys.path.insert(0, os.environ.get("LF_SRC", _find_src()))

from PyQt5.QtWidgets import QApplication  # noqa: E402

import launchforge  # noqa: E402


class FakeMessageBox:
    """记录弹窗内容，并按预设答案返回。"""
    Yes = 1
    No = 0
    Accepted = 1
    calls = []
    answer = Yes

    @classmethod
    def question(cls, parent, title, text, buttons=None, default=None):
        cls.calls.append(("question", title, text))
        return cls.answer

    @classmethod
    def information(cls, parent, title, text):
        cls.calls.append(("information", title, text))
        return cls.Yes

    @classmethod
    def warning(cls, parent, title, text):
        cls.calls.append(("warning", title, text))
        return cls.Yes


launchforge.QMessageBox = FakeMessageBox

# 准备探针
src_ping = os.path.join(os.environ.get("SystemRoot", r"C:\Windows"), "System32", "ping.exe")
for p in (ALIVE, IDLE):
    if not os.path.exists(p):
        shutil.copy2(src_ping, p)

app = QApplication(sys.argv)
win = launchforge.LauncherWindow()
win.add_to_list(ALIVE)
win.add_to_list(IDLE)

# 启动 alive 探针
proc = subprocess.Popen([ALIVE, "-t", "127.0.0.1"],
                        stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                        creationflags=0x08000000)  # CREATE_NO_WINDOW
time.sleep(1.2)
print("[1] 探针已启动，PID=%d，存活=%s" % (proc.pid, proc.poll() is None))
assert proc.poll() is None

# 记录是否被 close()（用于验证"关闭后启动器不退出"）
closed = {"flag": False}
_orig_close = win.close


def _spy_close():
    closed["flag"] = True
    return _orig_close()


win.close = _spy_close

# ---------- 场景 A：用户在确认框点「否」 ----------
FakeMessageBox.calls.clear()
FakeMessageBox.answer = FakeMessageBox.No
win.close_all_programs()
time.sleep(0.5)
q = [c for c in FakeMessageBox.calls if c[0] == "question"]
print("[2] 取消场景：是否弹出确认 = %s，进程仍存活 = %s" % (bool(q), proc.poll() is None))
assert q, "未弹出确认对话框"
print("    确认框正文摘要：%r" % q[0][2].splitlines()[0])
assert "正在运行" in q[0][2]
assert proc.poll() is None, "点否之后进程仍被杀了！"

# ---------- 场景 B：用户点「是」 ----------
FakeMessageBox.calls.clear()
FakeMessageBox.answer = FakeMessageBox.Yes
win.close_all_programs()

deadline = time.time() + 6
while time.time() < deadline and proc.poll() is None:
    app.processEvents()
    time.sleep(0.1)

info = [c for c in FakeMessageBox.calls if c[0] == "information"]
print("[3] 确认场景：进程存活 = %s（应为 False）" % (proc.poll() is None))
assert proc.poll() is not None, "确认后进程未被关闭！"
print("    结果提示：%r" % (info[-1][2] if info else ""))
assert "已关闭" in (info[-1][2] if info else "")

print("[4] 启动器是否被关闭 = %s（应为 False）" % closed["flag"])
assert not closed["flag"], "关闭后不应退出启动器"

# ---------- 场景 C：列表内程序都没运行 ----------
FakeMessageBox.calls.clear()
FakeMessageBox.answer = FakeMessageBox.Yes
win.close_all_programs()
titles = [c[1] for c in FakeMessageBox.calls]
print("[5] 全部未运行：弹窗标题 = %s（应无确认框）" % titles)
assert "无需关闭" in titles, "应提示无需关闭"
assert "确认关闭" not in titles, "没有运行的程序时不该再弹确认框"

print("\n需求 2 验收通过：先确认、检测运行状态、跳过未运行、关闭后不退出。")
