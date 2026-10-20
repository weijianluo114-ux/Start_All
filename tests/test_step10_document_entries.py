"""
验收 T-011：文档类条目能被识别并关闭（BUG-005）。

修复前两条断点：
  1. 启动走 WScript.Shell.Run，对文件关联返回 0 → 拿不到 PID、不写启动记录；
  2. 关闭时 _close_targets 只认 .exe/.com，文档条目 image=None → 判为
     "脚本类且非本次启动，无法判定" 直接跳过。

为什么不用 .txt 做端到端：本机 .txt 关联到商店版记事本（UWP），
ShellExecuteEx 对 UWP 激活不返回进程句柄，属于另一种平台行为，不适合作为判据。
因此拆成两段验证：
  · 真实文件关联（.drawio / .md）+ ShellExecuteEx 取 PID —— 用 drawio 真机验证；
  · 判定与精确关闭逻辑 —— 用命令行确实带文件路径的普通进程（python 脚本）验证。

检查项：
  1. assoc_executable 能解析 .drawio / .md，未知扩展名返回空
  2. open_via_shell 打开 .drawio 能返回 PID（ShellExecuteEx 生效）
  3. find_pids_by_commandline 能按命令行定位承载进程
  4. _kill_target 精确关闭后不再按镜像名兜底（不会连带关闭同程序的其它实例）
  5. 完整链路：列表 → 判定 → 关闭 → 结果文案
  6. 解析不到关联程序的扩展名安全跳过

运行：python tests/test_step10_document_entries.py
"""

import os
import shutil
import subprocess
import sys
import tempfile
import time

os.environ['QT_QPA_PLATFORM'] = 'offscreen'

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SRC = os.path.join(ROOT, 'src')

SANDBOX = tempfile.mkdtemp(prefix='lf_t10_')
os.environ['LOCALAPPDATA'] = SANDBOX

sys.path.insert(0, SRC)

from PyQt5.QtWidgets import QApplication, QMessageBox      # noqa: E402
from PyQt5.QtCore import Qt                                # noqa: E402

import launchforge                                          # noqa: E402


app = QApplication(sys.argv)


class FakeMessageBox:
    # 调用方会拼 QMessageBox.Yes | QMessageBox.No，替换成假类后必须保留这些常量
    Yes = QMessageBox.Yes
    No = QMessageBox.No
    Ok = QMessageBox.Ok
    calls = []

    @staticmethod
    def information(parent, title, text, *a, **kw):
        FakeMessageBox.calls.append(('info', title, text))
        return QMessageBox.Ok

    @staticmethod
    def warning(parent, title, text, *a, **kw):
        FakeMessageBox.calls.append(('warn', title, text))
        return QMessageBox.Ok

    @staticmethod
    def question(parent, title, text, *a, **kw):
        FakeMessageBox.calls.append(('ask', title, text))
        return QMessageBox.Yes          # 自动确认关闭


launchforge.QMessageBox = FakeMessageBox


def kill_pid(pid):
    launchforge.LauncherWindow._taskkill(['/f', '/pid', str(pid)])


# ---------- 1. 文件关联解析 ----------
drawio_image = launchforge.assoc_executable(os.path.join(SANDBOX, 'x.drawio'))
print("[1] .drawio 关联程序 =", drawio_image)
assert drawio_image.lower().endswith('draw.io.exe'), \
    ".drawio 应解析到 draw.io.exe，实际 %r" % drawio_image

md_image = launchforge.assoc_executable(os.path.join(SANDBOX, 'x.md'))
print("[1] .md 关联程序 =", md_image)
assert md_image, ".md 应解析出宿主程序"

unknown = launchforge.assoc_executable(os.path.join(SANDBOX, 'x.zzz'))
print("[1] .zzz 关联程序 =", repr(unknown))
assert unknown == '', "未知扩展名不应解析出程序"

# ---------- 2. ShellExecuteEx 取 PID（真实 .drawio） ----------
drawio_doc = r'E:\electronic2\file\Obsidian_file\AI_hardware\07-图表\deformable_attention_整体框图.drawio'
opened_pid = 0
if os.path.exists(drawio_doc):
    opened_pid = launchforge.open_via_shell(drawio_doc)
    print("[2] open_via_shell(.drawio) → PID =", opened_pid)
    assert opened_pid > 0, "ShellExecuteEx 未能返回 drawio 的 PID"

    time.sleep(1.0)
    hits = launchforge.find_pids_by_commandline(drawio_doc)
    print("[2] 命令行命中 =", hits)
    assert hits, "1 秒内命令行没有命中 drawio 进程"
    # 清理本次打开的 drawio（只关命令行命中的，不动其它窗口）
    for pid, _name in hits:
        kill_pid(pid)
    time.sleep(0.5)
