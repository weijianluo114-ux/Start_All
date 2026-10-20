import sys
import os
import csv
import json
import logging
import logging.handlers
import subprocess
import tempfile
import time
import threading
import ctypes
from PyQt5.QtWidgets import (
    QApplication, QMainWindow, QVBoxLayout, QHBoxLayout, QPushButton,
    QListWidget, QListWidgetItem, QFileDialog, QWidget, QMessageBox,
    QAbstractItemView, QComboBox, QLabel, QInputDialog, QMenu, QDialog
)
from PyQt5.QtCore import Qt, QTimer, QDir, QRectF, QPointF, pyqtSignal
from PyQt5.QtGui import (
    QDragEnterEvent, QDropEvent, QIcon, QPainter, QColor, QBrush, QPen, QFont,
    QLinearGradient, QRadialGradient, QPainterPath, QPainterPathStroker
)

try:
    from win32com.client import Dispatch
    HAS_WIN32 = True
except ImportError:
    HAS_WIN32 = False

try:
    from pynput.mouse import Listener as MouseListener, Button, Controller as MouseController
    from pynput.keyboard import Listener as KeyboardListener, Key
    HAS_PYNPUT = True
except ImportError:
    HAS_PYNPUT = False
    print('警告：未安装 pynput，鼠标宏功能不可用。请执行 pip install pynput')

try:
    import win32gui
    import win32con
    import win32process
    HAS_WIN32GUI = True
except ImportError:
    HAS_WIN32GUI = False
    print('警告：未安装 pywin32，激活窗口功能不可用。请执行 pip install pywin32')





def get_app_data_dir():
    if sys.platform == 'win32':
        base = os.environ.get('LOCALAPPDATA', os.path.expanduser('~'))
        path = os.path.join(base, 'MultiLauncher')
    elif sys.platform == 'darwin':
        path = os.path.expanduser('~/Library/Application Support/MultiLauncher')
    else:
        path = os.path.expanduser('~/.config/MultiLauncher')
    os.makedirs(path, exist_ok=True)
    return path


CONFIG_DIR = get_app_data_dir()
CONFIG_FILE = os.path.join(CONFIG_DIR, 'launcher_presets.json')
LOG_DIR = os.path.join(CONFIG_DIR, 'logs')
LOG_FILE = os.path.join(LOG_DIR, 'launcher.log')

APP_VERSION = '1.7.0'

log = logging.getLogger('launchforge')


# ------------------------- 子进程隐藏 -------------------------
#
# 打包成 --windowed 后进程没有控制台。此时用 subprocess 调用 taskkill / tasklist，
# Windows 会为每个子进程临时创建一个控制台窗口——视觉上就是"关程序时闪一堆黑框"。
# 关闭流程本来就会多次调用（快照 → 逐个 taskkill → 轮询复查），所以黑框会连续出现。
# 统一用 CREATE_NO_WINDOW + STARTUPINFO(SW_HIDE) 隐藏，并避免 shell=True（少一层 cmd.exe）。

_CREATE_NO_WINDOW = 0x08000000

_hidden_kwargs_cache = None


def hidden_subprocess_kwargs():
    """返回隐藏子进程窗口所需的 Popen 参数（非 Windows 返回空字典）。"""
    global _hidden_kwargs_cache
    if _hidden_kwargs_cache is not None:
        return _hidden_kwargs_cache
    if sys.platform != 'win32':
        _hidden_kwargs_cache = {}
        return _hidden_kwargs_cache
    si = subprocess.STARTUPINFO()
    si.dwFlags |= subprocess.STARTF_USESHOWWINDOW
    si.wShowWindow = 0                      # SW_HIDE
    _hidden_kwargs_cache = {
        'creationflags': _CREATE_NO_WINDOW | getattr(subprocess, 'CREATE_NEW_PROCESS_GROUP', 0),
        'startupinfo': si,
    }
    return _hidden_kwargs_cache


def setup_logging():
    """
    初始化文件日志。

    `--windowed` 打包后没有控制台，异常与失败原因只能靠日志留痕；
    日志按 1 MB 轮转、保留 3 份，避免长期运行无限增长。
    """
    logger = logging.getLogger('launchforge')
    if getattr(logger, '_lf_ready', False):
        return logger

    try:
        os.makedirs(LOG_DIR, exist_ok=True)
        handler = logging.handlers.RotatingFileHandler(
            LOG_FILE, maxBytes=1024 * 1024, backupCount=3, encoding='utf-8')
        handler.setFormatter(logging.Formatter(
            '%(asctime)s [%(levelname)s] %(message)s', '%Y-%m-%d %H:%M:%S'))
        logger.addHandler(handler)
        logger.setLevel(logging.INFO)

        # 仅在存在真实控制台时额外输出（--windowed 下 sys.stderr 为 None）
        if sys.stderr is not None:
            stream = logging.StreamHandler()
            stream.setFormatter(handler.formatter)
            logger.addHandler(stream)
        logger._lf_ready = True
    except Exception:
        # 日志不可用时不应影响程序本身
        pass
    return logger


def decode_console(data):
    """Windows 控制台输出多为 GBK，逐级回退解码。"""
    if not data:
        return ''
    if isinstance(data, str):
        return data
    for enc in ('gbk', 'utf-8', 'mbcs'):
        try:
            return data.decode(enc)
        except Exception:
            continue
    return data.decode('utf-8', errors='replace')


def install_exception_hooks():
    """把未捕获异常与线程异常写进日志，避免 GUI 下无痕崩溃。"""
    def hook(exc_type, exc, tb):
        try:
            log.error('未捕获异常: %s', exc, exc_info=(exc_type, exc, tb))
        except Exception:
            pass
        try:
            sys.__excepthook__(exc_type, exc, tb)
        except Exception:
            pass

    sys.excepthook = hook

    if hasattr(threading, 'excepthook'):
        def thread_hook(args):
            try:
                log.error('线程未捕获异常: %s (%s)',
                          args.exc_value, getattr(args.thread, 'name', '?'),
                          exc_info=(args.exc_type, args.exc_value, args.exc_traceback))
            except Exception:
                pass

        threading.excepthook = thread_hook


def resolve_lnk(path):
    if not HAS_WIN32 or not path.lower().endswith('.lnk'):
        return path
    try:
        shell = Dispatch('WScript.Shell')
        shortcut = shell.CreateShortCut(path)
        target = shortcut.TargetPath
        return target if os.path.exists(target) else path
    except Exception:
        return path


def get_display_name(path):
    if path.lower().endswith('.lnk') and HAS_WIN32:
        target = resolve_lnk(path)
        name = os.path.basename(target) if target != path else os.path.basename(path)
    else:
        name = os.path.basename(path)

    if not name:                      # 盘符根目录（如 C:\）的 basename 为空
        name = path
    return name


def normalize_input_path(text):
    """
    把拖入 / 粘贴 / 手输的路径规范化为绝对路径。

    支持：前后空白、成对引号（资源管理器“复制为路径”会带引号）、
    %USERPROFILE% 这类环境变量、~ 用户目录。
    返回空字符串表示输入无效。
    """
    if not text:
        return ''
    s = text.strip().strip('"').strip("'").strip()
    if not s:
        return ''
    s = os.path.expandvars(s)
    s = os.path.expanduser(s)
    return os.path.normpath(s)


def entry_kind(path):
    """条目类型：'dir' 文件夹 / 'file' 文件 / 'missing' 路径不存在。"""
    try:
        if os.path.isdir(path):
            return 'dir'
        if os.path.isfile(path):
            return 'file'
    except Exception:
        pass
    return 'missing'


def entry_label(path):
    """列表显示名：文件夹加 📁 前缀，失效路径加 ⚠ 前缀。"""
    name = get_display_name(path)
    kind = entry_kind(path)
    if kind == 'dir':
        return '📁 ' + name
    if kind == 'missing':
        return '⚠ ' + name
    return name


def entry_tooltip(path):
    tip = {'dir': '文件夹', 'file': '文件', 'missing': '路径不存在，启动时将被跳过'}[entry_kind(path)]
    return '%s\n%s' % (tip, path)


class ShellProc:
    """模拟 subprocess.Popen 对象，用于 WScript.Shell.Run 启动的进程"""
    def __init__(self, pid, target):
        self.pid = pid
        self.target = target

    def wait(self, timeout=None):
        return None

    def kill(self):
        try:
            subprocess.run(['taskkill', '/f', '/pid', str(self.pid)],
                           capture_output=True, timeout=5, **hidden_subprocess_kwargs())
        except Exception:
            return None


