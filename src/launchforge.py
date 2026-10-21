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
    QAbstractItemView, QComboBox, QLabel, QInputDialog, QMenu, QDialog,
    QGraphicsDropShadowEffect, QStyledItemDelegate
)
from PyQt5.QtCore import (
    Qt, QTimer, QDir, QRectF, QPointF, QSize, pyqtSignal, QEvent,
    pyqtProperty, QPropertyAnimation, QEasingCurve
)
from PyQt5.QtGui import (
    QDragEnterEvent, QDropEvent, QIcon, QPainter, QColor, QBrush, QPen, QFont,
    QLinearGradient, QRadialGradient, QPainterPath, QPainterPathStroker, QFontDatabase
)

try:
    from win32com.client import Dispatch
    HAS_WIN32 = True
except ImportError:
    HAS_WIN32 = False

# 全局鼠标宏已于 v1.9.0 封存：实现移至 src/legacy/macro_feature.py，
# 本文件不再 import 它，因此 PyInstaller 不会收集，pynput 也不再是运行时依赖。

try:
    import win32gui
    import win32con
    import win32process
    HAS_WIN32GUI = True
except ImportError:
    HAS_WIN32GUI = False
    print('警告：未安装 pywin32，激活窗口功能不可用。请执行 pip install pywin32')

try:
    import winreg
    HAS_WINREG = True
except ImportError:                # 非 Windows 平台
    HAS_WINREG = False





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

APP_VERSION = '1.11.0'

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
    """模拟 subprocess.Popen 对象，用于 ShellExecuteEx / WScript.Shell 启动的进程"""
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


# ------------------------- 文件关联与进程定位 -------------------------
#
# 背景（BUG-005）：`.drawio` / `.md` / `.docx` 这类"文档条目"自身没有进程镜像名。
# 旧实现有两个断点：
#   1. 启动走 WScript.Shell.Run，实测它对"文件关联"返回 0，拿不到 PID；
#   2. 关闭时 _close_targets 只认 .exe/.com，文档条目一律 image=None。
# 两者叠加 → 运行状态判不出来，整条被跳过（日志：脚本类且非本次启动，无法判定）。
# 修法：打开时用 ShellExecuteEx 取真实 PID；关闭时先按"命令行包含该文件路径"精确定位，
# 再用文件关联解析出的宿主程序名兜底。

class SHELLEXECUTEINFOW(ctypes.Structure):
    """ShellExecuteExW 的参数结构（只用到前几个字段，hProcess 是最后一项）。"""
    _fields_ = [
        ('cbSize', ctypes.c_ulong),
        ('fMask', ctypes.c_ulong),
        ('hwnd', ctypes.c_void_p),
        ('lpVerb', ctypes.c_wchar_p),
        ('lpFile', ctypes.c_wchar_p),
        ('lpParameters', ctypes.c_wchar_p),
        ('lpDirectory', ctypes.c_wchar_p),
        ('nShow', ctypes.c_int),
        ('hInstApp', ctypes.c_void_p),
        ('lpIDList', ctypes.c_void_p),
        ('lpClass', ctypes.c_wchar_p),
        ('hkeyClass', ctypes.c_void_p),
        ('dwHotKey', ctypes.c_ulong),
        ('hIcon', ctypes.c_void_p),
        ('hProcess', ctypes.c_void_p),
    ]


def open_via_shell(path):
    """
    用 ShellExecuteEx 打开文件（走系统关联），返回进程 PID；失败返回 0。

    为什么不用 WScript.Shell.Run：实测它对文档关联返回 0（成功但无 PID），
    于是启动记录里没有这一项，关闭时无从判定。
    """
    if sys.platform != 'win32':
        return 0
    try:
        sei = SHELLEXECUTEINFOW()
        sei.cbSize = ctypes.sizeof(sei)
        # SEE_MASK_NOCLOSEPROCESS(0x40) 拿进程句柄
        # SEE_MASK_NOASYNC(0x100) 保证返回时进程已创建
        # SEE_MASK_FLAG_NO_UI(0x400) 出错时不弹系统错误框
        sei.fMask = 0x00000040 | 0x00000100 | 0x00000400
        sei.lpVerb = 'open'
        sei.lpFile = path
        sei.nShow = 1
        if not ctypes.windll.shell32.ShellExecuteExW(ctypes.byref(sei)):
            log.warning('ShellExecuteEx 失败：%s（错误码 %s）', path, ctypes.get_last_error())
            return 0
        if not sei.hProcess:
            return 0
        pid = int(ctypes.windll.kernel32.GetProcessId(sei.hProcess))
        ctypes.windll.kernel32.CloseHandle(sei.hProcess)
        return pid
    except Exception:
        log.exception('ShellExecuteEx 调用异常：%s', path)
        return 0


# 这些是系统的"兜底宿主"，不是用户真正用来打开文档的程序。
# 典型：没有默认程序时 AssocQueryString 会给出 OpenWith.exe（"打开方式"对话框的宿主），
# 若把它当成关联程序，关闭时会误判为"已运行"甚至去关系统对话框。
SHELL_WRAPPER_IMAGES = {
    'openwith.exe',
    'applicationframehost.exe',
    'dllhost.exe',
    'explorer.exe',
    'launchwinapp.exe',
    'dllhost.exe',
}


def assoc_executable(path):
    """
    返回"打开该文件时系统会调用的程序"的完整路径；解析不到返回 ''。

    `.drawio` → `...\\draw.io\\draw.io.exe`。关闭文档条目时用它作为兜底的镜像名。
    系统兜底宿主（OpenWith.exe 等）会被过滤成空——它不代表一个真实的应用。
    """
    if sys.platform != 'win32':
        return ''
    ext = os.path.splitext(str(path))[1]
    if not ext:
        return ''
    exe = ''
    try:
        shlwapi = ctypes.windll.shlwapi
        buf = ctypes.create_unicode_buffer(1024)
        size = ctypes.c_ulong(1024)
        # ASSOCF_NONE=0, ASSOCSTR_EXECUTABLE=2；AssocQueryString 已处理"用户手动改过默认程序"
        hr = shlwapi.AssocQueryStringW(0, 2, ext, 'open', buf, ctypes.byref(size))
        if hr == 0 and buf.value:
            exe = buf.value
    except Exception:
        log.debug('AssocQueryString 失败：%s', path, exc_info=True)
    if not exe:
        exe = _assoc_from_registry(ext)
    if exe and os.path.basename(exe).lower() in SHELL_WRAPPER_IMAGES:
        log.info('%s 的关联程序是系统兜底宿主 %s，忽略', ext, os.path.basename(exe))
        return ''
    return exe


def _assoc_from_registry(ext):
    """AssocQueryString 不可用时的回退：ProgId → shell\\open\\command → 取出 exe 路径。"""
    try:
        import winreg
    except ImportError:
        return ''
    prog_id = ''
    for root, key in ((winreg.HKEY_CURRENT_USER, r'Software\Classes' + ext),
                      (winreg.HKEY_CLASSES_ROOT, ext)):
        try:
            with winreg.OpenKey(root, key) as k:
                prog_id = winreg.QueryValueEx(k, '')[0]
        except OSError:
            continue
        if prog_id:
            break
    if not prog_id:
        return ''
    for root in (winreg.HKEY_CLASSES_ROOT, winreg.HKEY_CURRENT_USER):
        try:
            with winreg.OpenKey(root, r'%s\shell\open\command' % prog_id) as k:
                cmd = winreg.QueryValueEx(k, '')[0]
        except OSError:
            continue
        exe = _first_token_path(cmd)
        if exe and os.path.isfile(exe):
            return exe
    return ''


def _first_token_path(cmd):
    """从 `"C:\\x\\a.exe" "%1"` 这类命令行里取出可执行文件路径。"""
    if not cmd:
        return ''
    cmd = cmd.strip()
    if cmd.startswith('"'):
        end = cmd.find('"', 1)
        return cmd[1:end] if end > 1 else ''
    return cmd.split()[0] if cmd.split() else ''


def _same_exe_path(a, b):
    """比较两个可执行文件路径是否指向同一文件（忽略大小写、尾部反斜杠与环境变量差异）。"""
    if not a or not b:
        return False
    try:
        return os.path.normcase(os.path.normpath(os.path.expandvars(a))) == \
            os.path.normcase(os.path.normpath(os.path.expandvars(b)))
    except Exception:
        return False


def find_pids_by_commandline(path):
    """
    找出命令行里包含该文件路径的进程，返回 [(pid, 镜像名)]。

    依据：Windows 打开文档时会把它作为参数传给宿主程序
    （实测 `draw.io.exe "…\\x.drawio"`），因此命令行是"谁承载了这个文件"最直接的证据。
    返回空表示没有进程带这个参数——典型情况是单实例应用把请求转交给了已在运行的实例，
    此时主进程的命令行里不会出现新文件。
    """
    if sys.platform != 'win32' or not path:
        return []
    try:
        target = os.path.normcase(os.path.normpath(str(path)))
    except Exception:
        return []
    if not target:
        return []
    try:
        import pythoncom
        import win32com.client
    except ImportError:
        return []

    hits = []
    pythoncom.CoInitialize()
    try:
        wmi = win32com.client.GetObject('winmgmts:')
        for proc in wmi.ExecQuery('SELECT ProcessId, Name, CommandLine FROM Win32_Process'):
            cmd = proc.CommandLine or ''
            if cmd and target in os.path.normcase(cmd):
                hits.append((int(proc.ProcessId), proc.Name or ''))
    except Exception:
        log.debug('按命令行定位进程失败：%s', path, exc_info=True)
        return []
    finally:
        try:
            pythoncom.CoUninitialize()
        except Exception:
            pass
    return hits


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

    # 文档类（.drawio / .md / .docx / 图片 …）：交给系统关联程序打开。
    # 用 ShellExecuteEx 而不是 WScript.Shell.Run —— 后者对文件关联返回 0，
    # 拿不到 PID，关闭时就没有任何线索（BUG-005）。
    if sys.platform == 'win32':
        pid = open_via_shell(resolved)
        if pid:
            log.info('由系统关联程序打开：%s（pid=%s）', resolved, pid)
            return ShellProc(pid, resolved), resolved
        # 仍然拿不到 PID 也要把文件打开，关闭时再按命令行 / 关联程序兜底
        try:
            os.startfile(path)
        except Exception:
            log.exception('打开文件失败：%s', path)
        return None

    try:
        os.startfile(path)
    except Exception:
        pass
    return None


