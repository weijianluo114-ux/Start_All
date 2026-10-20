"""
已封存的「全局鼠标宏」功能（v1.9.0 起不再随主程序打包）。

为什么要封存
------------
录制的是**屏幕绝对坐标**的鼠标轨迹（移动/按下/抬起/滚轮 + 相对时间戳），
回放时按时间戳 sleep 后重放。它有三个绕不过去的问题：
  1. 窗口位置一变、分辨率或缩放到 125%/150%，宏就会点到别处；
  2. 只录鼠标，不录键盘，输入类操作无法录制；
  3. 录制时点击「停止录制」这一下本身也会被录进末尾，回放会多点一次。

本模块**不被 src/launchforge.py import**，因此 PyInstaller 不会收集它，
exe 体积与依赖都不受影响（pynput 已从 requirements 中移除）。

如何恢复（三步）
----------------
1. `src/launchforge.py` 顶部加：
       from legacy.macro_feature import MacroRecorderDialog, play_macro
   并把 `pynput` 重新写入 `requirements.txt`（PyInstaller 只收集被 import 的包）。
2. 在列表下方重新加三个按钮，分别接：
       录制 -> dlg = MacroRecorderDialog(self); events = dlg.get_events()
       播放 -> threading.Thread(target=play_macro, args=(events,), daemon=True).start()
       清除 -> 配置字段置空
3. 在 `_launch_worker` 末尾、`_launch_finished` 之前恢复自动回放
   （原实现：启动完成后 `time.sleep(2)` 再回放）。
"""

import time
import threading

from PyQt5.QtWidgets import QDialog, QVBoxLayout, QLabel, QPushButton, QMessageBox
from PyQt5.QtCore import Qt  # noqa: F401  （保留，便于恢复时扩展快捷键）

from PyQt5.QtWidgets import QApplication  # noqa: F401

try:
    from pynput.mouse import Listener as MouseListener, Button, Controller as MouseController
    from pynput.keyboard import Listener as KeyboardListener, Key
    HAS_PYNPUT = True
except ImportError:
    HAS_PYNPUT = False


class MacroRecorderDialog(QDialog):
    """录制鼠标宏的对话框（用于全局宏）"""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle('录制全局鼠标宏')
        self.setModal(True)
        self.setMinimumSize(300, 120)

        layout = QVBoxLayout(self)
        self.label = QLabel('开始录制，请执行鼠标操作...\n点击「停止录制」或关闭窗口结束。')
        layout.addWidget(self.label)

        self.btn_stop = QPushButton('停止录制')
        self.btn_stop.clicked.connect(self.stop_recording)
        layout.addWidget(self.btn_stop)

        self.events = []
        self.recording = False
        self.start_time = None
        self._stop_flag = threading.Event()
        self.mouse_listener = None
        self.keyboard_listener = None

        self.start_recording()

    def start_recording(self):
        if not HAS_PYNPUT:
            QMessageBox.warning(self, '错误', 'pynput 未安装，无法录制宏。')
            self.reject()
            return

        self.events.clear()
        self.start_time = time.perf_counter()
        self.recording = True

        def on_move(x, y):
            if not self.recording or self._stop_flag.is_set():
                return False
            self.events.append({
                'type': 'move',
                'x': x,
                'y': y,
                'time': time.perf_counter() - self.start_time,
            })
            return True

        def on_click(x, y, button, pressed):
            if not self.recording or self._stop_flag.is_set():
                return False
            self.events.append({
                'type': 'click',
                'x': x,
                'y': y,
                'button': button.name,
                'pressed': pressed,
                'time': time.perf_counter() - self.start_time,
            })
            return True

        def on_scroll(x, y, dx, dy):
            if not self.recording or self._stop_flag.is_set():
                return False
            self.events.append({
                'type': 'scroll',
                'x': x,
                'y': y,
                'dx': dx,
                'dy': dy,
                'time': time.perf_counter() - self.start_time,
            })
            return True

        self.mouse_listener = MouseListener(on_move=on_move, on_click=on_click, on_scroll=on_scroll)
        self.mouse_listener.start()

        def on_press(key):
            if key == Key.esc:
                self.stop_recording()
                return False
            return True

        self.keyboard_listener = KeyboardListener(on_press=on_press)
        self.keyboard_listener.start()

        self.label.setText('录制中... 按 ESC 或点击「停止录制」结束。')

    def stop_recording(self):
        if not self.recording:
            return
        self.recording = False
        self._stop_flag.set()
        if self.mouse_listener and self.mouse_listener.running:
            self.mouse_listener.stop()
        if self.keyboard_listener and self.keyboard_listener.running:
            self.keyboard_listener.stop()
        self.label.setText(f'录制完成，共 {len(self.events)} 个事件。')
        self.btn_stop.setEnabled(False)
        self.btn_stop.setText('已停止')

    def get_events(self):
        return self.events

    def closeEvent(self, event):
        self.stop_recording()
        event.accept()

def play_macro(macro):
    """按录制时的时间戳回放鼠标事件。

    与旧实现等价：move 直接设坐标、click 按 pressed 分发 press/release、
    scroll 按 dx/dy 滚动。时间戳是相对录制起点的秒数，逐条算差值 sleep。
    """
    if not macro or not HAS_PYNPUT:
        return
    controller = MouseController()
    last_time = 0.0
    for event in macro:
        t = event.get('time', 0)
        delta = t - last_time
        if delta > 0:
            time.sleep(delta)
        last_time = t
        etype = event['type']
        if etype == 'move':
            controller.position = (event['x'], event['y'])
        elif etype == 'click':
            button_map = {'left': Button.left, 'right': Button.right, 'middle': Button.middle}
            btn = button_map.get(event['button'])
            if not btn:
                continue
            if event['pressed']:
                controller.press(btn)
            else:
                controller.release(btn)
        elif etype == 'scroll':
            controller.scroll(event['dx'], event['dy'])