def launch_program(path):
    """启动程序 / 打开文件或文件夹，返回 (proc, resolved_path) 或 None"""
    resolved = resolve_lnk(path)

    # 文件夹：交给系统打开。Windows 用 os.startfile 会以资源管理器打开该目录，
    # 不会产生需要管理的子进程，因此返回 None。
    if os.path.isdir(resolved):
        try:
            if sys.platform == 'win32':
                os.startfile(resolved)
            elif sys.platform == 'darwin':
                subprocess.Popen(['open', resolved])
            else:
                subprocess.Popen(['xdg-open', resolved])
        except Exception as e:
            print('打开文件夹失败 %s: %s' % (resolved, e))
        return None

    ext = os.path.splitext(resolved)[1].lower()

    if ext in ('.exe', '.bat', '.cmd', '.com'):
        if sys.platform == 'win32':
            if ext in ('.bat', '.cmd'):
                work_dir = os.path.dirname(resolved) or os.getcwd()
                proc = subprocess.Popen(
                    resolved,
                    cwd=work_dir,
                    creationflags=subprocess.CREATE_NEW_CONSOLE
                )
            else:
                work_dir = tempfile.mkdtemp()
                proc = subprocess.Popen(resolved, cwd=work_dir)
            return proc, resolved

        elif sys.platform == 'darwin':
            subprocess.Popen(['open', resolved])
        else:
            subprocess.Popen(['xdg-open', resolved])
        return None

    if HAS_WIN32:
        try:
            shell = Dispatch('WScript.Shell')
            pid = shell.Run(resolved, 1, False)
            if pid:
                return ShellProc(pid, resolved), resolved

            os.startfile(path)
            return None
        except Exception:
            try:
                os.startfile(path)
            except Exception:
                pass
            return None

    try:
        os.startfile(path)
    except Exception:
        pass
    return None


# ------------------------- 资源管理器窗口 -------------------------
#
# 关闭文件夹条目的本质是"关闭承载它的窗口"，Windows 没有"关闭某个文件夹"的接口。
# 实测结论（Windows 11，见 docs/04-问题/Q-003）：
#   1. Shell.Application.Windows() 会把标签页逐条列出，同一窗口的多个标签共享同一个 HWND；
#   2. 每个条目可用 Document.Folder.Self.Path 取到该标签的路径，后台标签也能取到；
#   3. 多标签窗口下 Quit() 无效，WM_CLOSE 只关闭"当前活动标签"，连发才能整窗关闭。
# 因此实现路线是：按 HWND 分组 → 用路径判定该窗口的标签是否**全部**属于列表条目 → 整窗关闭。
# 之所以不在打开时记录 HWND：用户把窗口拖进另一窗口合并成标签后，原 HWND 会消失，记录必然失效。

def _norm_fs_path(path):
    """路径归一化，用于与资源管理器窗口的路径比对。"""
    if not path:
        return ''
    p = str(path)
    if p.startswith('::'):
        return p.lower()               # 虚拟位置（主文件夹 / 此电脑），不参与匹配
    try:
        p = os.path.normpath(p)
    except Exception:
        return p.lower()
    return os.path.normcase(p)


def list_explorer_windows():
    """
    枚举资源管理器窗口。

    返回 [{'hwnd': int, 'title': str, 'paths': [路径, ...]}]，
    同一窗口的多个标签合并到同一条的 paths 中（顺序即系统给出的顺序）。
    非资源管理器窗口按窗口类名过滤；缺少 pywin32 时返回空列表。
    """
    if sys.platform != 'win32' or not HAS_WIN32 or not HAS_WIN32GUI:
        return []

    try:
        wins = Dispatch('Shell.Application').Windows()
    except Exception:
        log.exception('枚举资源管理器窗口失败')
        return []

    grouped, order = {}, []
    for i in range(wins.Count):
        try:
            w = wins.Item(i)
            hwnd = int(w.HWND)
        except Exception:
            continue
        try:
            if win32gui.GetClassName(hwnd) != 'CabinetWClass':
                continue
        except Exception:
            continue
        try:
            path = w.Document.Folder.Self.Path
        except Exception:
            path = ''
        if hwnd not in grouped:
            grouped[hwnd] = {'hwnd': hwnd, 'title': '', 'paths': []}
            order.append(hwnd)
        grouped[hwnd]['paths'].append(path or '')

    result = []
    for hwnd in order:
        entry = grouped[hwnd]
        try:
            entry['title'] = win32gui.GetWindowText(hwnd)
        except Exception:
            entry['title'] = ''
        result.append(entry)
    return result


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


