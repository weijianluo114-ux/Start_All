# -*- coding: utf-8 -*-
"""
Step 17 验收：批处理脚本的伴生进程归属（BUG-007 / v1.14.2）

覆盖：
  1. descendants_of 的纯逻辑：只认父子链，不认"新出现的 PID"
  2. 真实场景：bat 启动程序的同时，另一个无关程序也在 2 秒窗口内启动
     - 旧算法（全局差集 after - before）**会**把它算进去（复现 bug）
     - 新算法只收父子链可达的进程，无关程序不在其中
  3. 关闭侧：记录的伴生 PID 若已被复用（镜像名/创建时间不符），跳过不杀
  4. 关闭侧：记录正确的伴生 PID 能被正常结束
  5. 受保护进程（explorer.exe）永远不会被记成伴生进程

运行：python tests/test_step17_bat_spawn_safety.py
（真机测试：会启动几个真实的 ping.exe 作为被测进程，结束时全部清理）
"""

import os
import shutil
import subprocess
import sys
import tempfile
import threading
import time

os.environ['QT_QPA_PLATFORM'] = 'offscreen'

SANDBOX = tempfile.mkdtemp(prefix='lf_t17_')
os.environ['LOCALAPPDATA'] = SANDBOX

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, 'src'))

import launchforge
from launchforge import LauncherWindow, descendants_of, PROTECTED_IMAGES

PING = os.path.join(os.environ.get('SystemRoot', r'C:\Windows'), 'System32', 'ping.exe')
WORK = tempfile.mkdtemp(prefix='lf_bat_')
BAT = os.path.join(WORK, 'spawn.bat')

started = []          # 本脚本启动的所有进程，结束前全部清掉


def kill_tree(pid):
    try:
        subprocess.run(['taskkill', '/f', '/t', '/pid', str(pid)],
                       capture_output=True, timeout=10,
                       creationflags=0x08000000)
    except Exception:
        pass


def snapshot_of(extra_rows=()):
    """构造一份快照，便于纯逻辑断言。行格式 (pid, ppid, name)。"""
    snap = {}
    for pid, ppid, name in extra_rows:
        snap[pid] = {'ppid': ppid, 'name': name, 'created': '20260101000000.000000+480'}
    return snap


class FakeWindow:
    """
    不构造 UI：只把关闭侧用到的方法借过来。

    继承 LauncherWindow 会走到 QMainWindow 的构造（需要 QApplication、读配置、
    自愈注册表），这些与被测逻辑无关；用纯 Python 类挂方法最干净。
    """

    _spawned_processes = LauncherWindow._spawned_processes
    _spawn_still_same = LauncherWindow._spawn_still_same
    _kill_target = LauncherWindow._kill_target
    _find_launched = LauncherWindow._find_launched
    _pid_info = staticmethod(LauncherWindow._pid_info)
    _pid_identity = staticmethod(LauncherWindow._pid_identity)
    _taskkill = staticmethod(LauncherWindow._taskkill)
    _is_access_denied = staticmethod(LauncherWindow._is_access_denied)

    def __init__(self):
        self.launched_items = []
        self.special_kill_map = {}
        self._launch_lock = threading.Lock()


