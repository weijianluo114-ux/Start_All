# -*- coding: utf-8 -*-
"""
Step 11 验收：设置面板 + 开机自启动（REQ-010 / FEAT-010）

覆盖：
  1. 注册表读写：未设置 → 开启 → 读回 → 关闭 → 再关闭（幂等）
  2. autostart_state 能识别"指向旧文件"（不是简单看键是否存在）
  3. heal_autostart_path 只在目标文件确实不存在时才改写
  4. 设置面板：构造即反映真实状态；点整行 / 点开关都能写注册表
  5. 写失败时开关回滚，不出现"看起来开了其实没开"
  6. 悬停高亮确实改变渲染像素（不是只改个变量）
  7. 窗口尺寸受控，内容不溢出

安全约定：**全程使用独立注册表沙箱键**，绝不碰真实的 Run 键——
否则测试值会在下次登录时被执行。

运行：python tests/test_step11_settings_autostart.py
"""

import os
import shutil
import sys
import tempfile
import winreg

os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')

SANDBOX = tempfile.mkdtemp(prefix='lf_t11_')
os.environ['LOCALAPPDATA'] = SANDBOX

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, 'src'))

from PyQt5.QtCore import Qt, QPoint
from PyQt5.QtGui import QColor
from PyQt5.QtWidgets import QApplication
from PyQt5.QtTest import QTest

import launchforge

app = QApplication(sys.argv)

# 独立沙箱键：与真实 Run 键完全隔离，测试残留也不会被登录时执行
TEST_KEY = r'Software\MultiLauncherSelfTest\Run'
TEST_NAME = 'LaunchForgeSelfTest'
REAL_READ_BEFORE = launchforge.read_autostart()


def clean_key():
    try:
        winreg.DeleteKey(winreg.HKEY_CURRENT_USER, TEST_KEY)
    except OSError:
        pass


def raw_write(cmd):
    """直接写一条命令，用于制造"指向旧文件"的状态。"""
    with winreg.CreateKeyEx(winreg.HKEY_CURRENT_USER, TEST_KEY, 0,
                            winreg.KEY_SET_VALUE) as k:
        winreg.SetValueEx(k, TEST_NAME, 0, winreg.REG_SZ, cmd)


clean_key()

