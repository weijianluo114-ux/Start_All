# -*- coding: utf-8 -*-
"""
需求 3 验收测试：文件夹条目。

覆盖：
  1. 通过「添加文件夹」对话框加入，显示 📁 前缀，写入配置
  2. 路径规范化去重（C:/a 与 C:\\a 视为同一条）
  3. 手动输入：带引号 + 环境变量，可加入文件
  4. 手动输入非法路径 → 提示且不入列表
  5. 拖拽文件夹进列表（走真实 dropEvent 过滤逻辑）
  6. 持久化：重启后条目与「上次使用的文件夹」都能恢复
  7. 启动：文件夹用系统方式打开，且返回 None（不产生待关闭进程）
  8. 一键启动：失效条目被跳过，其余照常
  9. 关闭全部：文件夹按窗口处理，未打开窗口时提示「无需关闭」且不弹确认框
 10. 双击失效条目：只提示，不执行启动

运行环境：PyQt5 + offscreen，配置目录指向临时沙箱，不触碰真实配置。
"""
import json
import os
import shutil
import sys
import time

BASE = os.path.dirname(os.path.abspath(__file__))
SANDBOX = os.path.join(BASE, "_t3_appdata")
WORK = os.path.join(BASE, "_t3_work")

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

from PyQt5.QtCore import QMimeData, QPointF, Qt, QUrl  # noqa: E402
from PyQt5.QtGui import QDropEvent  # noqa: E402
from PyQt5.QtWidgets import QApplication, QFileDialog, QInputDialog  # noqa: E402

import launchforge  # noqa: E402


class FakeMessageBox:
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


class FakeFileDialog:
    """替代 QFileDialog 的静态方法，直接返回预设路径。"""
    dir_result = ""
    files_result = []
    ShowDirsOnly = 0x1
    calls_seen_dir = ""

    @classmethod
    def getExistingDirectory(cls, parent, caption, directory, options=None):
        cls.calls_seen_dir = directory
        return cls.dir_result

    @classmethod
    def getOpenFileNames(cls, parent, caption, directory, filters):
        cls.calls_seen_dir = directory
        return list(cls.files_result), ""


class FakeInput:
    text = ""
    ok = True

    @classmethod
    def getText(cls, parent, title, label, text=""):
        return cls.text, cls.ok


launchforge.QMessageBox = FakeMessageBox
launchforge.QFileDialog = FakeFileDialog
launchforge.QInputDialog = FakeInput

# 测试用目录结构
FOLDER = os.path.join(WORK, "工作目录")
SUBFOLDER = os.path.join(FOLDER, "子目录")
MISSING = os.path.join(WORK, "已删除的目录")
NOTE = os.path.join(WORK, "note.txt")
os.makedirs(SUBFOLDER)
with open(NOTE, "w", encoding="utf-8") as f:
    f.write("demo")

app = QApplication(sys.argv)
win = launchforge.LauncherWindow()
win.list_widget.clear()


def labels(w):
    return [w.list_widget.item(i).text() for i in range(w.list_widget.count())]


def paths(w):
    return [w.list_widget.item(i).data(Qt.UserRole) for i in range(w.list_widget.count())]


def config():
    with open(launchforge.CONFIG_FILE, "r", encoding="utf-8") as f:
        return json.load(f)


# ---------- 1. 通过「添加文件夹」加入 ----------
FakeFileDialog.dir_result = FOLDER
win.add_folder_dialog()
print("[1] 列表 =", labels(win))
assert labels(win) == ["📁 工作目录"], "文件夹应带 📁 前缀"
assert paths(win) == [os.path.normpath(FOLDER)]
assert win.list_widget.item(0).toolTip().splitlines()[0] == "文件夹"
assert config()["settings"]["last_folder"] == os.path.normpath(FOLDER), "应记住上次文件夹"
print("    提示文本 =", repr(win.list_widget.item(0).toolTip().replace("\n", " | ")))

# ---------- 2. 去重（不同分隔符） ----------
alt = FOLDER.replace("\\", "/")
dup = win.add_to_list(alt)
print("[2] 用 %r 重复添加 → 返回 %s，条目数 %d" % (alt, dup, win.list_widget.count()))
assert dup is False and win.list_widget.count() == 1, "同一目录不应重复加入"

# ---------- 3. 手动输入：引号 + 环境变量 ----------
os.environ["LF_TEST_ROOT"] = WORK
FakeInput.text = '"%LF_TEST_ROOT%\\note.txt"'
win.add_path_manually()
print("[3] 手动输入后的列表 =", labels(win))
assert labels(win)[-1] == "note.txt", "普通文件不加图标前缀"
assert paths(win)[-1] == os.path.normpath(NOTE), "环境变量与引号应被解析"
assert win.last_folder == os.path.normpath(WORK), "文件条目应记住其所在目录"

