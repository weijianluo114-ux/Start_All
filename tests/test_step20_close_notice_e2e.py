# -*- coding: utf-8 -*-
"""
Step 20 端到端（真实进程）：关闭全部的结果提示自己消失（REQ-017 / v1.16.0）

脚本级断言见 `test_step20_close_notice.py`；这里补**真实进程**的一趟：
真的启动记事本 → 真的走 `close_all_programs()` → 观察「关闭结果」提示：

  * 全程**不点任何按钮**（确认框除外，那是关闭前的必经确认），提示必须在 ~5 秒后自己消失
  * 提示上**没有任何按钮**，且是非模态（主界面仍可操作）
  * 记事本真的被关掉了（确认关闭流程本身没被这个改动影响）

失败分支（有程序没关掉 → 弹 `QMessageBox` 等用户点）的真实验证成本很高
（要造一个拒绝被结束的进程），交给脚本级 `test_step20_close_notice.py` 第 2 段用 mock 覆盖。

**必须用 windows 平台**：offscreen 下 `QMessageBox.exec_()` 段错误。

运行：python tests/test_step20_close_notice_e2e.py
"""

import os
import sys
import tempfile
import time

os.environ['QT_QPA_PLATFORM'] = 'windows'

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, 'src'))

from PyQt5.QtCore import QTimer, Qt
from PyQt5.QtWidgets import QApplication, QListWidgetItem, QMessageBox, QPushButton

app = QApplication(sys.argv)
os.environ['LOCALAPPDATA'] = tempfile.mkdtemp(prefix='lf_t20e_')

import launchforge
from launchforge import AutoCloseNotice

launchforge.heal_autostart_path = lambda: None

win = launchforge.LauncherWindow()
win.move(30, 30)
win.show()

NOTEPAD = os.path.join(os.environ.get('SystemRoot', r'C:\Windows'), 'System32',
                       'notepad.exe')
assert os.path.exists(NOTEPAD), '找不到 notepad.exe'

# ---------- 准备：列表里放记事本，并真的启动它 ----------
# 启动走后台线程（`_launch_worker`），条目必须进 `list_widget`，
# 光给 `win.items` 赋值不会被 `launch_all` 读到。
item = QListWidgetItem('记事本')
item.setData(Qt.UserRole, NOTEPAD)
win.list_widget.addItem(item)

print('[准备] 启动记事本…')
win.launch_all()
for _ in range(60):                       # 最多等 6 秒，等后台启动线程收尾
    app.processEvents()
    if not getattr(win, '_launching', False) and win.launched_items:
        break
    time.sleep(0.1)
assert win.launched_items, '记事本没被记进 launched_items，无法验证关闭流程'
procs = [p for p, *_ in win.launched_items if p is not None]
print('已启动 %d 个进程：%s' % (len(procs), [p.pid for p in procs]))

# ---------- 执行：模拟"用户不点按钮" ----------
state = {'seen': None, 'gone': None, 'buttons': None, 'yes': 0, 'text': None}


def poll():
    w = QApplication.activeModalWidget()
    if isinstance(w, QMessageBox):        # 关闭前的确认框：点 Yes（用户必须同意才能关）
        for b in w.buttons():
            if w.standardButton(b) in (QMessageBox.Yes, QMessageBox.Ok):
                state['yes'] += 1
                print('    确认框 %r → 点 Yes' % w.windowTitle())
                b.click()
                break
        return

    for top in QApplication.topLevelWidgets():
        if isinstance(top, AutoCloseNotice):
            if state['seen'] is None and top.isVisible():
                state['seen'] = time.time()
                state['buttons'] = top.findChildren(QPushButton)
                state['text'] = top._label.text()
                state['win_enabled'] = win.isEnabled()
                print('    结果提示出现，按钮数=%d，主界面可用=%s'
                      % (len(state['buttons']), state['win_enabled']))
            return
    if state['seen'] is not None and state['gone'] is None:
        state['gone'] = time.time()
        print('    %.2fs：提示已消失（全程没点它）' % (state['gone'] - state['seen']))
        app.quit()


timer = QTimer()
timer.timeout.connect(poll)
timer.start(120)
QTimer.singleShot(25000, app.quit)        # 兜底

print('[执行] 调用 close_all_programs()…')
win.close_all_programs()
app.exec_()

# ---------- 断言 ----------
print('[结果]')
assert state['seen'] is not None, '全程没出现结果提示'
assert len(state['buttons']) == 0, '提示上有 %d 个按钮，用户还得点' % len(state['buttons'])
assert state['win_enabled'], '提示弹出后主界面被禁用了（模态会挡住操作）'
assert state['gone'] is not None, '提示一直没自己消失（等到了兜底退出）'
stayed = state['gone'] - state['seen']
print('    提示停留 %.2fs（期望 ~5s，容差 4.0–7.0s）' % stayed)
assert 4.0 <= stayed <= 7.0, '停留 %.2fs 不在 5 秒附近' % stayed
assert '5 秒后自动关闭' in (state['text'] or ''), '倒计时文案不对：%r' % state['text']

alive = [p for p in procs if p.poll() is None]
print('    记事本进程仍在运行：%d 个（期望 0）' % len(alive))
assert not alive, '记事本没被关掉：%s' % [p.pid for p in alive]

print('\nSTEP 20 端到端通过：真实关闭全部后，提示无按钮、不挡界面、约 5 秒自己消失。')