# ------------------------- 开机自启动 -------------------------
#
# 实现方式：写 HKEY_CURRENT_USER\Software\Microsoft\Windows\CurrentVersion\Run。
# 选 HKCU 而不是 HKLM，是因为它**不需要管理员权限**——程序本身是绿色单文件，
# 提权会触发 UAC 弹窗，得不偿失。
#
# 需要注意的一个坑：本项目的产物名带版本号（LaunchForge_vX.Y.Z.exe），
# 升级后旧 exe 会被 clean_artifacts.py 删除，注册表里那条命令随即指向不存在的文件，
# 开机自启动就静默失效了。因此提供 heal_autostart_path()：
# 仅在"已开启且指向的文件确实不存在"时改写成当前程序；指向其它存在的副本时不动。

AUTOSTART_KEY = r'Software\Microsoft\Windows\CurrentVersion\Run'
AUTOSTART_NAME = 'LaunchForge'


def autostart_command():
    """写入 Run 键的命令行（带引号，防止路径含空格）。"""
    if getattr(sys, 'frozen', False):
        return '"%s"' % sys.executable
    # 源码运行时用 pythonw.exe 拉起本文件，便于在开发机上验证同一套逻辑
    script = os.path.abspath(__file__)
    pyw = os.path.join(os.path.dirname(sys.executable), 'pythonw.exe')
    interp = pyw if os.path.exists(pyw) else sys.executable
    return '"%s" "%s"' % (interp, script)


def read_autostart(key_path=None, value_name=None):
    """读注册表里的自启动命令；未设置或读取失败时返回 ''。"""
    if sys.platform != 'win32' or not HAS_WINREG:
        return ''
    key_path = key_path or AUTOSTART_KEY
    value_name = value_name or AUTOSTART_NAME
    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, key_path, 0, winreg.KEY_READ) as k:
            value, _kind = winreg.QueryValueEx(k, value_name)
            return str(value or '')
    except FileNotFoundError:
        return ''
    except OSError:
        log.debug('读取自启动项失败', exc_info=True)
        return ''


def autostart_state(key_path=None, value_name=None):
    """
    返回 (是否已启用, 注册表里的命令, 是否指向当前程序)。

    "是否指向当前程序"按命令里第一个路径比较（忽略大小写与尾部反斜杠），
    所以升级后版本号变化会被识别为"指向旧文件"，而不是当成已正确启用。
    """
    stored = read_autostart(key_path, value_name)
    if not stored:
        return False, '', False
    return True, stored, _same_exe_path(_first_token_path(stored), _first_token_path(autostart_command()))


def set_autostart(enabled, key_path=None, value_name=None):
    """
    写入 / 删除自启动项，返回 (成功, 失败原因)。

    只改当前用户，不需要管理员权限。失败原因原样返回给界面显示，不静默吞掉——
    与关闭流程"失败必须可见"的约定一致。
    """
    if sys.platform != 'win32' or not HAS_WINREG:
        return False, '当前系统不支持注册表自启动项'
    key_path = key_path or AUTOSTART_KEY
    value_name = value_name or AUTOSTART_NAME
    try:
        if enabled:
            with winreg.CreateKeyEx(winreg.HKEY_CURRENT_USER, key_path, 0,
                                    winreg.KEY_SET_VALUE) as k:
                winreg.SetValueEx(k, value_name, 0, winreg.REG_SZ, autostart_command())
            log.info('已开启开机自启动：%s = %s', value_name, autostart_command())
        else:
            try:
                with winreg.OpenKey(winreg.HKEY_CURRENT_USER, key_path, 0,
                                    winreg.KEY_SET_VALUE) as k:
                    winreg.DeleteValue(k, value_name)
                log.info('已关闭开机自启动：%s', value_name)
            except FileNotFoundError:
                pass            # 本来就没有，按"已关闭"处理
        return True, ''
    except OSError as e:
        log.warning('修改自启动项失败：%s', e)
        return False, str(e)


def heal_autostart_path(key_path=None, value_name=None):
    """
    自启动项指向的文件已不存在时，改写成当前程序；返回新命令行（没改则返回 ''）。

    只在"用户开过自启动 + 那条命令确实指向不存在的文件"时才动，
    避免抢走用户另一份仍然存在的安装。
    """
    enabled, stored, same = autostart_state(key_path, value_name)
    if not enabled or same:
        return ''
    stale = _first_token_path(stored)
    if stale and os.path.exists(stale):
        return ''
    ok, err = set_autostart(True, key_path, value_name)
    if not ok:
        log.warning('自启动项自愈失败：%s', err)
        return ''
    log.info('自启动项指向的文件已不存在（%s），改写为当前程序', stale or stored)
    return autostart_command()


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
    RUN_COLORS = ('#A9ECC9', '#4CC38A', '#1D7350')
    CLOSE_COLORS = ('#F2605A', '#C1121F', '#6B0710')
    IDLE_COLORS = ('#EDEDED', '#CFCFCF', '#A6A6A6')

    def __init__(self, diameter=160, parent=None):
        super().__init__(parent)
        self._d = int(diameter)
        self._margin = 16                     # 留给落影
        self._gap = 4                         # 两条鱼之间的缝隙（只透底色，不加投影）
        self._cache = None
        self.setFixedSize(self._d + self._margin * 2, self._d + self._margin * 2)
        self.setMouseTracking(True)
        self.setCursor(Qt.PointingHandCursor)
        self.setToolTip('左（绿）：一键启动当前预设　|　右（红）：关闭列表内的程序与文件夹窗口')
        self._hover = None
        self._hover_t = 0.0                   # 悬停强度 0→1，驱动光圈与外圈高亮
        self._pressed = None
        self._run_enabled = True
        self._close_enabled = True

        self._hover_anim = QPropertyAnimation(self, b'hover_glow', self)
        # 比按钮略长：圆的面积大，太快会显得跳
        self._hover_anim.setDuration(130 if Theme.ANIMATIONS else 1)
        self._hover_anim.setEasingCurve(QEasingCurve.OutCubic)

    # ---- 悬停强度（动画属性） ----
    def _get_hover_t(self):
        return self._hover_t

    def _set_hover_t(self, value):
        self._hover_t = max(0.0, min(1.0, float(value)))
        self.update()

    hover_glow = pyqtProperty(float, _get_hover_t, _set_hover_t)

    def _set_hover_side(self, side):
        """切换悬停半区，并把强度平滑推到 1 / 0（而不是瞬间切换）。"""
        if side == self._hover:
            return
        self._hover = side
        self._hover_anim.stop()
        self._hover_anim.setStartValue(self._hover_t)
        self._hover_anim.setEndValue(1.0 if side else 0.0)
        self._hover_anim.start()

    # ------------------------- 对外接口 -------------------------

    def set_run_enabled(self, enabled):
        self._run_enabled = bool(enabled)
        if not self._run_enabled and self._hover == 'run':
            self._set_hover_side(None)
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
            # 110% 是终点，按动画强度插值，避免悬停瞬间"跳"一下
            factor = 100 + int(10 * self._hover_t)
            light, main, dark = (c.lighter(factor) if factor > 100 else c
                                 for c in (light, main, dark))
        return enabled, light, main, dark

    def _paint_shadow(self, p, big):
        p.save()
        p.setPen(Qt.NoPen)
        for offset, spread, alpha in ((2, 0, 30), (5, 1, 20), (9, 2, 12), (13, 4, 6)):
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

        # 2b) 内在发光：用"自身颜色的提亮版"做径向渐变。
        # 直接叠白色会把玉绿冲成灰绿，只有提高自身明度才有"从里面亮"的观感。
        bright = light.lighter(124)
        inner = QRadialGradient(QPointF(cx, cy), radius * 0.80)
        inner.setColorAt(0.0, QColor(bright.red(), bright.green(), bright.blue(),
                                    86 if enabled else 46))
        inner.setColorAt(0.42, QColor(bright.red(), bright.green(), bright.blue(), 34))
        inner.setColorAt(0.78, QColor(bright.red(), bright.green(), bright.blue(), 9))
        inner.setColorAt(1.0, QColor(bright.red(), bright.green(), bright.blue(), 0))
        p.fillPath(path, QBrush(inner))

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
        hover_here = self._hover_t if self._hover == side else 0.0
        if enabled and (hover_here > 0.01 or self._pressed == side):
            if self._pressed == side:
                rim = QColor(0, 0, 0, 80)
            else:
                rim = QColor(255, 255, 255, int(135 * hover_here))
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
                    p.setPen(QColor(0, 0, 0, 112))
                    p.drawText(box.translated(0.6, 1.2), Qt.AlignCenter, ch)
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
        self._paint_hover_glow(p, big)
        # 把圆内区域先填成控件底色，避免落影从缝隙里透出来
        p.setPen(Qt.NoPen)
        p.setBrush(self.palette().color(self.backgroundRole()))
        p.drawEllipse(big)

        self._paint_fish(p, left, 'run')
        self._paint_fish(p, right, 'close')

        # 中心发光：两块之间留出的缝只透底色，靠这层柔光让盘心"亮起来"，
        # 看上去像光从内部透出，而不是靠深色阴影把两块分开。
        self._paint_core_glow(p, big, _radius, _cx, _cy)

        # 鱼眼：左鱼嵌红点、右鱼嵌绿点
        self._paint_eye(p, eyes[0], eye_r, self.CLOSE_COLORS, self._run_enabled)
        self._paint_eye(p, eyes[1], eye_r, self.RUN_COLORS, self._close_enabled)

        self._paint_bezel(p, big)
        self._paint_text(p)
        p.end()

    def _paint_hover_glow(self, p, big):
        """
        悬停半圆的外发光：三圈递减的弧线叠出"柔光"（Qt 没有模糊画笔，用叠层代替）。

        只描被悬停的那一半，另一半保持安静 —— 这样两只"鱼"各自的边界始终清楚。
        """
        side = self._hover
        if not side or self._hover_t <= 0.01:
            return
        color = QColor(self.RUN_COLORS[1] if side == 'run' else self.CLOSE_COLORS[1])
        p.save()
        p.setBrush(Qt.NoBrush)
        for outset, width, alpha in ((3.0, 7.0, 28), (6.0, 4.0, 20), (9.0, 2.4, 13)):
            pen = QPen(QColor(color.red(), color.green(), color.blue(),
                              int(alpha * self._hover_t)))
            pen.setWidthF(width)
            pen.setCapStyle(Qt.RoundCap)
            p.setPen(pen)
            ring = big.adjusted(-outset, -outset, outset, outset)
            p.drawArc(ring, 90 * 16, (180 if side == 'run' else -180) * 16)
        p.restore()

    def _paint_core_glow(self, p, big, radius, cx, cy):
        """
        中心内发光：径向柔光 + 一枚更集中的球面亮斑。

        两层叠加才像"从里面亮"，单层纯白渐变更像蒙了一层雾。
        整体裁剪在圆内，边缘不留亮边，避免破坏外圈包边。
        """
        p.save()
        clip = QPainterPath()
        clip.addEllipse(big)
        p.setClipPath(clip)
        p.setPen(Qt.NoPen)

        # 1) 跨缝柔光：让盘心整体更亮，缝两侧也跟着提亮，光才"连贯"
        halo = QRadialGradient(QPointF(cx, cy), radius * 0.85)
        halo.setColorAt(0.0, QColor(255, 255, 255, 44))
        halo.setColorAt(0.35, QColor(255, 255, 255, 22))
        halo.setColorAt(0.70, QColor(255, 255, 255, 7))
        halo.setColorAt(1.0, QColor(255, 255, 255, 0))
        p.setBrush(QBrush(halo))
        p.drawEllipse(big)

        # 2) 球面亮斑：半径小、衰减快，做出"鼓起来受光"的点
        core = QRadialGradient(QPointF(cx, cy - radius * 0.06), radius * 0.34)
        core.setColorAt(0.0, QColor(255, 255, 255, 64))
        core.setColorAt(0.55, QColor(255, 255, 255, 18))
        core.setColorAt(1.0, QColor(255, 255, 255, 0))
        p.setBrush(QBrush(core))
        p.drawEllipse(big)
        p.restore()

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
        self._set_hover_side(side)
        super().mouseMoveEvent(event)

    def leaveEvent(self, event):
        self._set_hover_side(None)
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

