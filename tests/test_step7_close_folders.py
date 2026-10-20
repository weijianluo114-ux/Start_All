# -*- coding: utf-8 -*-
"""
需求 5 验收测试：关闭文件夹窗口（整窗关闭 + 混合标签询问）。

覆盖：
  1. 枚举资源管理器窗口：返回结构合法，同一窗口的标签合并为一条
  2. 纯文件夹条目 + 真实打开两个文件夹 → 判定为"可整窗关闭"
  3. 用户在主确认框点「否」→ 一个窗口都不关
  4. 用户点「是」→ 列表内的两个窗口关闭；无关窗口完好；explorer.exe 存活
  5. 列表内文件夹未打开 → 计入"未打开窗口"，不报错
  6. 混合标签窗口（列表内 + 列表外）→ 单独询问
       · 选「否」→ 跳过，不调用关闭
       · 选「是」→ 整窗关闭
  7. 只有文件夹且都没打开 → 提示「无需关闭」，不弹确认框

运行环境：PyQt5 + offscreen，配置目录指向临时沙箱。
本测试会真实打开/关闭两个临时文件夹窗口（约 3 秒），不触碰其他窗口。
"""
import os
import shutil
import sys
import time

BASE = os.path.dirname(os.path.abspath(__file__))
SANDBOX = os.path.join(BASE, "_t7_appdata")
WORK = os.path.join(BASE, "_t7_work")

shutil.rmtree(SANDBOX, ignore_errors=True)
shutil.rmtree(WORK, ignore_errors=True)
os.makedirs(SANDBOX, exist_ok=True)
os.makedirs(WORK, exist_ok=True)
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

from PyQt5.QtWidgets import QApplication, QMessageBox  # noqa: E402

import launchforge  # noqa: E402


class FakeMessageBox:
    Yes = QMessageBox.Yes
    No = QMessageBox.No
    calls = []
    answers = []

    @classmethod
    def reset(cls, *answers):
        cls.calls = []
        cls.answers = list(answers) if answers else [cls.Yes]

    @classmethod
    def question(cls, parent, title, text, buttons=None, default=None):
        cls.calls.append(("question", title, text))
        return cls.answers.pop(0) if cls.answers else cls.No

    @classmethod
    def information(cls, parent, title, text):
        cls.calls.append(("information", title, text))
        return cls.Yes

    @classmethod
    def warning(cls, parent, title, text):
        cls.calls.append(("warning", title, text))
        return cls.Yes


launchforge.QMessageBox = FakeMessageBox

A = os.path.join(WORK, "Alpha")
B = os.path.join(WORK, "Bravo")
C = os.path.join(WORK, "Charlie")      # 不在列表内，用于"无关窗口"与"混合标签"
D = os.path.join(WORK, "Delta")        # 在列表内，但不打开
for d in (A, B, C, D):
    os.makedirs(d, exist_ok=True)
    with open(os.path.join(d, "readme.txt"), "w", encoding="utf-8") as f:
        f.write("keep")

app = QApplication(sys.argv)


def norm(p):
    return launchforge._norm_fs_path(p)


def windows():
    return launchforge.list_explorer_windows()


def has_window(path):
    return any(norm(p) == norm(path) for w in windows() for p in w["paths"])


def wait_until(predicate, timeout=6.0):
    deadline = time.time() + timeout
    while time.time() < deadline:
        app.processEvents()
        if predicate():
            return True
        time.sleep(0.15)
    return False


def open_folder(path):
    launchforge.launch_program(path)


def close_quietly(path):
    """收尾用：按路径找到窗口并发 WM_CLOSE，避免测试残留窗口。"""
    import win32gui
    for w in windows():
        if any(norm(p) == norm(path) for p in w["paths"]):
            try:
                win32gui.PostMessage(w["hwnd"], 0x0010, 0, 0)   # WM_CLOSE
            except Exception:
                pass


# ---------- 1. 枚举结构 ----------
wins = windows()
print("[1] 枚举到资源管理器窗口 %d 个" % len(wins))
for w in wins:
    assert isinstance(w["hwnd"], int) and w["hwnd"] > 0
    assert isinstance(w["paths"], list) and w["paths"]
print("    样例：hwnd=%s tabs=%d title=%r" % (wins[0]["hwnd"], len(wins[0]["paths"]), wins[0]["title"]))

baseline = {w["hwnd"] for w in wins}

# ---------- 2. 打开 A、B（列表内）+ C（列表外，作为无关窗口） ----------
open_folder(A)
open_folder(B)
open_folder(C)
opened = wait_until(lambda: has_window(A) and has_window(B) and has_window(C))
print("[2] 三个临时文件夹已打开 =", opened)
assert opened, "临时文件夹窗口未能打开，环境异常"

