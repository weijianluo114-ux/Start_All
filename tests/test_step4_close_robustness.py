# -*- coding: utf-8 -*-
"""
需求 4 验收测试：关闭流程的健壮性（日志 + 镜像名兜底）。

复现用户报告的场景：程序已经开着，再从启动器点「一键启动」，
新进程把请求转交给已有实例后立刻退出（Electron / Tauri 的单实例行为），
启动记录里的 PID 随即失效。旧实现 `if launched ... elif image` 会跳过
镜像名关闭，表现为「能打开、关不掉」。

本测试用 ping.exe 的副本模拟：
  · 真实运行一个进程
  · 人为塞进一条 PID 已失效的启动记录
  · 调用关闭流程，断言进程仍被镜像名关掉，且日志记录了失效 PID 与 taskkill 细节
"""
import os
import shutil
import subprocess
import sys
import time

BASE = os.path.dirname(os.path.abspath(__file__))
SANDBOX = os.path.join(BASE, "_t4_appdata")
WORK = os.path.join(BASE, "_t4_bin")
PROBE = os.path.join(WORK, "lf_single_probe.exe")
DEAD_PROBE = os.path.join(WORK, "lf_dead_probe.exe")

shutil.rmtree(SANDBOX, ignore_errors=True)
shutil.rmtree(WORK, ignore_errors=True)
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
    Yes = 1
    No = 0
    calls = []
    answer = Yes
    answer_elevated = No

    @classmethod
    def question(cls, parent, title, text, buttons=None, default=None):
        cls.calls.append(("question", title, text))
        if "管理员" in title:
            return cls.answer_elevated
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


class FakeNotice:
    """捕获「5 秒自关」轻提示（v1.16.0 起，关闭全部成功时不再走 information）。"""
    msgs = []

    class _Sig:
        def connect(self, *a, **k):
            pass

    finished = _Sig()

    def __init__(self, parent, msg, seconds=5):
        FakeNotice.msgs.append(msg)

    def popup(self):
        return self


launchforge.AutoCloseNotice = FakeNotice

src_ping = os.path.join(os.environ.get("SystemRoot", r"C:\Windows"), "System32", "ping.exe")
for p in (PROBE, DEAD_PROBE):
    if not os.path.exists(p):
        shutil.copy2(src_ping, p)

app = QApplication(sys.argv)
win = launchforge.LauncherWindow()
win.list_widget.clear()

# 探针真实启动（模拟"程序本来就在运行"）
proc = subprocess.Popen([PROBE, "-t", "127.0.0.1"],
                        stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                        creationflags=0x08000000)
time.sleep(1.0)
assert proc.poll() is None, "探针未能启动"
print("[1] 探针运行中 PID=%d（模拟程序早已打开）" % proc.pid)

win.add_to_list(PROBE)
win.add_to_list(DEAD_PROBE)

# 关键：伪造"本次启动记录"，但 PID 指向一个不存在的进程
win.launched_items.append((launchforge.ShellProc(999999, os.path.normpath(PROBE)),
                           os.path.normpath(PROBE), win.current_preset_name, []))
win.launched_items.append((launchforge.ShellProc(999998, os.path.normpath(DEAD_PROBE)),
                           os.path.normpath(DEAD_PROBE), win.current_preset_name, []))
print("[2] 已注入失效启动记录：PID 999999 / 999998（进程并不存在）")

FakeMessageBox.calls.clear()
FakeMessageBox.answer = FakeMessageBox.Yes
FakeMessageBox.answer_elevated = FakeMessageBox.No
win.close_all_programs()

deadline = time.time() + 8
while time.time() < deadline and proc.poll() is None:
    app.processEvents()
    time.sleep(0.1)

print("[3] 关闭后探针存活 = %s（应为 False）" % (proc.poll() is None))
assert proc.poll() is not None, "镜像名兜底未生效：进程仍在运行（这是修复前的表现）"

info = [c for c in FakeMessageBox.calls if c[0] == "information"]
result_text = info[-1][2] if info else (FakeNotice.msgs[-1] if FakeNotice.msgs else "")
print("[4] 结果提示 = %r" % result_text.replace("\n", " | "))
assert "已关闭 1 个程序" in result_text, "应统计为已关闭 1 个（提示路径断了？）"

# 日志内容核对
log_text = ""
for _ in range(20):
    if os.path.exists(launchforge.LOG_FILE):
        with open(launchforge.LOG_FILE, "r", encoding="utf-8") as f:
            log_text = f.read()
        if "/im lf_single_probe.exe" in log_text.lower():
            break
    time.sleep(0.15)

print("[5] 日志文件 = %s（%d 字节）" % (launchforge.LOG_FILE, len(log_text)))
assert os.path.exists(launchforge.LOG_FILE), "日志文件未生成"
assert "PID 999999 已失效" in log_text, "日志未记录失效 PID"
assert "taskkill /f /t /im lf_single_probe.exe" in log_text.lower(), "日志未记录镜像名关闭命令"
print("    日志片段：")
for line in log_text.splitlines():
    if "999999" in line or "lf_single_probe" in line.lower() or "关闭目标" in line:
        print("      " + line)

# 第二轮：全部未运行（失效记录存在，但进程确实不在），应提示无需关闭
FakeMessageBox.calls.clear()
win.list_widget.clear()
win.add_to_list(DEAD_PROBE)
win.close_all_programs()
titles = [c[1] for c in FakeMessageBox.calls]
print("[6] 全部未运行：弹窗标题 = %s（不应出现确认框）" % titles)
assert "无需关闭" in titles and "确认关闭" not in titles
print("    提示：%r" % next(c[2] for c in FakeMessageBox.calls if c[1] == "无需关闭"))

print("\nBUG-002 验收通过：失效 PID 不再阻断关闭，镜像名兜底生效，失败原因可留痕。")