class TaijiLaunchButton(QWidget):
    """
    太极阴阳式启动 / 关闭控件：左（绿）＝一键启动，右（红）＝关闭全部。

    造型按太极图的几何构造绘制：
      · 整圆半径 R，被 S 形曲线分成两条"鱼"——
        上半个 S = 小圆（圆心在正上方 R/2、半径 R/2）的右半圆，
        下半个 S = 小圆（圆心在正下方 R/2、半径 R/2）的左半圆；
      · 两条鱼之间留 `gap` 像素的真实缝隙（用 QPainterPathStroker 从鱼形里减掉），
        点在缝隙上不响应；
      · 鱼眼用对比色：左鱼（绿）嵌红眼、右鱼（红）嵌绿眼；
      · 凹凸感靠"边缘浮雕"实现——沿鱼形路径用对角线渐变画笔描边（左上白 → 右下黑），
        再叠顶部镜面高光与底部内阴影，观感像两枚压铸出来的实体按键；
      · 文字竖排：每个字单独居中绘制、自上而下排列，不做旋转。
    """

    run_requested = pyqtSignal()
    close_requested = pyqtSignal()

    # 每个半区三段色：高光 / 本色 / 暗部（偏沉稳的玉石绿与朱砂红，避免糖果色）
    RUN_COLORS = ('#75C39B', '#2B815C', '#114835')
    CLOSE_COLORS = ('#D98C7A', '#AB4132', '#5D1A12')
    IDLE_COLORS = ('#E9E9E9', '#C8C8C8', '#9E9E9E')

    def __init__(self, diameter=160, parent=None):
        super().__init__(parent)
        self._d = int(diameter)
        self._margin = 16                     # 留给落影
        self._gap = 5                         # 两条鱼之间的缝隙
        self._cache = None
        self.setFixedSize(self._d + self._margin * 2, self._d + self._margin * 2)
        self.setMouseTracking(True)
        self.setCursor(Qt.PointingHandCursor)
        self.setToolTip('左（绿）：一键启动当前预设　|　右（红）：关闭列表内的程序与文件夹窗口')
        self._hover = None
        self._pressed = None
        self._run_enabled = True
        self._close_enabled = True

    # ------------------------- 对外接口 -------------------------

    def set_run_enabled(self, enabled):
        self._run_enabled = bool(enabled)
        if not self._run_enabled and self._hover == 'run':
            self._hover = None
        self.update()

    def is_run_enabled(self):
        return self._run_enabled

    def set_close_enabled(self, enabled):
        self._close_enabled = bool(enabled)
        self.update()

    # ------------------------- 几何 -------------------------

    def _geometry(self):
        """
        返回 (圆外框, 左鱼路径, 右鱼路径, 两只鱼眼中心, 鱼眼半径)。

        S 形分割按太极图构造：上段小圆的右半圆 + 下段小圆的左半圆。
        路径缓存起来，绘制与命中判定共用同一份几何，避免两者算出不同的边界。
        """
        if self._cache is not None:
            return self._cache

        d = float(self._d)
        r = d / 2.0
        cx = cy = self._margin + r
        big = QRectF(self._margin, self._margin, d, d)
        small_top = QRectF(cx - r / 2.0, cy - r, r, r)      # 圆心 (cx, cy - r/2)
        small_bot = QRectF(cx - r / 2.0, cy, r, r)          # 圆心 (cx, cy + r/2)

        # 左鱼：外圈左半 → 下段 S（小圆左半，自下而上）→ 上段 S（小圆右半，自下而上）
        left = QPainterPath()
        left.moveTo(cx, cy - r)
        left.arcTo(big, 90, 180)
        left.arcTo(small_bot, 270, -180)
        left.arcTo(small_top, 270, 180)
        left.closeSubpath()

        # 右鱼：外圈右半 → 下段 S（小圆右半）→ 上段 S（小圆左半）
        right = QPainterPath()
        right.moveTo(cx, cy - r)
        right.arcTo(big, 90, -180)
        right.arcTo(small_bot, 270, -180)
        right.arcTo(small_top, 270, 180)
        right.closeSubpath()

        # 用 S 曲线的粗描边把两条鱼各切掉一半缝隙，得到真实间隙
        divider = QPainterPath()
        divider.moveTo(cx, cy - r)
        divider.arcTo(small_top, 90, -180)
        divider.arcTo(small_bot, 90, 180)
        stroker = QPainterPathStroker()
        stroker.setWidth(self._gap)
        stroker.setCapStyle(Qt.FlatCap)
        gap = stroker.createStroke(divider)
        left = left.subtracted(gap)
        right = right.subtracted(gap)

        eyes = (QPointF(cx, cy - r / 2.0), QPointF(cx, cy + r / 2.0))
        self._cache = (big, left, right, eyes, r * 0.165, r, cx, cy)
        return self._cache

    def _side_at(self, pos):
        _big, left, right, _eyes, _er, _r, _cx, _cy = self._geometry()
        pt = QPointF(pos)
        if left.contains(pt):
            return 'run'
        if right.contains(pt):
            return 'close'
        return None                       # 圆外或缝隙

    def _side_enabled(self, side):
        if side == 'run':
            return self._run_enabled
        if side == 'close':
            return self._close_enabled
        return False

    # ------------------------- 绘制 -------------------------

    def _palette_for(self, side):
        enabled = self._run_enabled if side == 'run' else self._close_enabled
        base = self.IDLE_COLORS if not enabled else (
            self.RUN_COLORS if side == 'run' else self.CLOSE_COLORS)
        light, main, dark = (QColor(c) for c in base)
        if enabled and self._pressed == side:
            light, main, dark = (c.darker(116) for c in (light, main, dark))
        elif enabled and self._hover == side:
            light, main, dark = (c.lighter(110) for c in (light, main, dark))
        return enabled, light, main, dark

    def _paint_shadow(self, p, big):
        p.save()
        p.setPen(Qt.NoPen)
        for offset, spread, alpha in ((2, 0, 40), (5, 1, 28), (9, 2, 17), (13, 4, 9)):
            r = big.adjusted(-spread, -spread + offset, spread, spread + offset)
            p.setBrush(QColor(0, 0, 0, alpha))
            p.drawEllipse(r)
        p.restore()

    def _paint_fish(self, p, path, side):
        _big, _l, _r, _eyes, _er, radius, cx, cy = self._geometry()
        enabled, light, main, dark = self._palette_for(side)
        rect = self._rect()

        p.save()
        p.setClipPath(path)

        # 1) 主体：对角渐变（左上亮 → 右下暗），统一光源
        grad = QLinearGradient(rect.topLeft(), rect.bottomRight())
        grad.setColorAt(0.0, light)
        grad.setColorAt(0.5, main)
        grad.setColorAt(1.0, dark)
        p.fillPath(path, QBrush(grad))

        # 2) 顶部镜面高光
        spec = QRadialGradient(QPointF(cx - radius * 0.30, cy - radius * 0.45), radius * 0.85)
        spec.setColorAt(0.0, QColor(255, 255, 255, 105 if enabled else 60))
        spec.setColorAt(0.55, QColor(255, 255, 255, 34 if enabled else 18))
        spec.setColorAt(1.0, QColor(255, 255, 255, 0))
        p.fillPath(path, QBrush(spec))

        # 3) 底部内阴影：制造厚度
        shade = QLinearGradient(QPointF(0, cy + radius * 0.15), QPointF(0, rect.bottom()))
        shade.setColorAt(0.0, QColor(0, 0, 0, 0))
        shade.setColorAt(1.0, QColor(0, 0, 0, 78 if enabled else 34))
        p.fillPath(path, QBrush(shade))

        # 4) 边缘浮雕：沿轮廓用对角渐变描边，左上见白、右下见黑
        p.setClipping(False)
        bevel = QLinearGradient(rect.topLeft(), rect.bottomRight())
        bevel.setColorAt(0.0, QColor(255, 255, 255, 190 if enabled else 120))
        bevel.setColorAt(0.42, QColor(255, 255, 255, 0))
        bevel.setColorAt(0.58, QColor(0, 0, 0, 0))
        bevel.setColorAt(1.0, QColor(0, 0, 0, 120 if enabled else 60))
        pen = QPen(QBrush(bevel), 2.6)
        pen.setJoinStyle(Qt.RoundJoin)
        p.setPen(pen)
        p.setBrush(Qt.NoBrush)
        p.drawPath(path)

        # 5) 悬停 / 按下：再补一圈细边，强化"按得动"的手感
        if enabled and (self._hover == side or self._pressed == side):
            rim = QColor(255, 255, 255, 120) if self._pressed != side else QColor(0, 0, 0, 80)
            pen = QPen(rim)
            pen.setWidthF(1.2)
            p.setPen(pen)
            p.drawPath(path)
        p.restore()

    def _paint_eye(self, p, center, eye_r, colors, enabled):
        light, _main, dark = (QColor(c) for c in colors)
        p.save()
        # 阴影
        p.setPen(Qt.NoPen)
        p.setBrush(QColor(0, 0, 0, 70 if enabled else 30))
        p.drawEllipse(center + QPointF(0, 1.2), eye_r, eye_r)
        # 主体
        g = QLinearGradient(center + QPointF(-eye_r, -eye_r), center + QPointF(eye_r, eye_r))
        g.setColorAt(0.0, light.lighter(112))
        g.setColorAt(1.0, dark)
        p.setBrush(QBrush(g))
        p.drawEllipse(center, eye_r, eye_r)
        # 浮雕边
        bevel = QLinearGradient(center + QPointF(-eye_r, -eye_r), center + QPointF(eye_r, eye_r))
        bevel.setColorAt(0.0, QColor(255, 255, 255, 150))
        bevel.setColorAt(0.5, QColor(255, 255, 255, 0))
        bevel.setColorAt(1.0, QColor(0, 0, 0, 110))
        pen = QPen(QBrush(bevel), 1.4)
        p.setPen(pen)
        p.setBrush(Qt.NoBrush)
        p.drawEllipse(center, eye_r, eye_r)
        p.restore()

    def _paint_text(self, p):
        _big, _l, _r, _eyes, _er, radius, cx, cy = self._geometry()
        font = QFont(self.font())
        font.setWeight(QFont.DemiBold)
        font.setPixelSize(max(13, int(radius * 0.36)))
        p.save()
        p.setFont(font)
        fm = p.fontMetrics()
        line_h = int(fm.height() * 1.02)

        # 文字放在各自的"鱼身"里：左鱼靠左上、右鱼靠右下，
        # 这样两字竖排不会压到中间的 S 形缝隙（鱼身在这个位置最宽）。
        for side, text in (('run', '启动'), ('close', '关闭')):
            enabled = self._run_enabled if side == 'run' else self._close_enabled
            if side == 'run':
                x, base_y = cx - radius * 0.42, cy - radius * 0.26
            else:
                x, base_y = cx + radius * 0.42, cy + radius * 0.26
            for i, ch in enumerate(text):
                offset = (i - (len(text) - 1) / 2.0) * line_h
                box = QRectF(x - radius * 0.30, base_y + offset - line_h / 2.0,
                             radius * 0.60, line_h)
                # 浮雕字：先画右下暗影，再画亮面；禁用时改用深灰字，避免白字糊在浅灰上
                if enabled:
                    p.setPen(QColor(0, 0, 0, 95))
                    p.drawText(box.translated(0.6, 1.1), Qt.AlignCenter, ch)
                    p.setPen(QColor(255, 255, 255, 245))
                else:
                    p.setPen(QColor(255, 255, 255, 130))
                    p.drawText(box.translated(0.6, 1.1), Qt.AlignCenter, ch)
                    p.setPen(QColor(110, 110, 110, 215))
                p.drawText(box, Qt.AlignCenter, ch)
        p.restore()

    def _rect(self):
        return QRectF(self._margin, self._margin, self._d, self._d)

    def paintEvent(self, event):
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing, True)
        p.setRenderHint(QPainter.TextAntialiasing, True)
        big, left, right, eyes, eye_r, _radius, _cx, _cy = self._geometry()

        self._paint_shadow(p, big)
        # 把圆内区域先填成控件底色，避免落影从缝隙里透出来
        p.setPen(Qt.NoPen)
        p.setBrush(self.palette().color(self.backgroundRole()))
        p.drawEllipse(big)

        self._paint_fish(p, left, 'run')
        self._paint_fish(p, right, 'close')

        # 缝隙投影：沿 S 曲线在缝内压一道淡影，两块才像真的分开而不是画上去的
        _big, _l, _r, _eyes, _er, _radius, _cx, _cy = self._geometry()
        divider = QPainterPath()
        divider.moveTo(_cx, _cy - _radius)
        divider.arcTo(QRectF(_cx - _radius / 2.0, _cy - _radius, _radius, _radius), 90, -180)
        divider.arcTo(QRectF(_cx - _radius / 2.0, _cy, _radius, _radius), 90, 180)
        p.save()
        p.setBrush(Qt.NoBrush)
        pen = QPen(QColor(0, 0, 0, 32))
        pen.setWidthF(1.6)
        pen.setCapStyle(Qt.FlatCap)
        p.setPen(pen)
        p.translate(1.0, 1.6)
        p.drawPath(divider)
        p.restore()

        # 鱼眼：左鱼嵌红点、右鱼嵌绿点
        self._paint_eye(p, eyes[0], eye_r, self.CLOSE_COLORS, self._run_enabled)
        self._paint_eye(p, eyes[1], eye_r, self.RUN_COLORS, self._close_enabled)

        self._paint_bezel(p, big)
        self._paint_text(p)
        p.end()

    def _paint_bezel(self, p, big):
        """外圈包边：左上亮、右下暗，让整个圆盘像嵌在面板上。"""
        p.save()
        p.setBrush(Qt.NoBrush)
        ring = QLinearGradient(big.topLeft(), big.bottomRight())
        ring.setColorAt(0.0, QColor(255, 255, 255, 165))
        ring.setColorAt(0.45, QColor(255, 255, 255, 25))
        ring.setColorAt(0.6, QColor(0, 0, 0, 35))
        ring.setColorAt(1.0, QColor(0, 0, 0, 95))
        pen = QPen(QBrush(ring), 2.2)
        p.setPen(pen)
        p.drawEllipse(big.adjusted(1.1, 1.1, -1.1, -1.1))
        p.restore()

    # ------------------------- 交互 -------------------------

    def mouseMoveEvent(self, event):
        side = self._side_at(event.pos())
        if not self._side_enabled(side):
            side = None
        if side != self._hover:
            self._hover = side
            self.update()
        super().mouseMoveEvent(event)

    def leaveEvent(self, event):
        if self._hover is not None:
            self._hover = None
            self.update()
        super().leaveEvent(event)

    def mousePressEvent(self, event):
        if event.button() != Qt.LeftButton:
            return
        side = self._side_at(event.pos())
        self._pressed = side if self._side_enabled(side) else None
        self.update()

    def mouseReleaseEvent(self, event):
        if event.button() != Qt.LeftButton:
            return
        side = self._side_at(event.pos())
        pressed = self._pressed
        self._pressed = None
        self.update()
        if side and side == pressed and self._side_enabled(side):
            if side == 'run':
                self.run_requested.emit()
            else:
                self.close_requested.emit()

class LauncherWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        setup_logging()
        install_exception_hooks()
        log.info('启动 v%s | frozen=%s | exe=%s | 配置目录=%s | 日志=%s',
                 APP_VERSION, getattr(sys, 'frozen', False), sys.executable, CONFIG_DIR, LOG_FILE)

        self.setWindowTitle('一键多启')
        self.setAcceptDrops(True)

        if getattr(sys, 'frozen', False):
            icon_path = os.path.join(sys._MEIPASS, 'logo.ico')
        else:
            # 源码运行时图标在仓库的 assets/ 目录（src/ 的上一级）
            icon_path = os.path.join(
                os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                'assets', 'logo.ico')
        if os.path.exists(icon_path):
            self.setWindowIcon(QIcon(icon_path))

        self.presets = {}
        self.current_preset_name = ''

        self.launched_items = []
        self.global_macro = []
        self.last_folder = ''          # 上次使用的文件夹，供选择框/手动输入定位

        # 某些程序的“关不掉”附加进程名（例如 Steam 中转的脚本）
        self.special_kill_map = {
            'start_without_steam.bat': ['VTube Studio.exe']
        }

        self.load_config()

        # 启动并发控制
        self._launch_thread = None
        self._launching = False
        self._launch_lock = threading.Lock()
        self._stop_launch = False

        # 预设行
        self.preset_label = QLabel('预设方案：')
        self.preset_combo = QComboBox()
        self.preset_combo.setEditable(False)
        self.btn_new_preset = QPushButton('➕ 新建')
        self.btn_del_preset = QPushButton('❌ 删除')

        preset_layout = QHBoxLayout()
        preset_layout.addWidget(self.preset_label)
        preset_layout.addWidget(self.preset_combo, 1)
        preset_layout.addWidget(self.btn_new_preset)
        preset_layout.addWidget(self.btn_del_preset)

        # 程序列表
        self.list_widget = QListWidget()
        self.list_widget.setSelectionMode(QAbstractItemView.ExtendedSelection)
        self.list_widget.setDragDropMode(QAbstractItemView.DropOnly)
        self.list_widget.setDefaultDropAction(Qt.CopyAction)

        # 添加 / 删除（第一行）
        self.btn_add = QPushButton('📂 添加程序')
        self.btn_add_folder = QPushButton('📁 添加文件夹')
        self.btn_add_path = QPushButton('✏ 输入路径')
        self.btn_del = QPushButton('🗑 删除选中')

        add_layout = QHBoxLayout()
        for b in (self.btn_add, self.btn_add_folder, self.btn_add_path, self.btn_del):
            add_layout.addWidget(b, 1)

        # 太极式启动 / 关闭：单独占据顶部区域，不与其它功能按钮混排
        self.taiji = TaijiLaunchButton(160)

        taiji_row = QHBoxLayout()
        taiji_row.addStretch(1)
        taiji_row.addWidget(self.taiji)
        taiji_row.addStretch(1)

        # 全局宏按钮
        self.btn_record_global = QPushButton('🎬 录制总宏')
        self.btn_play_global = QPushButton('▶ 播放总宏')
        self.btn_clear_global = QPushButton('🗑 清除总宏')

        macro_layout = QHBoxLayout()
        macro_layout.addWidget(self.btn_record_global)
        macro_layout.addWidget(self.btn_play_global)
        macro_layout.addWidget(self.btn_clear_global)
        macro_layout.addStretch()
        self.btn_log = QPushButton('🗒 日志')
        macro_layout.addWidget(self.btn_log)

        # 布局
        central = QWidget()
        self.setCentralWidget(central)
        layout = QVBoxLayout(central)
        layout.setContentsMargins(12, 10, 12, 12)
        layout.setSpacing(10)
        layout.addLayout(taiji_row)
        layout.addLayout(preset_layout)
        layout.addWidget(self.list_widget)
        layout.addLayout(add_layout)
        layout.addLayout(macro_layout)

        # 填充预设下拉框
        self.preset_combo.addItems(self.presets.keys())
        if self.current_preset_name in self.presets:
            self.preset_combo.setCurrentText(self.current_preset_name)
        else:
            if self.preset_combo.count() > 0:
                self.current_preset_name = self.preset_combo.currentText()
            else:
                self.presets['默认方案'] = []
                self.preset_combo.addItem('默认方案')
                self.current_preset_name = '默认方案'
                self.preset_combo.setCurrentText('默认方案')

        self.load_current_preset_list()

        # 信号连接
        self.preset_combo.currentTextChanged.connect(self.on_preset_changed)
        self.btn_new_preset.clicked.connect(self.new_preset_dialog)
        self.btn_del_preset.clicked.connect(self.delete_current_preset)
        self.btn_add.clicked.connect(self.add_program_dialog)
        self.btn_add_folder.clicked.connect(self.add_folder_dialog)
        self.btn_add_path.clicked.connect(self.add_path_manually)
        self.btn_del.clicked.connect(self.remove_selected)
        self.taiji.run_requested.connect(self.launch_all)
        self.list_widget.itemDoubleClicked.connect(self.on_item_double_clicked)
        self.taiji.close_requested.connect(self.close_all_programs)

        self.btn_record_global.clicked.connect(self.record_global_macro)
        self.btn_play_global.clicked.connect(self.play_global_macro)
        self.btn_clear_global.clicked.connect(self.clear_global_macro)
        self.btn_log.clicked.connect(self.open_log_dir)

        # 说明：不在此处做任何自动启动。启动器打开时只呈现界面，
        # 必须由用户点击「🚀 一键启动」才会运行列表内的条目。


    def _get_all_pids(self):
        """返回当前系统所有进程PID的集合"""
        try:
            output = subprocess.check_output(
                ['tasklist', '/fo', 'csv', '/nh'],
                **hidden_subprocess_kwargs()).decode('gbk')
            pids = set()
            for line in output.splitlines():
                parts = line.split(',')
                if len(parts) >= 2:
                    pid_str = parts[1].strip('"')
                    if pid_str.isdigit():
                        pids.add(int(pid_str))
            return pids
        except Exception:
            return set()


    def on_item_double_clicked(self, item):
        path = item.data(Qt.UserRole)
        if entry_kind(path) == 'missing':
            QMessageBox.warning(self, '无法打开', '该路径已不存在：\n%s' % path)
            return
        try:
            result = launch_program(path)
            if result:
                proc, resolved = result
                self.launched_items.append((proc, resolved, self.current_preset_name, []))
        except Exception as e:
            QMessageBox.warning(self, '启动失败', str(e))


    def record_global_macro(self):
        if not HAS_PYNPUT:
            QMessageBox.warning(self, '无法录制', '请先安装 pynput (pip install pynput)')
            return
        dlg = MacroRecorderDialog(self)
        if dlg.exec_() == QDialog.Accepted or dlg.get_events():
            self.global_macro = dlg.get_events()
            QMessageBox.information(self, '成功', f'全局宏已保存，共 {len(self.global_macro)} 个事件。')
            self.save_config()
        else:
            QMessageBox.information(self, '取消', '未录制任何事件。')

    def clear_global_macro(self):
        if self.global_macro:
            reply = QMessageBox.question(self, '清除宏', '确定要清除当前全局宏吗？',
                                         QMessageBox.Yes | QMessageBox.No)
            if reply == QMessageBox.Yes:
                self.global_macro = []
                self.save_config()
                QMessageBox.information(self, '已清除', '全局宏已清除。')
        else:
            QMessageBox.information(self, '提示', '当前没有全局宏。')

    def play_global_macro(self):
        if not self.global_macro:
            QMessageBox.information(self, '提示', '当前没有全局宏。')
            return
        if not (HAS_PYNPUT and HAS_WIN32GUI):
            QMessageBox.warning(self, '错误', 'pynput 或 pywin32 缺失，无法播放宏。')
            return
        def run():
            self._play_macro(self.global_macro)

        threading.Thread(target=run, daemon=True).start()
    def _play_macro(self, macro):
        """实际播放宏的函数（内部使用）"""
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

    def save_current_list_to_preset(self):
        if not self.current_preset_name:
            return
        paths = [self.list_widget.item(i).data(Qt.UserRole) for i in range(self.list_widget.count())]
        self.presets[self.current_preset_name] = paths

    def load_current_preset_list(self):
        """
        按预设重建列表。

        路径已失效的条目（文件夹被移走、程序被卸载）不再静默丢弃，而是以 ⚠ 显示，
        这样预设不会因为一次加载就被 save_current_list_to_preset 永久抹掉。
        """
        self.list_widget.clear()
        paths = self.presets.get(self.current_preset_name, [])
        for p in paths:
            if not p:
                continue
            self.add_to_list(p, update_preset=False)
    def on_preset_changed(self, new_name):
        if not new_name or new_name == self.current_preset_name:
            return
        self.save_current_list_to_preset()
        self.current_preset_name = new_name
        self.load_current_preset_list()
        self.save_config()

    def new_preset_dialog(self):
        name, ok = QInputDialog.getText(self, '新建预设', '请输入预设名称：')
        if not ok or not name.strip():
            return
        name = name.strip()
        if name in self.presets:
            QMessageBox.warning(self, '错误', '预设名称已存在！')
            return
        self.save_current_list_to_preset()
        self.presets[name] = []
        self.preset_combo.addItem(name)
        self.preset_combo.setCurrentText(name)
        self.save_config()

    def delete_current_preset(self):
        if self.preset_combo.count() <= 1:
            QMessageBox.information(self, '提示', '至少保留一个预设方案。')
            return
        reply = QMessageBox.question(self, '删除预设',
                                     f'确定要删除预设“{self.current_preset_name}”吗？',
                                     QMessageBox.Yes | QMessageBox.No)
        if reply != QMessageBox.Yes:
            return
        del self.presets[self.current_preset_name]
        self.preset_combo.blockSignals(True)
        self.preset_combo.removeItem(self.preset_combo.currentIndex())
        self.preset_combo.blockSignals(False)
        new_name = self.preset_combo.currentText()
        self.current_preset_name = new_name
        self.load_current_preset_list()
        self.save_config()


    def add_to_list(self, path, update_preset=True):
        """
        加入列表（程序 / 文件 / 文件夹均可）。

        去重按规范化后的路径判断，避免 C:/a 与 C:\\a 被当成两条。
        返回 True 表示新增成功，False 表示已存在或路径无效。
        """
        path = normalize_input_path(path)
        if not path:
            return False

        key = os.path.normcase(os.path.normpath(path))
        for i in range(self.list_widget.count()):
            exist = self.list_widget.item(i).data(Qt.UserRole)
            if exist and os.path.normcase(os.path.normpath(exist)) == key:
                return False

        item = QListWidgetItem(entry_label(path))
        item.setData(Qt.UserRole, path)
        item.setToolTip(entry_tooltip(path))
        self.list_widget.addItem(item)

        if update_preset and self.current_preset_name:
            if path not in self.presets[self.current_preset_name]:
                self.presets[self.current_preset_name].append(path)
            self.save_config()
        return True

    def _start_dir(self):
        """文件/文件夹选择框的起始位置：上次用过的目录，否则用户主目录。"""
        if self.last_folder and os.path.isdir(self.last_folder):
            return self.last_folder
        return os.path.expanduser('~')

    def add_program_dialog(self):
        paths, _ = QFileDialog.getOpenFileNames(
            self,
            '选择要添加的程序或文件',
            self._start_dir(),
            '程序 (*.exe *.lnk *.bat *.cmd);;所有文件 (*)'
        )
        added = 0
        for p in paths:
            if self.add_to_list(p, update_preset=True):
                added += 1
                self.last_folder = os.path.dirname(normalize_input_path(p))
        if added:
            self.save_config()

    def add_folder_dialog(self):
        folder = QFileDialog.getExistingDirectory(
            self, '选择要添加的文件夹', self._start_dir(), QFileDialog.ShowDirsOnly)
        if not folder:
            return
        folder = normalize_input_path(folder)
        if not os.path.isdir(folder):
            QMessageBox.warning(self, '无法添加', '所选目录不存在或不可访问：\n' + folder)
            return
        if self.add_to_list(folder, update_preset=True):
            self.last_folder = folder
            self.save_config()
        else:
            QMessageBox.information(self, '提示', '该文件夹已在列表中。')

    def add_path_manually(self):
        """
        手动输入路径：默认填入上次使用的文件夹，支持粘贴带引号的路径与环境变量。
        """
        default = self.last_folder if os.path.isdir(self.last_folder or '') else os.path.expanduser('~')
        text, ok = QInputDialog.getText(
            self,
            '输入路径',
            '程序 / 文件 / 文件夹的完整路径（支持 %USERPROFILE% 等环境变量）：',
            text=default
        )
        if not ok:
            return
        path = normalize_input_path(text)
        if not path:
            return
        if not os.path.exists(path):
            QMessageBox.warning(self, '路径无效', '该路径不存在：\n%s' % path)
            return
        if not self.add_to_list(path, update_preset=True):
            QMessageBox.information(self, '提示', '该路径已在列表中。')
            return
        self.last_folder = path if os.path.isdir(path) else os.path.dirname(path)
        self.save_config()

    def remove_selected(self):
        for item in self.list_widget.selectedItems():
            path = item.data(Qt.UserRole)
            self.list_widget.takeItem(self.list_widget.row(item))
            if not self.current_preset_name:
                continue
            if not path in self.presets[self.current_preset_name]:
                continue
            self.presets[self.current_preset_name].remove(path)
        self.save_config()
    def launch_all(self):
        if self._launching:
            QMessageBox.information(self, '提示', '正在启动中，请稍候...')
            return
        if self.list_widget.count() == 0:
            return

        paths = [self.list_widget.item(i).data(Qt.UserRole) for i in range(self.list_widget.count())]
        log.info('一键启动：预设=%s，共 %d 项', self.current_preset_name, len(paths))

        self.taiji.set_run_enabled(False)
        self._launching = True
        self._stop_launch = False

        self._launch_thread = threading.Thread(
            target=self._launch_worker,
            args=(self.current_preset_name, paths),
            daemon=True
        )
        self._launch_thread.start()
    def _launch_worker(self, preset_name, paths):
        """后台线程：顺序启动所有程序，对bat/cmd捕获新增进程PID；文件夹汇总到一个多标签窗口"""
        try:
            folders = []
            for path in paths:
                if self._stop_launch:
                    break
                if entry_kind(path) == 'missing':
                    continue                      # 路径已失效，跳过
                if os.path.isdir(path):
                    folders.append(path)          # 文件夹延后统一打开，避免弹出多个窗口
                    continue
                ext = os.path.splitext(path)[1].lower()
                extra_pids = []
                if ext in ('.bat', '.cmd'):
                    # 批处理会启动子进程，用启动前后的 PID 差集来捕获
                    before = self._get_all_pids()
                    result = launch_program(path)

                    time.sleep(2)
                    after = self._get_all_pids()
                    extra_pids = list(after - before)
                    if result:
                        proc, resolved = result
                        with self._launch_lock:
                            self.launched_items.append((proc, resolved, preset_name, extra_pids))
                    else:
                        with self._launch_lock:
                            self.launched_items.append((None, path, preset_name, extra_pids))
                else:

                    try:
                        log.info('启动条目：%s', path)
                        result = launch_program(path)
                        if result:
                            proc, resolved = result
                            log.info('启动成功：%s → pid=%s（解析为 %s）',
                                     path, getattr(proc, 'pid', None), resolved)
                            with self._launch_lock:
                                self.launched_items.append((proc, resolved, preset_name, []))
                        else:
                            log.info('启动完成但未取得 PID：%s（由系统关联程序打开）', path)
                    except Exception:
                        log.exception('启动失败：%s', path)

            # 文件夹一律交给系统资源管理器打开（每个文件夹一个窗口）
            for folder in folders:
                if self._stop_launch:
                    break
                try:
                    log.info('打开文件夹（资源管理器）：%s', folder)
                    launch_program(folder)
                except Exception:
                    log.exception('打开文件夹失败：%s', folder)

            # 启动完成后自动播放全局宏
            if not self._stop_launch and self.global_macro and HAS_PYNPUT and HAS_WIN32GUI:
                time.sleep(2)
                QTimer.singleShot(0, self._auto_play_global_macro)
        finally:
            QTimer.singleShot(0, self._launch_finished)
    def _auto_play_global_macro(self):
        if self.global_macro:
            def run():
                self._play_macro(self.global_macro)

            threading.Thread(target=run, daemon=True).start()
    def _launch_finished(self):
        self._launching = False
        self.taiji.set_run_enabled(True)

    # ------------------------- 关闭程序 -------------------------

    def _get_process_map(self):
        """采集当前进程快照，返回 {镜像名小写: {pid, ...}}；失败返回空字典。"""
        try:
            output = subprocess.check_output(
                ['tasklist', '/fo', 'csv', '/nh'],
                **hidden_subprocess_kwargs()).decode('gbk', errors='ignore')
            result = {}
            for row in csv.reader(output.splitlines()):
                if len(row) >= 2 and row[1].strip().isdigit():
                    result.setdefault(row[0].strip().lower(), set()).add(int(row[1]))
            return result
        except Exception:
            return {}

    def _close_targets(self, paths):
        """
        把列表条目解析为可关闭目标 [(原路径, 镜像名)]。
        文件夹与无法按镜像名判定的脚本类（.bat/.cmd）镜像名为 None。
        """
        targets = []
        for p in paths:
            if not p:
                continue
            if os.path.isdir(p):
                continue                      # 文件夹不参与"关闭程序"
            try:
                resolved = resolve_lnk(p)
            except Exception:
                resolved = p
            ext = os.path.splitext(resolved)[1].lower()
            if ext in ('.exe', '.com'):
                targets.append((p, os.path.basename(resolved)))
            else:
                targets.append((p, None))     # .bat/.cmd 等，进程名是 cmd.exe
        return targets

    def _find_launched(self, path):
        """在本会话的启动记录里查找与 path 对应的条目，找不到返回 None。"""
        try:
            resolved = resolve_lnk(path)
        except Exception:
            resolved = path
        key = os.path.normcase(os.path.normpath(resolved))
        for item in list(self.launched_items):
            target = item[1]
            if target and os.path.normcase(os.path.normpath(target)) == key:
                return item
        return None

    @staticmethod
    def _taskkill(args):
        """
        执行 taskkill，返回 (是否成功, 退出码, 输出)。

        与旧版的区别：不再吞掉错误。GUI 下用户看不到控制台，失败原因必须进日志，
        因此命令、退出码与原始输出都记录，供「关闭失败」时定位。
        """
        cmd = ['taskkill'] + list(args)
        try:
            res = subprocess.run(cmd, capture_output=True, timeout=10,
                                 **hidden_subprocess_kwargs())
            output = decode_console((res.stdout or b'') + (res.stderr or b''))
            text = output.replace('\r', '').replace('\n', ' | ').strip()
            log.info('taskkill %s → rc=%s %s',
                     ' '.join(str(a) for a in args), res.returncode, text)
            return res.returncode == 0, res.returncode, output
        except Exception as e:
            log.exception('taskkill %s 执行异常', ' '.join(str(a) for a in args))
            return False, -1, str(e)

    @staticmethod
    def _is_access_denied(text):
        low = (text or '').lower()
        return ('拒绝访问' in (text or '')) or ('access is denied' in low) or ('access denied' in low)

    def _wait_until_gone(self, images, timeout=3.0):
        """
        轮询确认进程是否真的退出。

        taskkill /f 返回成功不等于进程立刻消失（尤其是 Electron 这类多进程应用），
        立即复查会产生"明明关了却报失败"的误判。
        """
        pending = {i.lower() for i in images if i}
        if not pending:
            return set()
        deadline = time.time() + timeout
        while True:
            current = self._get_process_map()
            pending = {i for i in pending if i in current}
            if not pending or time.time() >= deadline:
                return pending
            time.sleep(0.25)

    @staticmethod
    def _window_label(win_info):
        """窗口的可读标识：单标签取文件夹名，多标签额外标注标签数。"""
        paths = [p for p in (win_info.get('paths') or []) if p]
        names = []
        for p in paths[:3]:
            name = os.path.basename(str(p).rstrip('\\/'))
            names.append(name or str(p))
        label = '、'.join(names)
        if len(paths) > 3:
            label += ' 等'
        if len(paths) > 1:
            label += '（%d 个标签）' % len(paths)
        return label or ('窗口 %s' % win_info.get('hwnd'))

    def _folder_window_plan(self, folder_paths):
        """
        把列表中的文件夹条目对应到资源管理器窗口。

        返回 (closable, mixed)：
          closable —— 窗口内所有标签都属于列表条目，可直接整窗关闭
          mixed    —— 混有列表外的标签，整窗关闭会连带关掉别的标签，需用户确认
        只按"路径"判定，不依赖打开时记录的 HWND：用户把窗口拖进另一窗口合并成标签后，
        原 HWND 会消失，任何基于 HWND 的记录都会失效。
        """
        targets = {_norm_fs_path(p) for p in folder_paths if p}
        closable, mixed = [], []
        if not targets:
            return closable, mixed
        for win_info in list_explorer_windows():
            hits, foreign = [], []
            for p in win_info['paths']:
                np = _norm_fs_path(p)
                if np and np in targets:
                    hits.append(p)
                else:
                    foreign.append(p)
            if not hits:
                continue
            item = dict(win_info)
            if foreign:
                item['foreign'] = foreign
                mixed.append(item)
            else:
                closable.append(item)
        return closable, mixed

    def _close_folder_window(self, win_info):
        """
        整窗关闭一个资源管理器窗口，返回 (是否关闭, 说明)。

        多标签窗口不能一次关掉：实测 WM_CLOSE 只关闭"当前活动标签"，
        每关掉一个标签窗口就少一条记录，因此按标签数循环发送并复查；
        单标签窗口一次即可整窗消失。Quit() 在多标签场景下实测无效，故不使用。
        """
        if not HAS_WIN32GUI:
            return False, '缺少 pywin32，无法关闭窗口'
        hwnd = win_info.get('hwnd')
        if not hwnd:
            return False, '没有窗口句柄'

        tabs = max(1, len(win_info.get('paths') or []))
        deadline = time.time() + 3.0 + 0.8 * tabs
        attempts = 0
        last_remaining = tabs
        while time.time() < deadline:
            try:
                if not win32gui.IsWindow(hwnd):
                    return True, 'attempts=%d' % attempts
                win32gui.PostMessage(hwnd, win32con.WM_CLOSE, 0, 0)
            except Exception as e:
                return False, '发送关闭消息异常：%s' % e
            attempts += 1
            time.sleep(0.3)
            try:
                alive = bool(win32gui.IsWindow(hwnd))
                remaining = sum(1 for w in list_explorer_windows() if w['hwnd'] == hwnd)
            except Exception:
                alive, remaining = True, last_remaining
            if not alive or remaining == 0:
                return True, 'attempts=%d' % attempts
            if remaining >= last_remaining and attempts >= 2:
                # 连续两次标签数没有减少，说明关不动（被拦截或无响应），不再空转
                return False, 'attempts=%d remaining=%d' % (attempts, remaining)
            last_remaining = remaining

        try:
            return (not win32gui.IsWindow(hwnd)), 'attempts=%d remaining=%d' % (attempts, last_remaining)
        except Exception:
            return False, 'attempts=%d 复查失败' % attempts

    def close_all_programs(self):
        """
        关闭列表内的程序与文件夹窗口。

        流程：确认 → 检测运行状态/窗口状态（未运行、找不到窗口的跳过）→ 逐项关闭 → 汇总。
        与旧版的区别：
          · 不再只处理本次会话启动的进程，也不再关闭启动器自身；
          · 文件夹条目改为关闭其资源管理器窗口（整窗关闭，不结束 explorer.exe）；
          · 窗口内混有列表外标签时单独询问，用户拒绝则跳过，绝不擅自连带关闭。
        """
        paths = []
        for i in range(self.list_widget.count()):
            p = self.list_widget.item(i).data(Qt.UserRole)
            if p:
                paths.append(p)

        if not paths:
            QMessageBox.information(self, '提示', '列表为空，没有需要关闭的程序。')
            return

        # 文件夹条目单独处理：它们是"窗口"，不是"进程"
        folder_paths = [p for p in paths if os.path.isdir(p)]
        program_paths = [p for p in paths if not os.path.isdir(p)]

        proc_map = self._get_process_map()
        own_name = os.path.basename(sys.executable).lower() if getattr(sys, 'frozen', False) else None
        log.info('关闭检查开始：列表 %d 项（程序 %d / 文件夹 %d），进程快照 %d 种镜像',
                 len(paths), len(program_paths), len(folder_paths), len(proc_map))

        running = []      # [(path, image)]
        skipped = []      # [(path, reason)]
        for path, image in self._close_targets(program_paths):
            if entry_kind(path) == 'missing':
                skipped.append((path, '路径已不存在'))
                continue
            launched = self._find_launched(path)
            if launched is not None:
                pid = getattr(launched[0], 'pid', None) if launched[0] else None
                # 记录里的 PID 可能早已失效（单实例应用会把请求转交给已有进程后自行退出），
                # 因此不能只看"有记录"就认定为运行中，必须确认镜像仍在快照里。
                if pid and self._pid_in_map(pid, proc_map):
                    running.append((path, image))
                    continue
                if launched[3] and any(self._pid_in_map(p, proc_map) for p in launched[3]):
                    running.append((path, image))
                    continue
                log.info('%s：记录的启动 PID 已失效，改按镜像名判定', get_display_name(path))
            if image is None:
                skipped.append((path, '脚本类且非本次启动，无法判定'))
                continue
            if own_name and image.lower() == own_name:
                skipped.append((path, '启动器自身'))
                continue
            if image.lower() in proc_map:
                running.append((path, image))
            else:
                skipped.append((path, '未运行'))

        closable, mixed = self._folder_window_plan(folder_paths)

        log.info('判定结果：运行中程序 %d 项 %s；可整窗关闭的窗口 %d 个 %s；混有列表外标签 %d 个 %s；程序跳过 %d 项'
                 ' %s',
                 len(running), [os.path.basename(p) for p, _ in running],
                 len(closable), [self._window_label(w) for w in closable],
                 len(mixed), [self._window_label(w) for w in mixed],
                 len(skipped), [(os.path.basename(p), r) for p, r in skipped])

        if not running and not closable and not mixed:
            QMessageBox.information(
                self, '无需关闭',
                '列表中的程序当前都没有在运行，也没有找到对应的文件夹窗口，已全部跳过。\n\n'
                '共检查 %d 个程序、%d 个文件夹。' % (len(program_paths), len(folder_paths)))
            return

        # 列表里有、但当前没打开的文件夹（用于结果说明，不参与关闭）
        matched = set()
        for w in closable + mixed:
            for p in w['paths']:
                np = _norm_fs_path(p)
                if np:
                    matched.add(np)
        unopened = [p for p in folder_paths if _norm_fs_path(p) not in matched]

        sections = []
        if running:
            names = [get_display_name(p) for p, _ in running]
            detail = '\n'.join('· ' + n for n in names[:12])
            if len(names) > 12:
                detail += '\n· …等共 %d 个' % len(names)
            sections.append('程序 %d 个（正在运行）：\n%s' % (len(running), detail))
        if closable:
            labels = ['· ' + self._window_label(w) for w in closable[:8]]
            if len(closable) > 8:
                labels.append('· …等共 %d 个窗口' % len(closable))
            sections.append('文件夹窗口 %d 个（整窗关闭）：\n%s' % (len(closable), '\n'.join(labels)))

        text = '以下内容将被关闭：\n\n' + '\n\n'.join(sections)
        if mixed:
            text += '\n\n另有 %d 个文件夹窗口混有列表外的标签，稍后单独询问。' % len(mixed)
        if skipped:
            text += '\n\n另有 %d 项未运行或无法判定，将自动跳过。' % len(skipped)
        if unopened:
            text += '\n其中 %d 个文件夹当前没有打开的窗口，自然跳过。' % len(unopened)
        text += '\n\n关闭后不可恢复，请确认已保存工作。'

        reply = QMessageBox.question(self, '确认关闭', text,
                                     QMessageBox.Yes | QMessageBox.No,
                                     QMessageBox.No)
        if reply != QMessageBox.Yes:
            return

        # 混有列表外标签的窗口：逐一询问太吵，一次列清，同意则整窗关闭，不同意则整体跳过
        close_mixed = []
        skipped_windows = []
        if mixed:
            lines = []
            for w in mixed[:8]:
                foreign = [os.path.basename(str(p).rstrip('\\/')) or str(p)
                           for p in w.get('foreign', []) if p]
                shown = '、'.join(foreign[:3]) + ('…' if len(foreign) > 3 else '')
                lines.append('· %s，另有 %d 个标签：%s' % (self._window_label(w), len(foreign), shown))
            if len(mixed) > 8:
                lines.append('· …等共 %d 个窗口' % len(mixed))

            reply2 = QMessageBox.question(
                self, '窗口含其他标签',
                '以下 %d 个文件夹窗口里还有不属于本列表的标签：\n\n%s\n\n'
                '整窗关闭会把这些标签一起关掉（它们的文件不会被删除）。\n'
                '是否一并关闭？\n\n'
                '「是」= 整窗关闭；「否」= 跳过这些窗口，其余内容照常关闭。'
                % (len(mixed), '\n'.join(lines)),
                QMessageBox.Yes | QMessageBox.No,
                QMessageBox.No)
            if reply2 == QMessageBox.Yes:
                close_mixed = mixed
            else:
                skipped_windows = [(self._window_label(w), '含列表外标签，按你的选择跳过')
                                   for w in mixed]
                log.info('用户选择跳过混合标签窗口 %d 个', len(mixed))

        # 先中止可能仍在进行的启动流程，避免"一边启动一边关闭"
        self._stop_launch = True
        if self._launch_thread and self._launch_thread.is_alive():
            self._launch_thread.join(timeout=1)

        results = []
        for path, image in running:
            results.append(self._kill_target(path, image))

        images = [img for _, img in running if img]
        remaining = self._wait_until_gone(images)

        # 只有确实因权限被拒、且进程仍在，才询问是否提权重试；提权会弹 UAC
        denied = sorted({r['image'] for r in results if r.get('denied') and r.get('image')})
        if denied and (remaining & {i.lower() for i in denied}):
            reply2 = QMessageBox.question(
                self, '需要管理员权限',
                '%d 个程序拒绝访问，通常是它们以管理员身份运行。\n'
                '是否以管理员身份重试关闭？\n（系统会弹出 UAC 确认）' % len(denied),
                QMessageBox.Yes | QMessageBox.No,
                QMessageBox.No)
            if reply2 == QMessageBox.Yes:
                if self._elevated_kill(denied):
                    remaining = self._wait_until_gone(images, timeout=2)
                else:
                    log.warning('提权关闭未成功或用户取消')

        closed, failed = 0, []
        for res in results:
            image = (res.get('image') or '').lower()
            if image and image in remaining:
                reason = '权限不足（需管理员）' if image in {d.lower() for d in denied} \
                    else '进程仍在运行（可能被后台服务重启）'
                failed.append((get_display_name(res['path']), reason))
                log.warning('关闭失败：%s | image=%s | 原因=%s',
                            res['path'], res.get('image'), reason)
            else:
                closed += 1

        # 关闭文件夹窗口（整窗；多标签窗口由 _close_folder_window 循环处理）
        win_closed, win_failed = 0, []
        for w in (closable + close_mixed):
            ok, note = self._close_folder_window(w)
            if ok:
                win_closed += 1
                log.info('文件夹窗口已关闭：%s | tabs=%s | %s',
                         self._window_label(w), len(w.get('paths') or []), note)
            else:
                win_failed.append((self._window_label(w), '窗口未关闭（可能被拦截或无响应）'))
                log.warning('文件夹窗口关闭失败：%s | hwnd=%s | %s',
                            self._window_label(w), w.get('hwnd'), note)

        self.launched_items.clear()
        self.save_config()

        msg_parts = []
        if running:
            msg_parts.append('已关闭 %d 个程序。' % closed)
        if closable or close_mixed:
            msg_parts.append('已关闭 %d 个文件夹窗口。' % win_closed)
        msg = '\n'.join(msg_parts) if msg_parts else '没有内容被关闭。'

        skip_total = len(skipped) + len(skipped_windows) + len(unopened)
        if skip_total:
            msg += '\n跳过 %d 项（未运行 / 未打开窗口 / 无法判定 / 按你的选择跳过）。' % skip_total

        all_failed = failed + win_failed
        if all_failed:
            msg += '\n\n关闭失败 %d 项：\n%s' % (
                len(all_failed),
                '\n'.join('· %s —— %s' % (n, r) for n, r in all_failed[:8]))
            msg += '\n\n详细命令与返回码已写入日志：\n%s' % LOG_FILE
            msg += '\n（可点击主界面「🗒 日志」打开所在目录）'

        log.info('关闭结束：程序成功 %d / 失败 %d；文件夹窗口成功 %d / 失败 %d；跳过 %d',
                 closed, len(failed), win_closed, len(win_failed), skip_total)
        QMessageBox.information(self, '关闭结果', msg)

    @staticmethod
    def _pid_in_map(pid, proc_map):
        for pids in proc_map.values():
            if pid in pids:
                return True
        return False

    @staticmethod
    def _pid_info(pid):
        """
        返回 (是否存活, 镜像名)。

        用于两件事：判断记录里的 PID 是否还有效；以及在关闭前核对它是否仍属于目标程序，
        防止 PID 被系统复用后误杀无关进程。
        """
        try:
            out = decode_console(subprocess.check_output(
                ['tasklist', '/fi', 'PID eq %d' % pid, '/fo', 'csv', '/nh'],
                stderr=subprocess.DEVNULL, **hidden_subprocess_kwargs()))
            for row in csv.reader(out.splitlines()):
                if len(row) >= 2 and row[1].strip() == str(pid):
                    return True, row[0].strip()
        except Exception:
            pass
        return False, ''

    def _kill_target(self, path, image):
        """
        关闭单个目标：先按本次记录的 PID（含伴生 PID），**再按镜像名兜底**。

        镜像名这一步不能省：若程序已在运行，再次启动时新进程往往把请求转交给已有实例
        后立即退出（Electron / Tauri 的单实例行为），记录的 PID 随即失效。
        旧实现用 `elif image` 跳过镜像名关闭，于是出现"能打开、关不掉"。
        """
        result = {'path': path, 'image': image, 'denied': False, 'steps': []}
        launched = self._find_launched(path)

        if launched is not None:
            proc, _target, _preset, extra_pids = launched
            pid = getattr(proc, 'pid', None) if proc else None
            if pid:
                alive, alive_name = self._pid_info(pid)
                if alive and image and alive_name.lower() != image.lower():
                    # PID 可能被系统复用：放弃按 PID 关闭，交给镜像名兜底
                    log.warning('%s：记录 PID %s 现属于 %s，与目标镜像 %s 不符，跳过按 PID 关闭',
                                get_display_name(path), pid, alive_name, image)
                    alive = False
                if alive:
                    ok, rc, out = self._taskkill(['/f', '/t', '/pid', str(pid)])
                    result['steps'].append(('pid', pid, ok, rc))
                    if self._is_access_denied(out):
                        result['denied'] = True
                    try:
                        proc.wait(timeout=2)
                    except Exception:
                        pass
                else:
                    log.info('%s：记录 PID %s 已失效（多为单实例应用转交给已有进程）',
                             get_display_name(path), pid)
            for ep in (extra_pids or []):
                ok, rc, out = self._taskkill(['/f', '/t', '/pid', str(ep)])
                result['steps'].append(('pid', ep, ok, rc))
                if self._is_access_denied(out):
                    result['denied'] = True

        if image:
            ok, rc, out = self._taskkill(['/f', '/t', '/im', image])
            result['steps'].append(('image', image, ok, rc))
            if self._is_access_denied(out):
                result['denied'] = True

        # 兜底：处理登记过的"关不掉的伴生进程"（如 Steam 中转的脚本）
        try:
            resolved_base = os.path.basename(resolve_lnk(path)).lower()
        except Exception:
            resolved_base = ''
        for name in (os.path.basename(path).lower(), resolved_base):
            for extra_name in self.special_kill_map.get(name, []):
                ok, rc, out = self._taskkill(['/f', '/im', extra_name])
                result['steps'].append(('extra', extra_name, ok, rc))
                if self._is_access_denied(out):
                    result['denied'] = True

        log.info('关闭目标 %s | 镜像=%s | 步骤=%s | 权限拒绝=%s',
                 path, image, result['steps'], result['denied'])
        return result

    def _elevated_kill(self, images):
        """
        以管理员权限重试关闭，只弹一次 UAC。

        做法：把若干 taskkill 写进临时批处理，用 runas 启动 cmd 执行，再轮询验证。
        """
        if sys.platform != 'win32' or not images:
            return False

        bat = os.path.join(tempfile.gettempdir(), 'lf_close_elevated.bat')
        lines = ['@echo off']
        for name in images:
            lines.append('taskkill /f /t /im "%s"' % name)
        lines.append('exit /b 0')
        try:
            with open(bat, 'w', encoding='mbcs', errors='replace') as f:
                f.write('\r\n'.join(lines) + '\r\n')
        except Exception:
            log.exception('写入提权关闭脚本失败')
            return False

        try:
            rc = ctypes.windll.shell32.ShellExecuteW(
                None, 'runas', 'cmd.exe', '/c "%s"' % bat, None, 0)
        except Exception:
            log.exception('ShellExecuteW 提权调用失败')
            return False

        log.info('请求管理员权限关闭：%s | ShellExecute rc=%s', images, rc)
        if rc <= 32:
            log.warning('提权被取消或失败（rc=%s）', rc)
            return False

        remaining = self._wait_until_gone(images, timeout=20)
        log.info('提权关闭结束，剩余仍在运行：%s', remaining)
        return not remaining

    def open_log_dir(self):
        """打开日志所在目录，方便用户查看失败原因。"""
        try:
            os.makedirs(LOG_DIR, exist_ok=True)
            os.startfile(LOG_DIR)
            log.info('用户打开日志目录：%s', LOG_DIR)
        except Exception as e:
            log.exception('打开日志目录失败')
            QMessageBox.warning(self, '无法打开目录', '%s\n\n%s' % (LOG_DIR, e))



    def dragEnterEvent(self, event: QDragEnterEvent):
        if event.mimeData().hasUrls():
            event.acceptProposedAction()
            event.accept()
        else:
            event.ignore()

    def dropEvent(self, event: QDropEvent):
        for url in event.mimeData().urls():
            file_path = url.toLocalFile()
            if not file_path or not os.path.exists(file_path):
                continue
            if self.add_to_list(file_path, update_preset=True) and os.path.isdir(file_path):
                self.last_folder = normalize_input_path(file_path)
                self.save_config()
        event.acceptProposedAction()

    def save_config(self):
        self.save_current_list_to_preset()

        data = {
            'last_used': self.current_preset_name,
            'presets': self.presets,
            # settings 存放界面偏好；last_folder 用于选择框定位与手动输入默认值
            'settings': {
                'last_folder': self.last_folder,
            },
            'global_macro': self.global_macro,
        }
        try:
            with open(CONFIG_FILE, 'w', encoding='utf-8') as f:
                json.dump(data, f, indent=2, ensure_ascii=False)
        except Exception as e:
            QMessageBox.warning(self, '保存失败', f'无法写入配置文件：\n{e}')
    def load_config(self):
        if not os.path.exists(CONFIG_FILE):
            self.presets = {'默认方案': []}
            self.current_preset_name = '默认方案'
            self.global_macro = []
            self.last_folder = ''
            return
        try:
            with open(CONFIG_FILE, 'r', encoding='utf-8') as f:
                data = json.load(f)
            raw_presets = data.get('presets', {})
            self.presets = {}
            for name, items in raw_presets.items():
                new_items = []
                for entry in items:
                    if isinstance(entry, dict) and 'path' in entry:
                        new_items.append(entry['path'])
                    elif isinstance(entry, str):
                        new_items.append(entry)
                self.presets[name] = new_items
            if not self.presets:
                self.presets = {'默认方案': []}
            self.current_preset_name = data.get('last_used', list(self.presets.keys())[0])
            if self.current_preset_name not in self.presets:
                self.current_preset_name = list(self.presets.keys())[0]
            # 旧配置里的 settings.auto_launch 一律忽略：本版本不存在自动启动行为
            settings = data.get('settings', {})
            if isinstance(settings, dict):
                self.last_folder = normalize_input_path(settings.get('last_folder', ''))
            else:
                self.last_folder = ''
            self.global_macro = data.get('global_macro', [])
        except Exception as e:
            QMessageBox.warning(self, '加载失败', f'配置文件读取失败：\n{e}\n将使用默认设置。')
            self.presets = {'默认方案': []}
            self.current_preset_name = '默认方案'
            self.global_macro = []
            self.last_folder = ''

    def closeEvent(self, event):
        self.save_config()
        event.accept()


if __name__ == '__main__':
    app = QApplication(sys.argv)
    window = LauncherWindow()
    window.resize(520, 680)
    window.show()
    sys.exit(app.exec_())