try:
    # ---------- 1. 注册表读写 ----------
    state = launchforge.autostart_state(TEST_KEY, TEST_NAME)
    assert state == (False, '', False), state
    print("[1] 初始状态 → 未启用")

    cmd = launchforge.autostart_command()
    ok, err = launchforge.set_autostart(True, TEST_KEY, TEST_NAME)
    assert ok, '开启失败：%s' % err
    stored = launchforge.read_autostart(TEST_KEY, TEST_NAME)
    assert stored == cmd, stored
    enabled, got, same = launchforge.autostart_state(TEST_KEY, TEST_NAME)
    assert enabled and same, (enabled, got, same)
    print("[2] 开启后读回 → %s" % stored)

    ok, _ = launchforge.set_autostart(True, TEST_KEY, TEST_NAME)
    assert ok and launchforge.read_autostart(TEST_KEY, TEST_NAME) == cmd
    print("[3] 重复开启幂等 ✅")

    ok, err = launchforge.set_autostart(False, TEST_KEY, TEST_NAME)
    assert ok, err
    assert launchforge.read_autostart(TEST_KEY, TEST_NAME) == ''
    ok, err = launchforge.set_autostart(False, TEST_KEY, TEST_NAME)
    assert ok, '重复关闭应成功：%s' % err
    print("[4] 关闭 / 重复关闭 → 键已删除且不报错 ✅")

    # ---------- 2. 状态判定区分"键存在"与"指向当前程序" ----------
    missing = os.path.join(SANDBOX, 'gone', 'LaunchForge_v0.0.1.exe')
    raw_write('"%s"' % missing)
    enabled, got, same = launchforge.autostart_state(TEST_KEY, TEST_NAME)
    assert enabled and not same, '指向不存在的文件应判为不一致'
    print("[5] 指向旧路径 → enabled=%s same=%s" % (enabled, same))

    healed = launchforge.heal_autostart_path(TEST_KEY, TEST_NAME)
    assert healed == cmd, healed
    assert launchforge.read_autostart(TEST_KEY, TEST_NAME) == cmd
    print("[6] 自愈 → %s" % healed)

    # 指向仍存在的文件时不该改写（避免抢走用户的另一份安装）
    raw_write('"%s"' % sys.executable)
    healed = launchforge.heal_autostart_path(TEST_KEY, TEST_NAME)
    assert healed == '', '目标仍存在时不应改写，实际返回 %r' % healed
    assert launchforge.read_autostart(TEST_KEY, TEST_NAME) == '"%s"' % sys.executable
    print("[7] 目标仍存在 → 不改写 ✅")

    # ---------- 3. 面板反映真实状态 ----------
    raw_write(cmd)
    dlg = launchforge.SettingsDialog(key_path=TEST_KEY, value_name=TEST_NAME)
    assert dlg.row_autostart.is_checked(), '注册表已开启时面板应显示为开'
    print("[8] 面板初始状态 = %s（与注册表一致）" % dlg.row_autostart.is_checked())

    size = (dlg.width(), dlg.height())
    assert size == (launchforge.SettingsDialog.WIDTH, launchforge.SettingsDialog.HEIGHT)
    assert size[0] <= 460 and size[1] <= 280, '设置窗口应保持小尺寸：%s' % (size,)
    print("[9] 窗口尺寸 = %dx%d（受限）" % size)

    # 内容不溢出：提示行与关闭按钮都要落在可视区内
    # 未 show 时布局不会生效，y 值还是构造时的默认值，必须先激活布局
    dlg.layout().activate()
    app.processEvents()
    hint_bottom = dlg.hint.y() + dlg.hint.height()
    assert hint_bottom <= dlg.height() - 16, '提示行溢出：%d > %d' % (hint_bottom, dlg.height() - 16)
    btn_bottom = dlg.btn_close.y() + dlg.btn_close.height()
    assert btn_bottom <= dlg.height() - 12, '关闭按钮溢出：%d' % btn_bottom
    assert dlg.hint.y() > dlg.row_autostart.y() + dlg.row_autostart.height(), '提示行应在设置卡片下方'
    print("[10] 布局不溢出：卡片底=%d，提示行底=%d，按钮底=%d，窗高=%d"
          % (dlg.row_autostart.y() + dlg.row_autostart.height(),
             hint_bottom, btn_bottom, dlg.height()))

    # ---------- 4. 点整行 → 关闭自启动 ----------
    QTest.mouseClick(dlg.row_autostart, Qt.LeftButton, pos=QPoint(40, 45))
    app.processEvents()
    assert launchforge.read_autostart(TEST_KEY, TEST_NAME) == '', '点整行应关闭自启动'
    assert not dlg.row_autostart.is_checked()
    print("[11] 点整行 → 注册表已删除，开关=%s" % dlg.row_autostart.is_checked())

    # ---------- 5. 点开关本身 → 重新开启 ----------
    sw = dlg.row_autostart.switch
    QTest.mouseClick(sw, Qt.LeftButton, pos=QPoint(sw.width() // 2, sw.height() // 2))
    app.processEvents()
    assert launchforge.read_autostart(TEST_KEY, TEST_NAME) == cmd, '点开关应重新开启'
    print("[12] 点开关 → 已写回 %s" % launchforge.read_autostart(TEST_KEY, TEST_NAME))

    # ---------- 6. 写失败回滚 ----------
    from PyQt5.QtWidgets import QMessageBox

    warned = []
    real_info = QMessageBox.warning
    real_set = launchforge.set_autostart
    QMessageBox.warning = staticmethod(lambda *a, **k: warned.append(a[2]) or QMessageBox.Ok)
    launchforge.set_autostart = lambda *a, **k: (False, '模拟写入失败')
    try:
        dlg.row_autostart.set_checked(False)          # 尝试关闭
        app.processEvents()
    finally:
        launchforge.set_autostart = real_set
        QMessageBox.warning = real_info
    assert warned, '写失败应弹提示'
    assert dlg.row_autostart.is_checked(), '写失败后开关必须回滚到原状态'
    assert launchforge.read_autostart(TEST_KEY, TEST_NAME) == cmd
    print("[13] 写失败 → 回滚为开，提示：%s" % warned[0].splitlines()[0])

    # ---------- 7. 悬停高亮（渲染像素级验证） ----------
    row = dlg.row_autostart
    row.resize(360, launchforge.SettingRow.HEIGHT)
    row._set_hover(False)
    normal = row.grab().toImage()
    row._set_hover(True)
    hover = row.grab().toImage()

    def px(img, x, y):
        c = img.pixelColor(x, y)
        return (c.red(), c.green(), c.blue())

    # 边框：常态 #E2DACB → 悬停 #B79A5E（明显更深更金）
    border_normal = px(normal, row.width() // 2, 1)
    border_hover = px(hover, row.width() // 2, 1)
    # 卡片内部：常态 #FFFDF8 → 悬停 #FFFFFF
    fill_normal = px(normal, row.width() // 2, 30)
    fill_hover = px(hover, row.width() // 2, 30)
    assert border_normal != border_hover, '边框颜色应随悬停变化'
    assert fill_normal != fill_hover, '底色应随悬停变化'
    assert sum(border_hover) < sum(border_normal), '悬停边框应更深（转金）'
    print("[14] 悬停：边框 %s → %s；底色 %s → %s"
          % (border_normal, border_hover, fill_normal, fill_hover))

    # 左侧竖条：悬停时加长加粗
    bar_normal = px(normal, 8, 14)
    bar_hover = px(hover, 8, 14)
    assert bar_normal != bar_hover, '状态竖条应随悬停变化'
    print("[15] 状态竖条：{%d,%d,%d} → {%d,%d,%d}（悬停加长）" % (bar_normal + bar_hover))

    # 开关自身的悬浮环
    sw2 = launchforge.ToggleSwitch(False)
    sw2.resize(sw2.size())
    sw2.set_hover(False)
    a = sw2.grab().toImage()
    sw2.set_hover(True)
    b = sw2.grab().toImage()
    diff = sum(1 for y in range(a.height()) for x in range(a.width())
               if a.pixelColor(x, y) != b.pixelColor(x, y))
    assert diff > 40, '开关悬停应有明显的环，变化像素 %d' % diff
    print("[16] 开关悬停变化像素 = %d" % diff)

    # ---------- 8. 尺寸常量 ----------
    assert launchforge.ToggleSwitch.WIDTH == 52 and launchforge.ToggleSwitch.HEIGHT == 28
    assert launchforge.SettingRow.HEIGHT == 90
    print("[17] 控件尺寸：开关 52x28，设置行高 90 ✅")

    dlg.close()
finally:
    launchforge.set_autostart(False, TEST_KEY, TEST_NAME)
    clean_key()
    shutil.rmtree(SANDBOX, ignore_errors=True)

assert launchforge.read_autostart(TEST_KEY, TEST_NAME) == '', '沙箱键应已清理'
assert launchforge.read_autostart() == REAL_READ_BEFORE, '真实 Run 键不应被测试触碰'
print("[18] 沙箱已清理，真实 Run 键未被触碰 ✅")

print("\n需求 10 验收通过：设置面板可开机自启动，开关与注册表双向一致，悬停高亮可见。")