# ---------- 4. 非法路径 ----------
FakeMessageBox.calls.clear()
FakeInput.text = MISSING
count_before = win.list_widget.count()
win.add_path_manually()
titles = [c[1] for c in FakeMessageBox.calls]
print("[4] 输入不存在的路径 → 弹窗 %s，条目数 %d（应仍为 %d）"
      % (titles, win.list_widget.count(), count_before))
assert "路径无效" in titles and win.list_widget.count() == count_before

# ---------- 5. 拖拽文件夹 ----------
mime = QMimeData()
mime.setUrls([QUrl.fromLocalFile(SUBFOLDER)])
event = QDropEvent(QPointF(10, 10), Qt.CopyAction, mime, Qt.LeftButton, Qt.NoModifier)
win.dropEvent(event)
print("[5] 拖入文件夹后 =", labels(win))
assert "📁 子目录" in labels(win), "拖拽文件夹应被接受"
assert win.last_folder == os.path.normpath(SUBFOLDER)

# ---------- 6. 持久化 ----------
win.save_config()
saved = config()
print("[6] 配置中的预设 =", saved["presets"][win.current_preset_name])
assert os.path.normpath(FOLDER) in saved["presets"][win.current_preset_name]
win2 = launchforge.LauncherWindow()
print("    重建窗口后 =", labels(win2))
assert "📁 工作目录" in labels(win2) and "note.txt" in labels(win2)
assert win2.last_folder == os.path.normpath(SUBFOLDER), "上次文件夹应跨会话保留"

# ---------- 7. 文件夹以系统方式打开 ----------
opened = []
_real_startfile = getattr(os, "startfile", None)
os.startfile = lambda p: opened.append(p)
try:
    result = launchforge.launch_program(FOLDER)
finally:
    if _real_startfile is not None:
        os.startfile = _real_startfile
print("[7] 打开文件夹 → opened=%r，返回值=%r" % (opened, result))
assert opened == [os.path.normpath(FOLDER)], "应调用系统接口打开目录"
assert result is None, "文件夹不产生待管理进程"

# ---------- 8. 一键启动：失效条目跳过 ----------
# 先制造一条失效条目（模拟目录被删/移动）
assert win2.add_to_list(MISSING) is True
print("[8] 含失效条目的列表 =", labels(win2))
assert any(l.startswith("⚠") for l in labels(win2))

launched = []
_real_launch = launchforge.launch_program
launchforge.launch_program = lambda p: launched.append(p)
try:
    win2.launch_all()
    if win2._launch_thread:
        win2._launch_thread.join(timeout=10)
    deadline = time.time() + 2
    while time.time() < deadline and win2._launching:
        app.processEvents()
        time.sleep(0.05)
finally:
    launchforge.launch_program = _real_launch

print("    实际启动 =", [os.path.basename(p) for p in launched])
assert os.path.normpath(NOTE) in launched
assert MISSING not in launched, "失效条目必须跳过"
# v1.6.0 起：文件夹一律交给系统资源管理器打开（每个文件夹一个窗口）
assert os.path.normpath(FOLDER) in launched, "文件夹应由资源管理器打开"
assert os.path.normpath(os.path.join(FOLDER, "子目录")) in launched
assert not hasattr(win2, "_folder_window"), "自建标签窗口已回退，不应存在"

# ---------- 9. 文件夹条目参与"关闭全部"（v1.7.0 起按窗口关闭） ----------
# 该临时文件夹从未真正打开过窗口 → 应提示"没有找到对应的文件夹窗口"，且不弹确认框
win3 = launchforge.LauncherWindow()
win3.list_widget.clear()
win3.add_to_list(FOLDER)
FakeMessageBox.calls.clear()
win3.close_all_programs()
titles = [c[1] for c in FakeMessageBox.calls]
print("[9] 仅文件夹且未打开窗口时点击关闭 → 弹窗 %s" % titles)
assert "无需关闭" in titles
assert "没有找到对应的文件夹窗口" in "".join(c[2] for c in FakeMessageBox.calls)
assert "确认关闭" not in titles, "没有可关闭的窗口时不该弹确认框"

# ---------- 10. 双击失效条目 ----------
calls = []
launchforge.launch_program = lambda p: calls.append(p)
try:
    target_item = None
    for i in range(win2.list_widget.count()):
        if win2.list_widget.item(i).text().startswith("⚠"):
            target_item = win2.list_widget.item(i)
            break
    assert target_item is not None
    FakeMessageBox.calls.clear()
    win2.on_item_double_clicked(target_item)
finally:
    launchforge.launch_program = _real_launch
print("[10] 双击失效条目 → 启动调用 = %r，弹窗 = %s"
      % (calls, [c[1] for c in FakeMessageBox.calls]))
assert calls == [] and "无法打开" in [c[1] for c in FakeMessageBox.calls]

print("\n需求 3 验收通过：文件夹可添加/持久化/打开，失效路径可见且被安全跳过。")