win = launchforge.LauncherWindow()
win.list_widget.clear()
for p in (A, B, D):
    win.add_to_list(p)

closable, mixed = win._folder_window_plan([A, B, D])
print("[3] 判定：可整窗关闭 %d 个，混合 %d 个 → %s"
      % (len(closable), len(mixed), [win._window_label(w) for w in closable]))
assert len(closable) == 2 and not mixed, "应识别出 A、B 两个可关闭窗口，且 D 未打开不算"
assert all(len(w["paths"]) == 1 for w in closable)

# ---------- 3. 主确认框点「否」 ----------
FakeMessageBox.reset(FakeMessageBox.No)
win.close_all_programs()
assert has_window(A) and has_window(B), "点了否却把窗口关了"
print("[4] 确认框点否 → 窗口仍在，正文含窗口清单 =",
      "文件夹窗口" in FakeMessageBox.calls[0][2])

# ---------- 4. 主确认框点「是」 ----------
FakeMessageBox.reset(FakeMessageBox.Yes)
win.close_all_programs()
gone = wait_until(lambda: not has_window(A) and not has_window(B))
print("[5] 确认后 A/B 已关闭 =", gone, "；无关窗口 C 仍在 =", has_window(C))
assert gone, "确认后 A/B 窗口未关闭"
assert has_window(C), "列表外的窗口 C 被误关！"

info = [c for c in FakeMessageBox.calls if c[0] == "information"]
assert info and "文件夹窗口" in info[-1][2], "结果提示应包含窗口关闭数量"
print("    结果提示：%r" % info[-1][2].replace("\n", " | "))

import subprocess
out = subprocess.run(["tasklist", "/fi", "IMAGENAME eq explorer.exe", "/fo", "csv", "/nh"],
                     capture_output=True).stdout.decode("gbk", errors="ignore")
assert "explorer.exe" in out.lower(), "资源管理器本体被误杀！"
print("[6] explorer.exe 存活 = True")

# ---------- 5. 混合标签窗口：用补丁模拟同一窗口含 A + C ----------
REAL_LIST = launchforge.list_explorer_windows
FAKE_HWND = 424242


def fake_list():
    return [{"hwnd": FAKE_HWND, "title": "Alpha 和 Charlie", "paths": [A, C]}]


launchforge.list_explorer_windows = fake_list
try:
    win2 = launchforge.LauncherWindow()
    win2.list_widget.clear()
    win2.add_to_list(A)
    closable2, mixed2 = win2._folder_window_plan([A])
    print("[7] 混合窗口判定：可关闭 %d，混合 %d，外标签 %s"
          % (len(closable2), len(mixed2), mixed2[0]["foreign"] if mixed2 else None))
    assert not closable2 and len(mixed2) == 1
    assert norm(mixed2[0]["foreign"][0]) == norm(C)

    calls = []
    win2._close_folder_window = lambda w: (calls.append(w), (True, "fake"))[1]

    # 5a. 混合询问选「否」→ 跳过
    FakeMessageBox.reset(FakeMessageBox.Yes, FakeMessageBox.No)
    win2.close_all_programs()
    mixed_q = [c for c in FakeMessageBox.calls if c[0] == "question" and "其他标签" in c[1]]
    print("[8] 混合窗口选否 → 是否询问 = %s，关闭调用 = %d 次" % (bool(mixed_q), len(calls)))
    assert mixed_q, "混合窗口应单独询问"
    assert not calls, "选否仍然关闭了窗口"

    # 5b. 混合询问选「是」→ 整窗关闭
    calls.clear()
    FakeMessageBox.reset(FakeMessageBox.Yes, FakeMessageBox.Yes)
    win2.close_all_programs()
    print("[9] 混合窗口选是 → 关闭调用 = %d 次，hwnd=%s"
          % (len(calls), calls[0]["hwnd"] if calls else None))
    assert len(calls) == 1 and calls[0]["hwnd"] == FAKE_HWND
finally:
    launchforge.list_explorer_windows = REAL_LIST

# ---------- 6. 只有文件夹且都没打开 ----------
win3 = launchforge.LauncherWindow()
win3.list_widget.clear()
win3.add_to_list(D)
FakeMessageBox.reset(FakeMessageBox.Yes)
win3.close_all_programs()
titles = [c[1] for c in FakeMessageBox.calls]
print("[10] 只有文件夹且未打开 → 弹窗 %s" % titles)
assert "无需关闭" in titles, "应提示无需关闭"
assert "确认关闭" not in titles

# ---------- 收尾 ----------
close_quietly(C)
wait_until(lambda: not has_window(C), timeout=4)
print("[11] 清理后 C 仍存在 =", has_window(C))

shutil.rmtree(WORK, ignore_errors=True)
print("\n需求 5 验收通过：文件夹窗口可整窗关闭，混合标签窗口询问后按用户选择执行。")