# ------------------------- 视觉令牌 -------------------------
#
# 建立一套可复用的令牌，避免"随手取色、随手改字号"导致风格漂移：
#   · 字重只用 400 / 600 / 700 三档（中文正文不用细体，小字号会发虚）；
#   · 动效：悬停 110ms、按下 90ms，统一 ease-out；不用 linear，不做触发布局的动画；
#   · 颜色：暖灰 + 金 为骨架，绿与朱砂只出现在启停圆盘与状态指示上。

class Theme:
    INK = '#2B2721'          # 主文字
    INK_SOFT = '#5C5446'     # 次级文字（标签）
    MUTED = '#8A8170'        # 辅助说明
    PANEL = '#EDE7DB'
    CARD = '#FFFDF8'
    CARD_EDGE = '#E2DACB'
    GOLD = '#BEAD86'
    GOLD_DEEP = '#A8873F'
    GREEN = '#4CC38A'
    BLOOD = '#C1121F'
    HOVER_MS = 110           # 悬停：80–120ms 区间，取偏稳的 110
    PRESS_MS = 90            # 按下：80–100ms，要比悬停更快才有"手感"
    ANIMATIONS = True        # 由系统"动画效果"开关决定，见下方 _system_animations_enabled()

    @staticmethod
    def hover_ms():
        return Theme.HOVER_MS if Theme.ANIMATIONS else 1

    @staticmethod
    def press_ms():
        return Theme.PRESS_MS if Theme.ANIMATIONS else 1


def _system_animations_enabled():
    """
    读取 Windows「动画效果」开关（SPI_GETCLIENTAREAANIMATION）。

    桌面端没有 CSS 的 `prefers-reduced-motion`，等价物就是这个系统开关：
    关掉后过渡时长压到 1ms，界面立刻响应，同时保留最终视觉状态。
    """
    if sys.platform != 'win32':
        return True
    try:
        value = ctypes.c_int(1)
        ok = ctypes.windll.user32.SystemParametersInfoW(0x1042, 0, ctypes.byref(value), 0)
        return bool(value.value) if ok else True
    except Exception:
        return True


Theme.ANIMATIONS = _system_animations_enabled()

_FAMILY_CACHE = {}


def _resolve_family(kind):
    """
    按"首选 → 回退"挑一个本机存在的字体家族，结果缓存。

    为什么要回退链：Noto Sans SC 有多档字重（Light/Medium/Black），做标题层次比
    雅黑细；但它不随 Windows 预装，缺了就退回雅黑 UI，界面不会崩成宋体。
    """
    if kind in _FAMILY_CACHE:
        return _FAMILY_CACHE[kind]
    wanted = {
        'display': ('Noto Sans SC', 'Microsoft YaHei UI', 'Microsoft YaHei', 'Segoe UI'),
        'text': ('Microsoft YaHei UI', 'Microsoft YaHei', 'Segoe UI', 'Arial'),
        'mono': ('Cascadia Mono', 'Consolas', 'Courier New'),
    }[kind]
    installed = set(QFontDatabase().families())
    chosen = next((f for f in wanted if f in installed), wanted[-1])
    _FAMILY_CACHE[kind] = chosen
    return chosen


def ui_font(size=13, weight=QFont.Normal, kind='text', spacing=0.0):
    """统一字体入口：家族按角色解析、字重只用几档、字距只在短标签上加。"""
    font = QFont(_resolve_family(kind))
    font.setPixelSize(int(size))
    font.setWeight(weight)
    if spacing:
        font.setLetterSpacing(QFont.AbsoluteSpacing, float(spacing))
    return font


def pill_font(compact=False):
    """胶囊按钮的字体：13px Medium；预设行的小胶囊 12px。"""
    return ui_font(12 if compact else 13,
                   QFont.DemiBold if compact else QFont.Medium,
                   'text', 0.3)


def _rounded_path(rect, tl, tr, br, bl):
    """
    四角半径各不相同（外小内大）的圆角矩形路径。

    `QPainterPath.addRoundedRect` 只支持统一半径，所以手工按四角拼弧线；
    顺序是 左上 → 右上 → 右下 → 左下。
    """
    path = QPainterPath()
    path.moveTo(rect.left() + tl, rect.top())
    path.lineTo(rect.right() - tr, rect.top())
    if tr > 0:
        path.arcTo(QRectF(rect.right() - 2 * tr, rect.top(), 2 * tr, 2 * tr), 90, -90)
    path.lineTo(rect.right(), rect.bottom() - br)
    if br > 0:
        path.arcTo(QRectF(rect.right() - 2 * br, rect.bottom() - 2 * br, 2 * br, 2 * br), 0, -90)
    path.lineTo(rect.left() + bl, rect.bottom())
    if bl > 0:
        path.arcTo(QRectF(rect.left(), rect.bottom() - 2 * bl, 2 * bl, 2 * bl), 270, -90)
    path.lineTo(rect.left(), rect.top() + tl)
    if tl > 0:
        path.arcTo(QRectF(rect.left(), rect.top(), 2 * tl, 2 * tl), 180, -90)
    path.closeSubpath()
    return path


