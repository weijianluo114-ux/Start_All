# -*- coding: utf-8 -*-
"""
BUG-003 验收：关闭程序时不再弹出黑色控制台窗口。

必须在**无控制台**的宿主下运行（pythonw.exe），否则子进程会继承父进程的控制台，
测不出"是否新建窗口"这件事。

做法：
  1. 对照组——用普通参数启动一个存活数秒的 ping，统计控制台窗口数（应 >= 1，
     证明本测试确实能看见黑框，不是瞎断言）；
  2. 实验组——用 hidden_subprocess_kwargs() 启动同样的 ping，统计（应为 0）；
  3. 单元检查——确认参数里带了 CREATE_NO_WINDOW 与 SW_HIDE；
  4. 功能检查——真实 tasklist / taskkill 在隐藏参数下仍能正常工作。
"""
import ctypes
import ctypes.wintypes as wt
import os
import subprocess
import sys
import time

BASE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(BASE)
sys.path.insert(0, os.path.join(ROOT, "src"))
OUT = os.path.join(BASE, "_t6_result.txt")

import launchforge  # noqa: E402

lines = []


def emit(msg):
    lines.append(str(msg))


def count_console_windows():
    """统计当前桌面上控制台类窗口数量。"""
    user32 = ctypes.WinDLL("user32", use_last_error=True)
    EnumProc = ctypes.WINFUNCTYPE(wt.BOOL, wt.HWND, wt.LPARAM)
    user32.EnumWindows.argtypes = [EnumProc, wt.LPARAM]
    user32.GetClassNameW.argtypes = [wt.HWND, wt.LPWSTR, ctypes.c_int]
    found = []

    def cb(hwnd, _):
        buf = ctypes.create_unicode_buffer(256)
        user32.GetClassNameW(hwnd, buf, 256)
        cls = buf.value
        if "Console" in cls or "CASCADIA" in cls.upper() or "PseudoConsole" in cls:
            found.append(cls)
        return True

    user32.EnumWindows(EnumProc(cb), 0)
    return found


def spawn_ping(**kwargs):
    return subprocess.Popen(
        ["ping", "-n", "6", "127.0.0.1"],
        stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, **kwargs)


def run():
    emit("宿主可执行文件: %s" % sys.executable)
    emit("frozen=%s" % getattr(sys, "frozen", False))
    emit("")

    # ---- 0. 宿主本身不应有控制台 ----
    hwnd = ctypes.windll.kernel32.GetConsoleWindow()
    emit("[0] 宿主控制台句柄 = %s（pythonw 下应为 0）" % hwnd)
    assert hwnd == 0, "请用 pythonw.exe 运行本测试，否则结论无效"

    # ---- 1. 单元检查 ----
    kw = launchforge.hidden_subprocess_kwargs()
    emit("[1] hidden_subprocess_kwargs = creationflags=%#010x startupinfo=%s"
         % (kw.get("creationflags", 0), bool(kw.get("startupinfo"))))
    assert kw.get("creationflags", 0) & 0x08000000, "缺少 CREATE_NO_WINDOW"
    assert kw.get("startupinfo") is not None, "缺少 STARTUPINFO"
    assert kw["startupinfo"].wShowWindow == 0, "STARTUPINFO 未设置 SW_HIDE"

    # ---- 2. 对照组：不隐藏参数 ----
    base_count = len(count_console_windows())
    emit("[2] 基线控制台窗口数 = %d" % base_count)

    p1 = spawn_ping()
    time.sleep(1.5)
    visible = count_console_windows()
    emit("    对照组（无隐藏参数）控制台窗口 = %d 个 %s" % (len(visible), visible))
    p1.kill()
    p1.wait()
    time.sleep(0.8)
    assert len(visible) > base_count, "对照组没看到黑框，说明本测试无法判定，结论不可信"

    # ---- 3. 实验组：隐藏参数 ----
    p2 = spawn_ping(**kw)
    time.sleep(1.5)
    hidden = count_console_windows()
    emit("    实验组（隐藏参数）控制台窗口 = %d 个 %s" % (len(hidden), hidden))
    p2.kill()
    p2.wait()
    time.sleep(0.5)
    assert len(hidden) <= base_count, "仍有控制台窗口出现"

    # ---- 4. 功能检查：tasklist / taskkill 仍可用 ----
    out = subprocess.check_output(
        ["tasklist", "/fi", "PID eq %d" % os.getpid(), "/fo", "csv", "/nh"],
        stderr=subprocess.DEVNULL, **kw).decode("gbk", errors="replace")
    emit("[3] 隐藏参数下 tasklist 输出 = %r" % out.strip()[:80])
    assert str(os.getpid()) in out, "tasklist 在隐藏参数下不可用"

    ok, rc, text = launchforge.LauncherWindow._taskkill(["/f", "/pid", "999999"])
    emit("[4] 隐藏参数下 taskkill（不存在的 PID）→ ok=%s rc=%s 输出=%r"
         % (ok, rc, (text or "").strip()[:60]))
    assert rc != 0, "对不存在的 PID 应返回非零"

    emit("")
    emit("BUG-003 验收通过：关闭程序不再新建控制台窗口，taskkill/tasklist 功能正常。")


try:
    run()
except Exception as e:
    import traceback
    emit("FAILED: %s" % e)
    emit(traceback.format_exc())
finally:
    with open(OUT, "w", encoding="utf-8") as f:
        f.write("\n".join(lines))
