# -*- coding: utf-8 -*-
"""
需求 1 验收测试：启动器打开时不得自动运行任何条目。

验证方式：
  1. 造一份「旧版配置」，其中 settings.auto_launch = True，预设里放一个探针 .bat
  2. 创建主窗口并让事件循环空转 3.5 秒（旧版会在 300ms 时触发自动启动）
  3. 断言探针没有被执行（标记文件不存在）
  4. 再手动触发「一键启动」，断言探针被执行（证明启动能力本身没坏）
  5. 断言「设置」菜单已随功能一并移除
"""
import json
import os
import sys
import time

BASE = os.path.dirname(os.path.abspath(__file__))
SANDBOX = os.path.join(BASE, "_t1_appdata")
MARKER = os.path.join(BASE, "_t1_marker.txt")
PROBE = os.path.join(BASE, "_t1_probe.bat")

# 必须在 import launchforge 之前设置：CONFIG_DIR 在模块导入期就算好了
os.makedirs(SANDBOX, exist_ok=True)
os.environ["LOCALAPPDATA"] = SANDBOX
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

cfg_dir = os.path.join(SANDBOX, "MultiLauncher")
os.makedirs(cfg_dir, exist_ok=True)

for p in (MARKER,):
    if os.path.exists(p):
        os.remove(p)

# 探针批处理：被执行时写一个标记文件
with open(PROBE, "w", encoding="gbk") as f:
    f.write("@echo off\r\n")
    f.write('echo launched > "%s"\r\n' % MARKER)

# 旧版配置：故意把 auto_launch 设为 True
with open(os.path.join(cfg_dir, "launcher_presets.json"), "w", encoding="utf-8") as f:
    json.dump({
        "last_used": "测试方案",
        "presets": {"测试方案": [PROBE]},
        "settings": {"auto_launch": True},
        "global_macro": [],
    }, f, ensure_ascii=False, indent=2)

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

app = QApplication(sys.argv)
win = launchforge.LauncherWindow()

print("[1] 窗口已创建，列表条目数 =", win.list_widget.count())

# 空转 3.5 秒，模拟用户"打开程序后先不动"
deadline = time.time() + 3.5
while time.time() < deadline:
    app.processEvents()
    time.sleep(0.05)

print("[2] 空转 3.5s 后，探针标记存在 =", os.path.exists(MARKER),
      "（应为 False，说明没有自动启动）")
assert not os.path.exists(MARKER), "打开即启动的行为仍然存在！"

print("[3] 菜单栏 action 数 =", len(win.menuBar().actions()),
      "（应为 0，说明「设置」菜单已移除）")
assert len(win.menuBar().actions()) == 0
assert not hasattr(win, "auto_launch_enabled"), "auto_launch_enabled 应已删除"
assert not hasattr(win, "auto_launch_last_preset"), "auto_launch_last_preset 应已删除"

# 手动触发一键启动
win.launch_all()
deadline = time.time() + 12
while time.time() < deadline and not os.path.exists(MARKER):
    app.processEvents()
    time.sleep(0.1)

print("[4] 点击「一键启动」后，探针标记存在 =", os.path.exists(MARKER),
      "（应为 True，说明手动启动正常）")
assert os.path.exists(MARKER), "一键启动失效！"

win.launched_items.clear()
win.close()

print("\n需求 1 验收通过：打开只显示界面，点击按钮才启动。")