class PillButton(QPushButton):
    """
    象牙白 + 灰金胶囊按钮（v1.11.0 起改为自绘，带逐帧过渡）。

    为什么放弃 QSS：QSS 的 `:hover` 是瞬时切换，无法过渡；而靠定时器反复重设
    `styleSheet` 会触发整棵样式树重算。自绘后悬停 110ms、按下 90ms 都是属性插值，
    只触发重绘、不触发布局，符合"微交互不动布局"的约束。

    圆角内外呼应：贴圆一侧 19px（高度一半），朝外一侧 8px；左右列各自反向。
    """

    HEIGHT = 38
    SIDE_PADDING = 18
    MIN_WIDTH = 86

    HEIGHT_COMPACT = 28
    PADDING_COMPACT = 13
    MIN_WIDTH_COMPACT = 58

    SMALL_RADIUS = 8        # 朝外一侧的小圆角

    def __init__(self, text, parent=None, compact=False, small_side=None):
        super().__init__(text, parent)
        self._compact = compact
        self._height = self.HEIGHT_COMPACT if compact else self.HEIGHT
        self._padding = self.PADDING_COMPACT if compact else self.SIDE_PADDING
        self._min_width = self.MIN_WIDTH_COMPACT if compact else self.MIN_WIDTH
        self._small_side = small_side          # None / 'left' / 'right'

        self._hover_t = 0.0
        self._press_t = 0.0

        self.setCursor(Qt.PointingHandCursor)
        self.setFixedHeight(self._height)
        self.setFont(pill_font(compact))

        self._hover_anim = QPropertyAnimation(self, b'hover_t', self)
        self._hover_anim.setDuration(Theme.hover_ms())
        self._hover_anim.setEasingCurve(QEasingCurve.OutCubic)
        self._press_anim = QPropertyAnimation(self, b'press_t', self)
        self._press_anim.setDuration(Theme.press_ms())
        self._press_anim.setEasingCurve(QEasingCurve.OutQuad)

    # ---- 动画属性 ----
    def _get_hover_t(self):
        return self._hover_t

    def _set_hover_t(self, value):
        self._hover_t = max(0.0, min(1.0, float(value)))
        self.update()

    hover_t = pyqtProperty(float, _get_hover_t, _set_hover_t)

    def _get_press_t(self):
        return self._press_t

    def _set_press_t(self, value):
        self._press_t = max(0.0, min(1.0, float(value)))
        self.update()

    press_t = pyqtProperty(float, _get_press_t, _set_press_t)

    def _glide(self, anim, attr, target):
        anim.stop()
        anim.setStartValue(getattr(self, attr))
        anim.setEndValue(target)
        anim.start()

    # ---- 尺寸与圆角 ----
    def corner_radii(self):
        """返回 (左上, 右上, 右下, 左下)，绘制与验收共用同一份定义。"""
        big = self._height // 2
        small = min(self.SMALL_RADIUS, big)
        if self._small_side == 'left':
            return (small, big, big, small)
        if self._small_side == 'right':
            return (big, small, small, big)
        return (big, big, big, big)

    def sizeHint(self):
        metrics = self.fontMetrics()
        width = metrics.horizontalAdvance(self.text()) + self._padding * 2
        return QSize(max(self._min_width, width), self._height)

    # ---- 交互 ----
    def enterEvent(self, event):
        self._glide(self._hover_anim, '_hover_t', 1.0)
        super().enterEvent(event)

    def leaveEvent(self, event):
        self._glide(self._hover_anim, '_hover_t', 0.0)
        self._glide(self._press_anim, '_press_t', 0.0)
        super().leaveEvent(event)

    def mousePressEvent(self, event):
        if event.button() == Qt.LeftButton and self.isEnabled():
            self._glide(self._press_anim, '_press_t', 1.0)
        super().mousePressEvent(event)

    def mouseReleaseEvent(self, event):
        self._glide(self._press_anim, '_press_t', 0.0)
        super().mouseReleaseEvent(event)

    # ---- 绘制 ----
    def paintEvent(self, event):
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing, True)

        h, pr = self._hover_t, self._press_t
        enabled = self.isEnabled()
        rect = QRectF(0.5, 0.5, self.width() - 1.0, self.height() - 1.0)
        tl, tr, br, bl = self.corner_radii()
        path = _rounded_path(rect, tl, tr, br, bl)

        if enabled:
            top = QColor('#FFFFFF')
            bottom = _mix_color(QColor('#F1E9D9'), QColor('#FFF9EC'), h)
            if pr > 0:
                top = _mix_color(top, QColor('#EADFC8'), pr * 0.9)
                bottom = _mix_color(bottom, QColor('#F8F2E5'), pr * 0.9)
            # 四边同色（REQ-009 明确要求过，不再给上沿单独提亮），
            # 悬停时整体转为更深的金，明度差靠内侧高光与衬底渐变承担
            edge = _mix_color(QColor('#C3B18A'), QColor('#9C7C33'), h)
            text_color = _mix_color(QColor('#3A3429'), QColor('#0F0D09'), h)
        else:
            top, bottom = QColor('#F6F2E9'), QColor('#EFEADE')
            edge = QColor('#DCD3BF')
            text_color = QColor('#A79E8B')

        # 1) 主体：竖向渐变，上半接近纯白，下半是米金
        grad = QLinearGradient(rect.topLeft(), rect.bottomLeft())
        grad.setColorAt(0.0, top)
        grad.setColorAt(0.45, _mix_color(top, bottom, 0.30))
        grad.setColorAt(1.0, bottom)
        p.fillPath(path, QBrush(grad))

        # 2) 底部内阴影：常态=压铸厚度，悬停减弱（抬起），按下增强（压入）
        depth = 0.52 - 0.34 * h + 0.50 * pr
        depth = max(0.0, min(1.0, depth))
        if depth > 0.02:
            shade = QLinearGradient(QPointF(0, rect.center().y() - 2), QPointF(0, rect.bottom()))
            shade.setColorAt(0.0, QColor(0, 0, 0, 0))
            shade.setColorAt(1.0, QColor(0, 0, 0, int(52 * depth)))
            p.save()
            p.setClipPath(path)
            p.fillRect(rect, QBrush(shade))
            p.restore()

        # 3) 顶部 1px 镜面高光：悬停更亮，按下时几乎消失
        hi = int((72 + 128 * h) * (1.0 - 0.85 * pr))
        if hi > 4:
            p.setPen(QPen(QColor(255, 255, 255, hi), 1.0))
            p.drawLine(QPointF(rect.left() + max(tl * 0.85, 2), rect.top() + 1.2),
                       QPointF(rect.right() - max(tr * 0.85, 2), rect.top() + 1.2))

        # 3b) 底缘反光：悬停时才出现，配合减弱的内阴影形成"抬起"错觉
        if h > 0.05:
            p.setPen(QPen(QColor(255, 255, 255, int(70 * h)), 1.0))
            p.drawLine(QPointF(rect.left() + max(bl * 0.9, 2), rect.bottom() - 1.2),
                       QPointF(rect.right() - max(br * 0.9, 2), rect.bottom() - 1.2))

        # 4) 描边：四边同色；悬停时加深，避免出现"上沿白线"那种不一致
        pen = QPen(edge, 1.0)
        p.setPen(pen)
        p.setBrush(Qt.NoBrush)
        p.drawPath(path)

        # 5) 文字：按下时整体下沉 0.9px，模拟实体键程
        p.setFont(self.font())
        p.setPen(text_color)
        p.drawText(rect.translated(0, 0.9 * pr), Qt.AlignCenter, self.text())

        # 6) 键盘焦点环：只在 Tab 聚焦时出现
        if enabled and self.hasFocus():
            pen = QPen(QColor(168, 135, 63, 165))
            pen.setWidthF(1.0)
            pen.setStyle(Qt.DashLine)
            p.setPen(pen)
            p.setBrush(Qt.NoBrush)
            inner = rect.adjusted(2.0, 2.0, -2.0, -2.0)
            p.drawPath(_rounded_path(inner, max(tl - 2, 1), max(tr - 2, 1),
                                     max(br - 2, 1), max(bl - 2, 1)))
        p.end()

class PillColumn(QWidget):
    """
    贴在圆一侧的胶囊列：三枚按钮按「中间那枚与圆心同高、上下两枚向外」摆放。

    用绝对定位而不是 QVBoxLayout，因为布局只能平均分配剩余空间，
    做不到"中间那枚严格对齐圆心"这条视觉规则。

    side='left'  这一列在圆的左边，按钮左边缘对齐（贴面板左侧）；
    side='right' 这一列在圆的右边，按钮右边缘对齐（贴面板右侧）。
    宽度由 widths 逐排给定，左右两列传同一组值，保证成对等宽、上下对称。
    """

    CENTER_GAP = 66        # 中间那枚与上下两枚的中心距

    def __init__(self, buttons, side, height, widths=None, parent=None):
        super().__init__(parent)
        self._buttons = list(buttons)
        self._side = side
        self._widths = list(widths) if widths else [b.sizeHint().width() for b in self._buttons]
        assert len(self._widths) == len(self._buttons), '每枚按钮都要有对应宽度'
        for btn in self._buttons:
            btn.setParent(self)
        self.setFixedSize(max(self._widths), height)
        self._relayout()

    def _relayout(self):
        center_y = self.height() / 2.0
        offsets = (-self.CENTER_GAP, 0, self.CENTER_GAP)
        for btn, dy, width in zip(self._buttons, offsets, self._widths):
            width = min(width, self.width())
            x = 0 if self._side == 'left' else self.width() - width
            btn.setGeometry(int(x),
                            int(center_y + dy - btn.height() / 2.0),
                            int(width), btn.height())

    def resizeEvent(self, event):
        self._relayout()
        super().resizeEvent(event)


def _mix_color(a, b, t):
    """按比例混合两色，用于开关在开/关之间的过渡。"""
    t = max(0.0, min(1.0, t))
    return QColor(int(a.red() + (b.red() - a.red()) * t),
                  int(a.green() + (b.green() - a.green()) * t),
                  int(a.blue() + (b.blue() - a.blue()) * t))