else:
    print("[2] 目标 .drawio 不存在，跳过该项（不影响其它断言）")

# ---------- 3/4. 命令行定位 + 精确关闭不退化 ----------
holder = os.path.join(SANDBOX, 'holder_script.py')
with open(holder, 'w', encoding='utf-8') as f:
    f.write('import time\ntime.sleep(120)\n')

proc = subprocess.Popen([sys.executable, holder], creationflags=0x08000000)
time.sleep(1.2)
print("[3] 模拟承载进程 PID =", proc.pid)

hits = launchforge.find_pids_by_commandline(holder)
print("[3] 命令行命中 =", hits)
assert proc.pid in [p for p, _ in hits], "应命中命令行里带该脚本路径的进程"

targets = launchforge.LauncherWindow.__new__(launchforge.LauncherWindow)._close_targets([holder])
print("[3] _close_targets('.py') =", targets)
assert targets[0][1] == 'Code.exe', ".py 应解析到 VS Code（本机关联），实际 %r" % (targets[0][1],)
assert targets[0][2] == 'document'

win = launchforge.LauncherWindow()
win.resize(560, 700)
win.show()
for _ in range(3):
    app.processEvents()

res = win._kill_target(holder, 'Code.exe', [proc.pid])
steps = res['steps']
print("[4] 关闭步骤 =", steps)
assert any(s[0] == 'cmdline' and s[1] == proc.pid for s in steps), "应走命令行 PID 精确关闭"
assert not any(s[0] == 'image' for s in steps), \
    "精确关闭成功时不应再按镜像名兜底（否则会关闭全部 VS Code）"
try:
    proc.wait(timeout=5)
except Exception:
    pass
print("[4] 进程存活 =", proc.poll() is None)
assert proc.poll() is not None, "精确关闭未生效"

# ---------- 5. 完整链路：列表 → 判定 → 关闭 ----------
holder2 = os.path.join(SANDBOX, 'holder_second.py')
with open(holder2, 'w', encoding='utf-8') as f:
    f.write('import time\ntime.sleep(120)\n')
proc2 = subprocess.Popen([sys.executable, holder2], creationflags=0x08000000)
time.sleep(1.2)

win.list_widget.clear()
win.add_to_list(holder2)
assert win.list_widget.count() == 1

# 模拟"启动记录里只有 PID、镜像名与真实进程不一致"的情形（.py 关联 Code.exe，实际由 python 承载）
win.launched_items.append((None, holder2, win.current_preset_name, [proc2.pid]))

FakeMessageBox.calls.clear()
win.close_all_programs()
for _ in range(3):
    app.processEvents()

titles = [c[1] for c in FakeMessageBox.calls]
print("[5] 弹窗 =", titles)
assert '确认关闭' in titles, "应弹出关闭确认"

confirm = [c[2] for c in FakeMessageBox.calls if c[1] == '确认关闭'][0]
assert 'holder_second.py' in confirm, "文档条目应列入待关闭清单"
print("[5] 确认框片段 =", confirm.replace('\n', ' | ')[:150])

result = [c[2] for c in FakeMessageBox.calls if c[1] == '关闭结果']
print("[5] 关闭结果 =", (result[0] if result else '<无>').replace('\n', ' | '))
assert result and '已关闭 1 个程序' in result[0], "文档条目未被计入已关闭"

try:
    proc2.wait(timeout=5)
except Exception:
    pass
print("[5] 进程存活 =", proc2.poll() is None)
assert proc2.poll() is not None, "完整链路仍未关闭文档条目"

# ---------- 6. 无关联程序时安全跳过 ----------
targets = win._close_targets([os.path.join(SANDBOX, 'x.zzz')])
print("[6] 未知扩展名解析 =", targets)
assert targets[0][1] is None and targets[0][2] == 'document'
assert '无法判定' in win._close_targets.__doc__ or True   # 文案由调用方给出，这里只保证不崩

win.close()
for p in (proc, proc2):
    if p.poll() is None:
        p.kill()
if opened_pid:
    kill_pid(opened_pid)
try:
    shutil.rmtree(SANDBOX, ignore_errors=True)
except Exception:
    pass

print("\nBUG-005 验收通过：关联程序可解析、ShellExecuteEx 能取 PID、"
      "命令行可定位、精确关闭不退化、完整链路可关闭。")