try:
    # ---------- 1. 纯逻辑：父子链 ----------
    snap = snapshot_of([
        (100, 10, 'cmd.exe'),           # 脚本进程
        (101, 100, 'ping.exe'),         # 脚本的直接子进程
        (102, 101, 'child.exe'),        # 孙进程（跨两级）
        (200, 10, 'unrelated.exe'),     # 同一父进程下的兄弟 —— 不属于脚本
        (300, 1, 'system-idle.exe'),    # 完全无关
    ])
    kids = descendants_of(100, snap)
    print('[1] 从 cmd(100) 可达：%s' % sorted(kids))
    assert kids == {101, 102}, '父子链归属算错了：%s' % sorted(kids)
    assert 200 not in kids, '兄弟进程被算成了后代'
    assert 300 not in kids

    # 空快照 / 空 root 不能抛错
    assert descendants_of(0, snap) == set()
    assert descendants_of(100, {}) == set()
    print('    空 root / 空快照均返回空集合')

    # ---------- 2. 真实场景：窗口期内启动无关程序 ----------
    with open(BAT, 'w', encoding='mbcs') as f:
        f.write('@echo off\r\n')
        f.write('start "" "%s" -n 30 127.0.0.1 >nul\r\n' % PING)
        f.write('timeout /t 6 >nul\r\n')

    before = launchforge.process_snapshot()
    proc = subprocess.Popen([BAT], cwd=WORK,
                            creationflags=subprocess.CREATE_NEW_CONSOLE)
    started.append(proc)
    print('[2] 脚本已启动：cmd pid=%s' % proc.pid)

    # 关键：在 2 秒窗口内再启动一个**无关**程序（模拟用户手动打开别的软件）
    time.sleep(0.35)
    noise = subprocess.Popen([PING, '-n', '31', '127.0.0.1'],
                             stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                             creationflags=0x08000000)
    started.append(noise)
    print('    窗口期内启动的无关程序：pid=%s' % noise.pid)

    time.sleep(launchforge.SPAWN_WINDOW_SECONDS)
    after = launchforge.process_snapshot()

    old_diff = set(after) - set(before)
    print('[3] 旧算法（全局差集）收进来 %d 个 PID：%s'
          % (len(old_diff), sorted(old_diff)))
    if noise.pid not in old_diff:
        print('    注意：本机这次无关程序恰好没落进差集（时序原因），继续用归属判据验证')

    w = FakeWindow()
    extra, meta = w._spawned_processes(proc.pid, before, after)
    print('[4] 新算法（父子链）收进来 %d 个 PID：%s'
          % (len(extra), [(p, meta[p][0]) for p in extra]))

    assert noise.pid not in extra, '无关程序被记成了脚本的伴生进程（BUG-007 未修复）'
    assert extra, '脚本真正启动的 ping 应当被记录'
    # 每个被记录的 PID 都必须能沿父链追到 cmd（conhost 的父是 ping，不是 cmd，不能只看一层）
    reachable = descendants_of(proc.pid, after)
    assert set(extra) <= reachable, '记录了父链追不到 cmd 的进程：%s' % (set(extra) - reachable)
    assert all(p in after for p in extra), '记录了快照里不存在的 PID'
    spawn_pids = [p for p in extra if (after[p]['name'] or '').lower() == 'ping.exe']
    print('    归属到的 ping：%s；其中没有无关 pid=%s' % (spawn_pids, noise.pid))
    assert spawn_pids, '没抓到脚本启动的 ping'
    assert noise.pid not in spawn_pids

    # 受保护进程不会出现在归属结果里
    names = {(after[p]['name'] or '').lower() for p in extra}
    assert not (names & PROTECTED_IMAGES), '受保护进程被记进了伴生列表：%s' % names
    print('[5] 归属结果不含受保护进程（%s）' % '、'.join(sorted(PROTECTED_IMAGES)[:3]) + ' …')

    # ---------- 3. 关闭侧：PID 复用要跳过 ----------
    target = spawn_pids[0]
    w.launched_items.append((None, BAT, 'p', [target],
                             {target: ('not-the-same.exe', '19990101000000.000000+480')}))
    res = w._kill_target(BAT, None, [])
    steps = res['steps']
    print('[6] 镜像名/创建时间不符时：steps=%s' % steps)
    assert any(s[0] == 'spawn-skip' for s in steps), 'PID 被复用时仍试图关闭'
    alive, _name, _created = w._pid_identity(target)
    assert alive, '被判定为"疑似复用"的进程不该被结束'

    # 只改镜像名不符（创建时间一致）也要跳过
    w.launched_items = [(None, BAT, 'p', [target],
                         {target: ('definitely-not-ping.exe', meta[target][1])})]
    res = w._kill_target(BAT, None, [])
    assert any(s[0] == 'spawn-skip' for s in res['steps']), '镜像名不符时仍试图关闭'
    print('[7] 仅镜像名不符也会跳过')

    # ---------- 4. 关闭侧：记录正确时正常结束 ----------
    w.launched_items = [(None, BAT, 'p', [target], {target: meta[target]})]
    res = w._kill_target(BAT, None, [])
    print('[8] 记录正确时：steps=%s' % res['steps'])
    assert any(s[0] == 'spawn' for s in res['steps']), '记录正确却没执行关闭'
    deadline = time.time() + 3
    while time.time() < deadline and w._pid_identity(target)[0]:
        time.sleep(0.2)
    assert not w._pid_identity(target)[0], '记录了正确归属却没能结束进程'
    print('    目标进程已结束')

    # ---------- 5. 无 cmd PID 时宁可不记 ----------
    extra2, meta2 = w._spawned_processes(None, before, after)
    print('[9] 拿不到 cmd PID 时：extra=%s meta=%s' % (extra2, meta2))
    assert extra2 == [] and meta2 == {}, '没有 root pid 时不该记录任何进程'

    print('\nSTEP 17 全部通过：伴生进程只按父子链归属，窗口期内的无关程序不会被误杀。')

finally:
    # 只清理本脚本启动的进程（按 PID + 父子树），绝不碰用户正在用的程序
    for p in started:
        kill_tree(p.pid)
    time.sleep(0.3)
    shutil.rmtree(WORK, ignore_errors=True)
    shutil.rmtree(SANDBOX, ignore_errors=True)