class ToggleSwitch(QWidget):
    """
    胶囊形开关，纯 `QPainter` 绘制。

    不用 `QCheckBox` 的原因：勾选框与暖色面板 + 象牙白胶囊的质感不搭，
    而 QSS 无法给 QCheckBox 画出滑块、过渡与内阴影。手绘的好处是放大到 2 倍
    （截图、高 DPI）依然清晰，改配色只改两个常量。
    """

    toggled = pyqtSignal(bool)

    WIDTH, HEIGHT = 52, 28
    ON_COLORS = ('#A9ECC9', '#3EAE76')      # 与圆盘左半（启动）同源
    OFF_COLORS = ('#E7E1D4', '#CBC3B2')

    def __init__(self, checked=False, parent=None):
        super().__init__(parent)
        self._checked = bool(checked)
        self._hover = False
        self._pressed = False
        self._pos = 1.0 if checked else 0.0

        self.setFixedSize(self.WIDTH, self.HEIGHT)
        self.setCursor(Qt.PointingHandCursor)
        self.setFocusPolicy(Qt.StrongFocus)

        self._anim = QPropertyAnimation(self, b'knob', self)
        self._anim.setDuration(140)
        self._anim.setEasingCurve(QEasingCurve.OutCubic)

    # ---- 滑块位置（0=关，1=开），由动画驱动 ----
    def _get_knob(self):
        return self._pos

    def _set_knob(self, value):
        self._pos = max(0.0, min(1.0, float(value)))
        self.update()

    knob = pyqtProperty(float, _get_knob, _set_knob)

    def isChecked(self):
        return self._checked

    def set_hover(self, hovered):
        hovered = bool(hovered)
        if hovered != self._hover:
            self._hover = hovered
            self.update()

    def setChecked(self, checked, animate=True):
        """改状态但**不发信号**：由 SettingRow 统一发一次，避免重复写注册表。"""
        checked = bool(checked)
        if checked == self._checked:
            return
        self._checked = checked
        target = 1.0 if checked else 0.0
        self._anim.stop()
        if animate and self.isVisible():
            self._anim.setStartValue(self._pos)
            self._anim.setEndValue(target)
            self._anim.start()
        else:
            self._set_knob(target)
        self.update()

    def toggle(self):
        self.setChecked(not self._checked)
        self.toggled.emit(self._checked)

    # ---- 绘制 ----
    def paintEvent(self, event):
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing, True)

        rect = QRectF(1.5, 1.5, self.width() - 3.0, self.height() - 3.0)
        t = self._pos
        top = _mix_color(QColor(self.OFF_COLORS[0]), QColor(self.ON_COLORS[0]), t)
        bottom = _mix_color(QColor(self.OFF_COLORS[1]), QColor(self.ON_COLORS[1]), t)
        if self._hover:
            top, bottom = top.lighter(107), bottom.lighter(107)
        if self._pressed:
            top, bottom = top.darker(108), bottom.darker(108)

        # 1) 轨道
        path = QPainterPath()
        path.addRoundedRect(rect, rect.height() / 2.0, rect.height() / 2.0)
        track = QLinearGradient(rect.topLeft(), rect.bottomLeft())
        track.setColorAt(0.0, top)
        track.setColorAt(1.0, bottom)
        p.fillPath(path, QBrush(track))

        # 2) 内阴影：上沿压暗，做出凹槽感
        shade = QLinearGradient(rect.topLeft(), rect.bottomLeft())
        shade.setColorAt(0.0, QColor(0, 0, 0, 46))
        shade.setColorAt(0.55, QColor(0, 0, 0, 0))
        p.fillPath(path, QBrush(shade))

        # 3) 悬浮环：贴合圆盘"外圈上亮下暗"的语言
        if self._hover:
            ring = QColor(76, 195, 138, 125) if t > 0.5 else QColor(176, 149, 92, 115)
            pen = QPen(ring)
            pen.setWidthF(1.6)
            p.setPen(pen)
            p.setBrush(Qt.NoBrush)
            p.drawRoundedRect(rect.adjusted(-1.0, -1.0, 1.0, 1.0),
                              rect.height() / 2.0 + 1.0, rect.height() / 2.0 + 1.0)

        # 4) 轮廓
        pen = QPen(_mix_color(QColor('#BEAD86'), QColor('#2E8F63'), t))
        pen.setWidthF(1.1)
        p.setPen(pen)
        p.setBrush(Qt.NoBrush)
        p.drawPath(path)

        # 5) 滑块（带落影，向右移动时不做缩放，避免"跳动"）
        radius = rect.height() / 2.0 - 3.2
        cx = rect.left() + rect.height() / 2.0 + t * (rect.width() - rect.height())
        cy = rect.center().y() + 0.4

        p.setPen(Qt.NoPen)
        p.setBrush(QColor(0, 0, 0, 42))
        p.drawEllipse(QPointF(cx, cy + 1.1), radius, radius)

        knob = QLinearGradient(QPointF(cx, cy - radius), QPointF(cx, cy + radius))
        knob.setColorAt(0.0, QColor('#FFFFFF'))
        knob.setColorAt(1.0, QColor('#F4EFE3'))
        p.setBrush(QBrush(knob))
        pen = QPen(QColor(0, 0, 0, 28))
        pen.setWidthF(1.0)
        p.setPen(pen)
        p.drawEllipse(QPointF(cx, cy), radius, radius)

        # 6) 焦点框：键盘操作时可见，鼠标操作时不干扰视觉
        if self.hasFocus():
            pen = QPen(QColor(76, 195, 138, 150) if t > 0.5 else QColor(140, 125, 90, 140))
            pen.setWidthF(1.0)
            pen.setStyle(Qt.DotLine)
            p.setPen(pen)
            p.setBrush(Qt.NoBrush)
            p.drawRoundedRect(self.rect().adjusted(0, 0, -1, -1), 4, 4)
        p.end()

    # ---- 交互 ----
    def mousePressEvent(self, event):
        if event.button() == Qt.LeftButton:
            self._pressed = True
            self.update()
            event.accept()
            return
        super().mousePressEvent(event)

    def mouseReleaseEvent(self, event):
        if event.button() == Qt.LeftButton and self._pressed:
            self._pressed = False
            self.update()
            if self.rect().contains(event.pos()):
                self.toggle()
            event.accept()
            return
        super().mouseReleaseEvent(event)

    def enterEvent(self, event):
        self.set_hover(True)
        super().enterEvent(event)

    def leaveEvent(self, event):
        self.set_hover(False)
        super().leaveEvent(event)

    def keyPressEvent(self, event):
        if event.key() in (Qt.Key_Space, Qt.Key_Return, Qt.Key_Enter):
            self.toggle()
            event.accept()
            return
        super().keyPressEvent(event)


class SettingRow(QWidget):
    """
    设置项卡片：左侧标题 + 说明，右侧开关。

    **整行可点**——命中面积比只点开关大得多，不必精确瞄准 52×28。
    悬停时有四处同时变化：底色提亮、边框转金、左侧状态竖条加长、开关出现发光环。
    四处叠加是为了在小尺寸下也能一眼看出"当前指向哪一项"。
    """

    toggled = pyqtSignal(bool)

    HEIGHT = 90

    def __init__(self, title, description='', checked=False, with_switch=True, parent=None):
        super().__init__(parent)
        self._checked = bool(checked)
        self._hover = False
        self._enabled = True

        self.setFixedHeight(self.HEIGHT)
        self.setFocusPolicy(Qt.StrongFocus if with_switch else Qt.NoFocus)
        self.setCursor(Qt.PointingHandCursor if with_switch else Qt.ArrowCursor)

        self.title_label = QLabel(title, self)
        self.title_label.setFont(ui_font(14, QFont.DemiBold, 'text', 0.3))
        self.title_label.setAttribute(Qt.WA_TransparentForMouseEvents, True)

        self.desc_label = QLabel(description, self)
        self.desc_label.setFont(ui_font(11, QFont.Normal, 'text'))
        self.desc_label.setWordWrap(True)
        self.desc_label.setAttribute(Qt.WA_TransparentForMouseEvents, True)

        self.switch = ToggleSwitch(self._checked, self) if with_switch else None
        if self.switch is not None:
            self.switch.toggled.connect(self._on_switch_toggled)
            # 鼠标移到开关上时，字符串标签那份 hover 会断，靠事件过滤器补回来
            self.switch.installEventFilter(self)

        left = QVBoxLayout()
        left.setContentsMargins(0, 0, 0, 0)
        left.setSpacing(5)
        left.addWidget(self.title_label)
        left.addWidget(self.desc_label)
        left.addStretch(1)

        row = QHBoxLayout(self)
        row.setContentsMargins(20, 14, 16, 14)
        row.setSpacing(12)
        row.addLayout(left, 1)
        if self.switch is not None:
            row.addWidget(self.switch, 0, Qt.AlignVCenter)

        self._apply_text_colors()

    # ---- 状态 ----
    def is_checked(self):
        return self._checked

    def set_checked(self, checked, emit=True):
        checked = bool(checked)
        if checked == self._checked:
            if self.switch is not None:
                self.switch.setChecked(checked, animate=False)
            return
        self._checked = checked
        if self.switch is not None:
            self.switch.setChecked(checked, animate=emit and self.isVisible())
        self.update()
        if emit:
            self.toggled.emit(checked)

    def set_enabled_state(self, enabled):
        """整行禁用：文字转浅、开关置灰，点击不生效（用于平台不支持的场景）。"""
        self._enabled = bool(enabled)
        self.setCursor(Qt.PointingHandCursor if self._enabled else Qt.ForbiddenCursor)
        self.setFocusPolicy(Qt.StrongFocus if self._enabled else Qt.NoFocus)
        if self.switch is not None:
            self.switch.setEnabled(self._enabled)
        self._apply_text_colors()
        self.update()

    def _on_switch_toggled(self, checked):
        if checked == self._checked:
            return
        self._checked = checked
        self.update()
        self.toggled.emit(checked)

    def _set_hover(self, hovered):
        hovered = bool(hovered and self._enabled)
        if hovered == self._hover:
            return
        self._hover = hovered
        if self.switch is not None:
            self.switch.set_hover(hovered)
        self._apply_text_colors()
        self.update()

    def _apply_text_colors(self):
        if not self._enabled:
            title, desc = '#9C9382', '#ADA493'
        elif self._hover:
            title, desc = '#1F1B15', '#6E6553'
        else:
            title, desc = '#34302A', '#857B69'
        self.title_label.setStyleSheet('color: %s; background: transparent;' % title)
        self.desc_label.setStyleSheet('color: %s; background: transparent;' % desc)

    # ---- 绘制 ----
    def paintEvent(self, event):
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing, True)
        # 卡片比行高矮 4px，底部留出投影空间（投影只在悬停时出现）
        rect = QRectF(1.5, 1.5, self.width() - 3.0, self.height() - 5.0)
        radius = 10.0

        if self._hover and self._enabled:
            for dy, alpha in ((3.0, 14), (5.5, 9)):
                sh = QPainterPath()
                sh.addRoundedRect(rect.adjusted(2.5, dy - 1.0, -2.5, dy), radius, radius)
                p.fillPath(sh, QBrush(QColor(92, 74, 40, alpha)))

        bg = QLinearGradient(rect.topLeft(), rect.bottomLeft())
        if not self._enabled:
            bg.setColorAt(0.0, QColor('#F5F1E9'))
            bg.setColorAt(1.0, QColor('#EFEAE1'))
        elif self._hover:
            bg.setColorAt(0.0, QColor('#FFFFFF'))
            bg.setColorAt(1.0, QColor('#FDF8EE'))
        else:
            bg.setColorAt(0.0, QColor('#FFFDF8'))
            bg.setColorAt(1.0, QColor('#F8F2E6'))

        path = QPainterPath()
        path.addRoundedRect(rect, radius, radius)
        p.fillPath(path, QBrush(bg))

        edge = QColor('#B79A5E') if self._hover else QColor('#E2DACB')
        pen = QPen(edge)
        pen.setWidthF(1.6 if self._hover else 1.0)
        p.setPen(pen)
        p.setBrush(Qt.NoBrush)
        p.drawPath(path)

        # 左侧状态竖条：开启绿、关闭暖灰；悬停时上下各延伸 4px 并加粗，作为"当前项"指示
        if not self._enabled:
            bar_color = QColor('#DCD3C1')
        else:
            bar_color = QColor('#4CC38A') if self._checked else QColor('#D6CCB8')
        inset = 12.0 if self._hover else 16.0
        bar_width = 3.6 if self._hover else 3.0
        bar = QRectF(8.0, inset, bar_width, rect.height() - inset * 2)
        p.setPen(Qt.NoPen)
        p.setBrush(bar_color)
        p.drawRoundedRect(bar, bar_width / 2.0, bar_width / 2.0)

        # 悬停时顶部再加一道内高光，卡片才有"被托起"的感觉
        if self._hover:
            hal = QLinearGradient(rect.topLeft(), QPointF(rect.left(), rect.top() + 16))
            hal.setColorAt(0.0, QColor(255, 255, 255, 165))
            hal.setColorAt(1.0, QColor(255, 255, 255, 0))
            inner = QPainterPath()
            inner.addRoundedRect(rect.adjusted(1.0, 1.0, -1.0, -1.0), radius - 1.0, radius - 1.0)
            p.fillPath(inner, QBrush(hal))
        p.end()

    # ---- 交互 ----
    def mouseReleaseEvent(self, event):
        if self._enabled and self.switch is not None and event.button() == Qt.LeftButton:
            if self.rect().contains(event.pos()):
                self.set_checked(not self._checked)
            event.accept()
            return
        super().mouseReleaseEvent(event)

    def keyPressEvent(self, event):
        if self._enabled and self.switch is not None and \
                event.key() in (Qt.Key_Space, Qt.Key_Return, Qt.Key_Enter):
            self.set_checked(not self._checked)
            event.accept()
            return
        super().keyPressEvent(event)

    def enterEvent(self, event):
        self._set_hover(True)
        super().enterEvent(event)

    def leaveEvent(self, event):
        self._set_hover(False)
        super().leaveEvent(event)

    def eventFilter(self, obj, event):
        if self.switch is not None and obj is self.switch:
            if event.type() == QEvent.Enter:
                self._set_hover(True)
            elif event.type() == QEvent.Leave:
                self._set_hover(self.underMouse())
        return super().eventFilter(obj, event)


class SettingsDialog(QDialog):
    """
    设置面板（v1.10.0 起）。

    刻意做小（400×250）：只放真正会改变行为的开关，不摆"看起来丰富但不生效"的项。
    没有「保存」按钮——开关改动即时写入，失败会回滚开关并说明原因；
    因此面板本身不持有状态，每次都从注册表现读，外部改动也能如实反映。
    """

    WIDTH = 400
    HEIGHT = 224

    def __init__(self, parent=None, key_path=None, value_name=None):
        super().__init__(parent)
        self._key_path = key_path
        self._value_name = value_name

        self.setObjectName('settingsPanel')
        # 标题栏写项目名，面板内标题写「设置」——避免两处都是"设置"造成重复
        self.setWindowTitle('一键多启 · 设置')
        self.setFixedSize(self.WIDTH, self.HEIGHT)
        self.setWindowFlags((self.windowFlags() | Qt.WindowCloseButtonHint)
                            & ~Qt.WindowContextHelpButtonHint)
        self.setStyleSheet("""
            QDialog#settingsPanel { background-color: #EDE7DB; }
            QLabel#settingsTitle { color: #2E2A24; background: transparent; }
            QLabel#settingsHint { color: #8A8170; background: transparent; }
        """)

        title = QLabel('设置', self)
        title.setObjectName('settingsTitle')
        title.setFont(ui_font(17, QFont.Bold, 'display', 0.3))

        enabled_now = autostart_state(key_path, value_name)[0]
        self.row_autostart = SettingRow(
            '开机自启动',
            '登录 Windows 后自动打开启动器。\n不会自动启动列表内的条目。',
            checked=enabled_now, parent=self)
        self.row_autostart.toggled.connect(self._on_autostart_toggled)
        if sys.platform != 'win32':
            self.row_autostart.set_enabled_state(False)

        self.hint = QLabel('', self)
        self.hint.setObjectName('settingsHint')
        self.hint.setFont(ui_font(11, QFont.Normal, 'text'))
        self.hint.setWordWrap(False)

        self.btn_close = PillButton('关闭', compact=True)
        self.btn_close.clicked.connect(self.accept)

        footer = QHBoxLayout()
        footer.setContentsMargins(0, 0, 0, 0)
        footer.addStretch(1)
        footer.addWidget(self.btn_close)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(18, 16, 18, 16)
        layout.setSpacing(12)
        layout.addWidget(title)
        layout.addWidget(self.row_autostart)
        layout.addWidget(self.hint)
        layout.addStretch(1)
        layout.addLayout(footer)

        self.refresh()

    # ---- 状态同步 ----
    def refresh(self):
        """按注册表的真实状态刷新开关与提示文字。"""
        enabled, stored, same = autostart_state(self._key_path, self._value_name)
        self.row_autostart.set_checked(enabled, emit=False)
        command = autostart_command()
        exe_name = os.path.basename(_first_token_path(command)) or command
        if enabled and not same:
            self.hint.setStyleSheet('QLabel#settingsHint { color: #A8543C; background: transparent; }')
            self.hint.setText('注册表指向旧路径，下次启动会自动改写')
        elif enabled:
            self.hint.setStyleSheet('QLabel#settingsHint { color: #4E7A5F; background: transparent; }')
            self.hint.setText('已启用 · 登录后运行 %s' % exe_name)
        else:
            self.hint.setStyleSheet('QLabel#settingsHint { color: #8A8170; background: transparent; }')
            self.hint.setText('未启用 · 开启后随 Windows 登录启动')
        # 完整命令行放悬停提示：小窗口里塞不下长路径，但需要时可查
        self.hint.setToolTip('启动命令：\n%s' % command)

    def _on_autostart_toggled(self, checked):
        ok, err = set_autostart(checked, self._key_path, self._value_name)
        if not ok:
            # 写失败就回滚开关，绝不留下"看起来开了其实没开"的状态
            self.row_autostart.set_checked(not checked, emit=False)
            QMessageBox.warning(
                self, '设置未生效',
                '无法%s开机自启动：\n\n%s\n\n'
                '常见原因：注册表被安全软件拦截、或用户没有当前账户的写入权限。'
                % ('开启' if checked else '关闭', err))
        self.refresh()


def _kind_of(path):
    """列表行要画的类型：dir / exe / file / missing。"""
    kind = entry_kind(path)
    if kind != 'file':
        return kind
    ext = os.path.splitext(str(path))[1].lower()
    return 'exe' if ext in ('.exe', '.lnk', '.bat', '.cmd', '.com', '.msi') else 'file'


def _strip_kind_prefix(text):
    """列表文字里原有的 📁 / ⚠ 前缀去掉——类型改由矢量图形表达，不再用 emoji。"""
    for prefix in ('📁 ', '⚠ ', '📁', '⚠'):
        if text.startswith(prefix):
            return text[len(prefix):]
    return text


class ListRowDelegate(QStyledItemDelegate):
    """
    列表行绘制：左侧画类型图形、右侧画名称，底色由父视图的补间值驱动。

    为什么自绘：QSS 的 `::item:hover` 是瞬时切换，且无法做圆角行块 + 左侧强调条；
    用 delegate 后悬停与选中都能按帧淡入淡出，行高也由这里统一控制。
    """

    ROW_HEIGHT = 34
    GLYPH = 18

    def __init__(self, view):
        super().__init__(view)
        self._view = view
        self._font = ui_font(13, QFont.Normal, 'text', 0.2)

    def sizeHint(self, option, index):
        return QSize(0, self.ROW_HEIGHT)

    def paint(self, painter, option, index):
        row = index.row()
        hover = self._view.hover_value(row)
        select = self._view.select_value(row)
        path = index.data(Qt.UserRole) or ''
        kind = index.data(Qt.UserRole + 1) or _kind_of(path)
        text = _strip_kind_prefix(index.data(Qt.DisplayRole) or '')

        rect = QRectF(option.rect).adjusted(2.0, 1.0, -2.0, -1.0)
        radius = 8.0

        painter.save()
        painter.setRenderHint(QPainter.Antialiasing, True)

        # 底色：悬停=暖白、选中=暖金；取较大值，避免两种状态叠成两层色块
        strength = max(hover * 0.85, select * 0.95)
        if strength > 0.01:
            tint = _mix_color(QColor('#FBF6EC'), QColor('#EFE2C4'), select)
            painter.setPen(Qt.NoPen)
            painter.setBrush(QColor(tint.red(), tint.green(), tint.blue(), int(255 * strength)))
            painter.drawPath(_rounded_path(rect, radius, radius, radius, radius))

        # 选中时左侧强调条：只在选中态出现，悬停不出现，避免噪音
        if select > 0.02:
            painter.setPen(Qt.NoPen)
            painter.setBrush(QColor(176, 142, 79, int(235 * select)))
            painter.drawRoundedRect(
                QRectF(rect.left() + 6.0, rect.top() + 8.0, 3.0, rect.height() - 16.0), 1.5, 1.5)

        glyph_box = QRectF(rect.left() + 12.0,
                           rect.center().y() - self.GLYPH / 2.0,
                           self.GLYPH, self.GLYPH)
        self._paint_glyph(painter, glyph_box, kind)

        text_left = glyph_box.right() + 9.0
        text_rect = QRectF(text_left, rect.top(),
                           max(10.0, rect.right() - text_left - 10.0), rect.height())
        if kind == 'missing':
            color = QColor('#A8543C')
        else:
            color = _mix_color(QColor('#33302A'), QColor('#14120E'), max(hover, select))
        painter.setFont(self._font)
        painter.setPen(color)
        elided = painter.fontMetrics().elidedText(text, Qt.ElideMiddle, int(text_rect.width()))
        painter.drawText(text_rect, Qt.AlignVCenter | Qt.AlignLeft, elided)
        painter.restore()

    def _paint_glyph(self, p, box, kind):
        """用 18×18 的矢量图形表达类型：文件夹 / 可执行 / 普通文件 / 失效。"""
        p.save()
        p.setRenderHint(QPainter.Antialiasing, True)

        if kind == 'dir':
            tab = QRectF(box.left() + 1.5, box.top() + 2.5, box.width() * 0.46, 4.2)
            body = QRectF(box.left() + 1.5, box.top() + 5.0,
                          box.width() - 3.0, box.height() - 7.5)
            pen = QPen(QColor('#B08E4F'), 1.2)
            pen.setJoinStyle(Qt.RoundJoin)
            p.setPen(pen)
            p.setBrush(QColor(200, 169, 106, 40))
            p.drawRoundedRect(tab, 1.2, 1.2)
            p.setBrush(QColor(200, 169, 106, 26))
            p.drawRoundedRect(body, 2.2, 2.2)

        elif kind == 'exe':
            outer = QRectF(box.left() + 2.0, box.top() + 2.0,
                           box.width() - 4.0, box.height() - 4.0)
            p.setPen(QPen(QColor('#8A8170'), 1.2))
            p.setBrush(QColor(138, 129, 112, 22))
            p.drawRoundedRect(outer, 3.2, 3.2)
            cx, cy = outer.center().x(), outer.center().y()
            tri = QPainterPath()
            tri.moveTo(cx - 2.2, cy - 3.4)
            tri.lineTo(cx + 3.6, cy)
            tri.lineTo(cx - 2.2, cy + 3.4)
            tri.closeSubpath()
            p.setPen(Qt.NoPen)
            p.setBrush(QColor('#6E6759'))
            p.drawPath(tri)

        elif kind == 'missing':
            tri = QPainterPath()
            tri.moveTo(box.center().x(), box.top() + 2.4)
            tri.lineTo(box.right() - 2.0, box.bottom() - 3.0)
            tri.lineTo(box.left() + 2.0, box.bottom() - 3.0)
            tri.closeSubpath()
            pen = QPen(QColor('#C0503C'), 1.2)
            pen.setJoinStyle(Qt.RoundJoin)
            p.setPen(pen)
            p.setBrush(QColor(192, 80, 60, 28))
            p.drawPath(tri)
            p.setPen(QColor('#C0503C'))
            p.setFont(ui_font(9, QFont.Bold, 'text'))
            p.drawText(QRectF(box.left(), box.bottom() - 8.5, box.width(), 8.5),
                       Qt.AlignCenter, '!')

        else:      # file
            page = QRectF(box.left() + 3.5, box.top() + 2.0,
                          box.width() - 7.0, box.height() - 4.0)
            p.setPen(QPen(QColor('#8A8170'), 1.2))
            p.setBrush(QColor(138, 129, 112, 16))
            p.drawRoundedRect(page, 2.0, 2.0)
            p.drawLine(QPointF(page.left() + 3.0, page.center().y() + 1.5),
                       QPointF(page.right() - 3.0, page.center().y() + 1.5))
        p.restore()


class AnimatedList(QListWidget):
    """
    带逐行悬停 / 选中过渡的列表。

    一个 16ms 的补间器统一推进所有行的动画值，而不是给每行建 QPropertyAnimation：
    行数变化时不必维护动画对象生命周期，且只重绘 viewport、不触发布局。
    缓动指数 0.30 相当于 ~110ms 收敛，与按钮的悬停时长一致。
    """

    def __init__(self, parent=None):
        super().__init__(parent)
        self._hover_row = -1
        self._hover_val = {}
        self._select_val = {}

        self._ticker = QTimer(self)
        self._ticker.setInterval(16)
        self._ticker.timeout.connect(self._step)

        self.setMouseTracking(True)
        self.setUniformItemSizes(True)
        self.setVerticalScrollMode(QAbstractItemView.ScrollPerPixel)
        self.setItemDelegate(ListRowDelegate(self))
        self.itemEntered.connect(self._on_item_entered)
        self.itemSelectionChanged.connect(self._wake)

    # ---- 供 delegate 读取 ----
    def hover_value(self, row):
        return self._hover_val.get(row, 0.0)

    def select_value(self, row):
        return self._select_val.get(row, 0.0)

    # ---- 补间 ----
    def _on_item_entered(self, item):
        row = self.row(item)
        if row != self._hover_row:
            self._hover_row = row
            self._wake()

    def leaveEvent(self, event):
        self._hover_row = -1
        self._wake()
        super().leaveEvent(event)

    def wheelEvent(self, event):
        super().wheelEvent(event)
        self._hover_row = -1      # 滚动后行号已不可信，先清空再由 itemEntered 重新点亮

    def _wake(self):
        count = self.count()
        for row in range(count):
            self._hover_val.setdefault(row, 0.0)
            self._select_val.setdefault(row, 0.0)
        # 行数变少时清掉越界键，避免字典无限增长
        for store in (self._hover_val, self._select_val):
            for row in [k for k in store if k >= count]:
                del store[row]
        if not self._ticker.isActive():
            self._ticker.start()

    def _step(self):
        changed = False
        moving = False
        count = self.count()
        for row in range(count):
            item = self.item(row)
            targets = (
                (self._hover_val, 1.0 if row == self._hover_row else 0.0, 0.30),
                (self._select_val, 1.0 if item is not None and item.isSelected() else 0.0, 0.35),
            )
            for store, target, rate in targets:
                cur = store.get(row, 0.0)
                if abs(cur - target) < 0.008:
                    new = target
                else:
                    new = cur + (target - cur) * rate
                    moving = True
                if new != cur:
                    store[row] = new
                    changed = True
        if changed:
            self.viewport().update()
        if not moving:
            self._ticker.stop()

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
        self.preset_label = QLabel('预设方案')
        self.preset_label.setFont(ui_font(12, QFont.DemiBold, 'text', 0.4))
        self.preset_combo = QComboBox()
        self.preset_combo.setEditable(False)
        self.preset_combo.setFont(ui_font(13, QFont.Normal, 'text', 0.2))
        self.preset_combo.setMinimumHeight(30)
        self.btn_new_preset = PillButton('新建', compact=True)
        self.btn_del_preset = PillButton('删除', compact=True)

        preset_layout = QHBoxLayout()
        preset_layout.addWidget(self.preset_label)
        preset_layout.addWidget(self.preset_combo, 1)
        preset_layout.addWidget(self.btn_new_preset)
        preset_layout.addWidget(self.btn_del_preset)

        # 程序列表
        self.list_widget = AnimatedList()
        self.list_widget.setSelectionMode(QAbstractItemView.ExtendedSelection)
        self.list_widget.setDragDropMode(QAbstractItemView.DropOnly)
        self.list_widget.setDefaultDropAction(Qt.CopyAction)
        # 行内底色与文字由 delegate 画，这里的 QSS 只负责容器与滚动条，
        # 并且必须把 ::item 的背景清空——否则 Qt 会在自绘行上再叠一层默认选中块。
        self.list_widget.setStyleSheet("""
            QListWidget {
                background: #FFFFFF;
                border: 1px solid #E7DECD;
                border-radius: 12px;
                padding: 4px;
                outline: none;
            }
            QListWidget::item { background: transparent; border: none; }
            QListWidget::item:selected { background: transparent; }
            QScrollBar:vertical {
                background: transparent;
                width: 10px;
                margin: 4px 2px 4px 0;
            }
            QScrollBar::handle:vertical {
                background: #E2D9C6;
                border-radius: 4px;
                min-height: 28px;
            }
            QScrollBar::handle:vertical:hover { background: #CBB996; }
            QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical { height: 0; }
            QScrollBar::add-page:vertical, QScrollBar::sub-page:vertical { background: transparent; }
        """)

        # 六项操作做成胶囊条，挂在圆的左右两侧——中间只留一颗圆，不与按钮堆在一起。
        # 文字不用 emoji：彩色图标会破坏象牙白 + 灰金的整体质感。
        # small_side 决定"朝外的那一侧收小圆角"：左列收左边、右列收右边，两列内外呼应。
        self.btn_add = PillButton('添加程序', small_side='left')
        self.btn_add_folder = PillButton('添加文件夹', small_side='left')
        self.btn_add_path = PillButton('输入路径', small_side='left')
        self.btn_del = PillButton('删除选中', small_side='right')
        self.btn_log = PillButton('日志', small_side='right')
        self.btn_settings = PillButton('设置', small_side='right')

        # 顺序即位置：第 1 个在上、第 3 个在下，中间那枚与圆心同高。
        # 宽度规则（REQ-009）：同一排左右等宽，且上排与下排取同一个值，
        # 这样左右成对一致、上下关于中线镜像，整体才是对称的。
        self.taiji = TaijiLaunchButton(160)
        pills_height = self.taiji.height()
        w_outer = max(btn.sizeHint().width() for btn in
                      (self.btn_add_folder, self.btn_del, self.btn_add_path, self.btn_settings))
        w_mid = max(btn.sizeHint().width() for btn in (self.btn_add, self.btn_log))
        row_widths = [w_outer, w_mid, w_outer]

        self.left_pills = PillColumn(
            [self.btn_add_folder, self.btn_add, self.btn_add_path],
            'left', pills_height, widths=row_widths)
        self.right_pills = PillColumn(
            [self.btn_del, self.btn_log, self.btn_settings],
            'right', pills_height, widths=row_widths)

        taiji_row = QHBoxLayout()
        taiji_row.setSpacing(12)
        taiji_row.addStretch(1)
        taiji_row.addWidget(self.left_pills)
        taiji_row.addWidget(self.taiji)
        taiji_row.addWidget(self.right_pills)
        taiji_row.addStretch(1)

        # 布局：预设行在最上（全局上下文），圆区居次（主视觉），列表吃满剩余高度
        central = QWidget()
        central.setObjectName('panel')
        self.setCentralWidget(central)

        # 三层明度拉出层次：暖白面板（最深）→ 象牙白胶囊（中间调）→ 纯白列表（最亮）
        self.preset_label.setObjectName('presetLabel')
        self.setStyleSheet("""
            #panel {{ background-color: {panel}; }}
            QLabel#presetLabel {{ color: {ink_soft}; }}
            QComboBox {{
                background: {card};
                border: 1px solid #E1D6BF;
                border-radius: 8px;
                padding: 5px 10px;
                color: {ink};
                selection-background-color: #EFE6D2;
            }}
            QComboBox:hover {{ border-color: #C0A76F; }}
            QComboBox:focus {{ border-color: {gold_deep}; }}
            QComboBox::drop-down {{ border: none; width: 24px; }}
            QComboBox QAbstractItemView {{
                background: {card};
                border: 1px solid #E1D6BF;
                padding: 4px;
                selection-background-color: #EFE6D2;
                selection-color: {ink};
                outline: none;
            }}
        """.format(panel=Theme.PANEL, card=Theme.CARD, ink=Theme.INK,
                   ink_soft=Theme.INK_SOFT, gold_deep=Theme.GOLD_DEEP))

        layout = QVBoxLayout(central)
        layout.setContentsMargins(12, 10, 12, 12)
        layout.setSpacing(10)
        layout.addLayout(preset_layout)
        layout.addLayout(taiji_row)
        layout.addWidget(self.list_widget, 1)

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

        self.btn_log.clicked.connect(self.open_log_dir)
        self.btn_settings.clicked.connect(self.open_settings)

        # 自启动项可能指向已被清理的旧版本（产物名带版本号，升级后旧 exe 会被删）。
        # 这里只做"明确已失效"的自愈，指向其它仍存在的副本时不动，避免抢走用户的另一份安装。
        try:
            healed = heal_autostart_path()
            if healed:
                log.info('开机自启动项已更新到当前版本：%s', healed)
        except Exception:
            log.exception('检查开机自启动项时出错（不影响启动器正常使用）')

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
        # 类型在入列时算一次，delegate 每帧只读缓存 —— 否则重绘会反复做磁盘探测
        item.setData(Qt.UserRole + 1, _kind_of(path))
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

        finally:
            QTimer.singleShot(0, self._launch_finished)
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
        把列表条目解析为可关闭目标 [(原路径, 镜像名, 类型)]。

        类型：
          'exe'      自身就是可执行文件，可直接按镜像名判定；
          'script'   .bat/.cmd，真正跑起来的是 cmd.exe，只能靠启动时记下的 PID；
          'document' .drawio / .md / .docx 等，镜像名来自文件关联（如 draw.io.exe），
                     关闭时再叠加"命令行含文件路径"的精确匹配。

        解析不到镜像名时 image 为 None。
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
                targets.append((p, os.path.basename(resolved), 'exe'))
            elif ext in ('.bat', '.cmd'):
                targets.append((p, None, 'script'))
            else:
                # 文档类：借文件关联找出宿主程序（.drawio → draw.io.exe）
                exe = assoc_executable(resolved)
                image = os.path.basename(exe) if exe else None
                targets.append((p, image, 'document'))
                if image:
                    log.info('文档条目 %s：关联程序为 %s', os.path.basename(p), image)
                else:
                    log.info('文档条目 %s：解析不到关联程序', os.path.basename(p))
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

        running = []      # [(path, image, [命令行命中的精确 PID])]
        skipped = []      # [(path, reason)]
        for path, image, kind in self._close_targets(program_paths):
            if entry_kind(path) == 'missing':
                skipped.append((path, '路径已不存在'))
                continue
            launched = self._find_launched(path)
            if launched is not None:
                pid = getattr(launched[0], 'pid', None) if launched[0] else None
                # 记录里的 PID 可能早已失效（单实例应用会把请求转交给已有进程后自行退出），
                # 因此不能只看"有记录"就认定为运行中，必须确认 PID 仍在快照里。
                if pid and self._pid_in_map(pid, proc_map):
                    running.append((path, image, [pid]))
                    continue
                if launched[3] and any(self._pid_in_map(p, proc_map) for p in launched[3]):
                    running.append((path, image, list(launched[3])))
                    continue
                log.info('%s：记录的启动 PID 已失效，改用命令行 / 镜像名判定',
                         get_display_name(path))

            # 文档类条目：命令行里带这个文件路径的进程，才是真正承载它的那个。
            # 这一步比按镜像名精确——不会连带关闭同一程序的其它窗口。
            if kind == 'document':
                hits = find_pids_by_commandline(path)
                if hits:
                    pids = [pid for pid, _name in hits]
                    log.info('%s：按命令行定位到 PID %s（%s）', get_display_name(path),
                             pids, [name for _, name in hits])
                    running.append((path, image, pids))
                    continue

            if image is None:
                skipped.append((path, '无法判定（没有关联程序，也不是本次启动）'))
                continue
            if own_name and image.lower() == own_name:
                skipped.append((path, '启动器自身'))
                continue
            if image.lower() in proc_map:
                running.append((path, image, []))
            else:
                skipped.append((path, '未运行'))

        closable, mixed = self._folder_window_plan(folder_paths)

        log.info('判定结果：运行中程序 %d 项 %s；可整窗关闭的窗口 %d 个 %s；混有列表外标签 %d 个 %s；程序跳过 %d 项'
                 ' %s',
                 len(running), [(os.path.basename(p), img, pids) for p, img, pids in running],
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
            names = []
            for p, img, pids in running:
                label = get_display_name(p)
                is_document = os.path.splitext(p)[1].lower() not in ('.exe', '.com')
                if is_document and not pids and img:
                    # 没有命令行证据，只能按关联程序关闭 —— 会连带关掉同程序的其它窗口
                    label += '（将关闭 %s 的全部实例）' % img
                names.append(label)
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
        if any(img and not pids and os.path.splitext(p)[1].lower() not in ('.exe', '.com')
               for p, img, pids in running):
            text += ('\n\n注：标记了程序名的条目本身是文档（如 .drawio），没有独立进程，'
                     '只能按"打开它的程序"关闭，因此会同时关闭该程序的其他窗口。')
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
        for path, image, pids in running:
            results.append(self._kill_target(path, image, pids))

        images = [img for _, img, _pids in running if img]
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
            if res.get('precise_closed'):
                # 承载进程已按命令行 PID 关掉；此时再按关联程序名复核会误判
                # （例如 .py 的关联程序是 Code.exe，用户的 VS Code 当然还在）
                closed += 1
                continue
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

    def _kill_target(self, path, image, pids=None):
        """
        关闭单个目标，按四层优先级：

          1. **命令行命中的 PID**（`pids`）——文档类最精确的一层，命中的就是"打开这个文件的进程"；
          2. 本次启动记录的 PID（含 .bat/.cmd 的差集 PID）；
          3. **镜像名**——会命中同名全部实例，是单实例应用（转交后新进程退出）的兜底；
          4. 登记过的伴生进程名（如 Steam 中转的脚本）。

        第 1 层全部关闭成功时**不再**走第 3 层，否则"精确关闭"会退化成"全杀同程序"。
        """
        result = {'path': path, 'image': image, 'denied': False, 'steps': [],
                  'precise_closed': False}

        precise = [p for p in (pids or []) if self._pid_info(p)[0]]
        for p in precise:
            ok, rc, out = self._taskkill(['/f', '/t', '/pid', str(p)])
            result['steps'].append(('cmdline', p, ok, rc))
            if self._is_access_denied(out):
                result['denied'] = True
        if precise:
            alive = [p for p in precise if self._pid_info(p)[0]]
            if not alive:
                result['precise_closed'] = True
                log.info('关闭目标 %s | 按命令行命中的 PID %s 关闭成功', path, precise)
                return result
            log.warning('%s：命令行命中的 PID %s 未全部关闭，继续按镜像名兜底', path, alive)

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

    def open_settings(self):
        """
        打开设置面板。

        面板本身不保存状态：每次打开都从注册表现读，开关改动即时写入。
        这样即使有人手动删掉 Run 键，界面也不会残留"已开启"的假象。
        """
        log.info('用户打开设置面板')
        dialog = SettingsDialog(self)
        dialog.exec_()
        log.info('设置面板已关闭')


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
        except Exception as e:
            QMessageBox.warning(self, '加载失败', f'配置文件读取失败：\n{e}\n将使用默认设置。')
            self.presets = {'默认方案': []}
            self.current_preset_name = '默认方案'
            self.last_folder = ''

    def closeEvent(self, event):
        self.save_config()
        event.accept()


if __name__ == '__main__':
    app = QApplication(sys.argv)
    window = LauncherWindow()
    window.resize(560, 700)
    window.show()
    sys.exit(app.exec_())
