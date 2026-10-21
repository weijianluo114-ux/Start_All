# -*- coding: utf-8 -*-
"""
Step 16 验收：焦点环不再留虚线（BUG-006 / v1.14.1）

覆盖：
  1. 鼠标点出来的焦点不画任何环：与"无焦点"逐像素完全一致（0 差异）
  2. 键盘 Tab 导航仍可见焦点环：差异 > 200 像素，且在按钮内侧（不越界）
  3. 三个自绘控件一致：PillButton / ToggleSwitch / SizeSlider
  4. 源码里不再有 DashLine / DotLine（虚线段彻底移除，改为实线细环）
  5. 真实点击主窗口「设置」胶囊后，胶囊上没有环；面板关闭后依然没有
  6. 切窗口（ActiveWindowFocusReason）不算键盘导航，同样不画

运行：python tests/test_step16_focus_ring.py
（必须真实字体平台：焦点环是 1px 细线，offscreen 的绘制差异会被缩放吃掉）
"""

import os
import re
import sys
import tempfile

os.environ['QT_QPA_PLATFORM'] = 'windows'

SANDBOX = tempfile.mkdtemp(prefix='lf_t16_')
os.environ['LOCALAPPDATA'] = SANDBOX

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, 'src'))

from PyQt5.QtCore import QPoint, Qt
from PyQt5.QtTest import QTest
from PyQt5.QtWidgets import QApplication

import launchforge

app = QApplication(sys.argv)
launchforge.heal_autostart_path = lambda: None


def shot(widget):
    widget.show()
    app.processEvents()
    image = widget.grab().toImage()
    return image


def diff(a, b):
    """两张同尺寸图的差异像素数。"""
    assert (a.width(), a.height()) == (b.width(), b.height())
    count = 0
    for y in range(a.height()):
        for x in range(a.width()):
            if a.pixel(x, y) != b.pixel(x, y):
                count += 1
    return count


def inside_and_edge(before, after, margin=3):
    inner = edge = 0
    for y in range(before.height()):
        for x in range(before.width()):
            if before.pixel(x, y) == after.pixel(x, y):
                continue
            if (x < margin or y < margin
                    or x >= before.width() - margin or y >= before.height() - margin):
                edge += 1
            else:
                inner += 1
    return inner, edge


try:
    # ---------- 1. PillButton ----------
    btn = launchforge.PillButton('设置', small_side='right')
    no_focus = shot(btn)

    btn.setFocus(Qt.MouseFocusReason)
    app.processEvents()
    mouse_focus = btn.grab().toImage()
    mouse_diff = diff(no_focus, mouse_focus)
    print("[1] 胶囊 · 鼠标焦点 vs 无焦点：差异 %d 像素，_kb_focus=%s"
          % (mouse_diff, btn._kb_focus))
    assert mouse_diff == 0, '鼠标点击后仍画了焦点环（差异 %d 像素）' % mouse_diff
    assert btn._kb_focus is False

    btn.clearFocus()
    app.processEvents()
    btn.setFocus(Qt.TabFocusReason)
    app.processEvents()
    tab_focus = btn.grab().toImage()
    tab_diff = diff(no_focus, tab_focus)
    # 环画在内缩 2px 处，只要求它不压到最外 1px——压边会变成"描边"而不是焦点提示
    inner, edge = inside_and_edge(no_focus, tab_focus, margin=1)
    print("[2] 胶囊 · 键盘焦点 vs 无焦点：差异 %d 像素（内侧 %d / 贴边 %d），_kb_focus=%s"
          % (tab_diff, inner, edge, btn._kb_focus))
    assert btn._kb_focus is True
    assert tab_diff > 200, '键盘导航时应有可见焦点环（差异只有 %d）' % tab_diff
    assert edge == 0, '焦点环压到按钮边缘（%d 像素），会显得像描边' % edge

    # 切窗口的焦点不算键盘导航
    btn.clearFocus()
    app.processEvents()
    btn.setFocus(Qt.ActiveWindowFocusReason)
    app.processEvents()
    active_diff = diff(no_focus, btn.grab().toImage())
    print("[3] 胶囊 · 切窗口焦点 vs 无焦点：差异 %d 像素" % active_diff)
    assert active_diff == 0, '切窗口重新获得焦点时不该画环'
    btn.close()

    # ---------- 2. ToggleSwitch ----------
    switch = launchforge.ToggleSwitch(True)
    base = shot(switch)
    switch.setFocus(Qt.MouseFocusReason)
    app.processEvents()
    d = diff(base, switch.grab().toImage())
    print("[4] 开关 · 鼠标焦点：差异 %d 像素，_kb_focus=%s" % (d, switch._kb_focus))
    assert d == 0, '鼠标点开关后留下焦点框（%d 像素）' % d

    switch.clearFocus()
    app.processEvents()
    switch.setFocus(Qt.TabFocusReason)
    app.processEvents()
    kd = diff(base, switch.grab().toImage())
    print("[5] 开关 · 键盘焦点：差异 %d 像素" % kd)
    assert kd > 100, '键盘导航时开关应有可见焦点框'
    switch.close()

    # ---------- 3. SizeSlider ----------
    slider = launchforge.SizeSlider(11, 17, 13)
    base = shot(slider)
    slider.setFocus(Qt.MouseFocusReason)
    app.processEvents()
    d = diff(base, slider.grab().toImage())
    print("[6] 滑块 · 鼠标焦点：差异 %d 像素" % d)
    assert d == 0, '拖动滑块后留下焦点框（%d 像素）' % d

    slider.clearFocus()
    app.processEvents()
    slider.setFocus(Qt.TabFocusReason)
    app.processEvents()
    kd = diff(base, slider.grab().toImage())
    print("[7] 滑块 · 键盘焦点：差异 %d 像素" % kd)
    assert kd > 100, '键盘导航时滑块应有可见焦点框'
    slider.close()

    # ---------- 4. 源码里不再有虚线段 ----------
    src = open(os.path.join(ROOT, 'src', 'launchforge.py'), encoding='utf-8').read()
    dashes = re.findall(r'Qt\.(DashLine|DotLine|DashDotLine|CustomDashLine)', src)
    print("[8] 源码中的虚线样式：%d 处 %s" % (len(dashes), dashes or '（无）'))
    assert not dashes, '仍在使用虚线段：%s' % dashes

    # ---------- 5. 真实点击「设置」胶囊 ----------
    launchforge.CONFIG_FILE = os.path.join(SANDBOX, 'c.json')
    window = launchforge.LauncherWindow()
    window.resize(560, 700)
    window.move(60, 60)
    window.show()
    # 必须真正成为活动窗口：移到屏幕外时 isActiveWindow() 为 False，
    # setFocus(TabFocusReason) 拿不到系统焦点，hasFocus() 恒为 False，环也就无从验证。
    QTest.qWaitForWindowExposed(window)
    window.raise_()
    window.activateWindow()
    app.processEvents()
    assert window.isActiveWindow(), '主窗口未激活，键盘焦点断言会失真'

    # 断开点击信号：真面板是 exec_() 模态，测试里点一下就会卡在那里等用户。
    # 面板本身的行为由 T-014 / T-016 覆盖，这里只关心"点击后的焦点状态"。
    try:
        pill_signals = window.btn_settings.receivers(window.btn_settings.clicked)
        window.btn_settings.clicked.disconnect()
    except (TypeError, RuntimeError):
        pill_signals = 0
    print("[9a] 「设置」胶囊原有 clicked 接收者：%d 个（已断开）" % pill_signals)

    pill = window.btn_settings
    before = shot(window.centralWidget()).copy(pill.mapTo(window.centralWidget(),
                                                        QPoint(0, 0)).x(),
                                               pill.mapTo(window.centralWidget(),
                                                          QPoint(0, 0)).y(),
                                               pill.width(), pill.height())
    QTest.mouseClick(pill, Qt.LeftButton)
    app.processEvents()
    after = window.centralWidget().grab().toImage().copy(
        pill.mapTo(window.centralWidget(), QPoint(0, 0)).x(),
        pill.mapTo(window.centralWidget(), QPoint(0, 0)).y(),
        pill.width(), pill.height())
    click_diff = diff(before, after)
    print("[9] 点击「设置」胶囊：差异 %d 像素，_kb_focus=%s"
          % (click_diff, pill._kb_focus))
    assert pill.hasFocus(), '点击后按钮应持有焦点（这正是问题发生的条件）'
    assert pill._kb_focus is False, '鼠标点击被当成了键盘导航'
    # 悬停/按下动画会让像素有少量变化，但**不能**出现环（环至少 200 像素）
    assert click_diff < 200, '点击后胶囊上出现了不该有的环（%d 像素）' % click_diff

    # ---------- 6. 打开真实面板再关闭，胶囊仍无环 ----------
    dialog = launchforge.SettingsDialog(window, key_path=r'Software\LF16\Run',
                                       value_name='S')
    dialog.show()
    app.processEvents()
    focused = app.focusWidget()
    print("[10] 设置面板首焦点：%s（面板本身不画焦点环）"
          % (type(focused).__name__ if focused else 'None'))
    dialog.close()
    app.processEvents()

    after_panel = window.centralWidget().grab().toImage().copy(
        pill.mapTo(window.centralWidget(), QPoint(0, 0)).x(),
        pill.mapTo(window.centralWidget(), QPoint(0, 0)).y(),
        pill.width(), pill.height())
    panel_diff = diff(before, after_panel)
    print("[11] 关闭面板后，胶囊与初始状态差异 %d 像素，_kb_focus=%s"
          % (panel_diff, pill._kb_focus))
    assert panel_diff < 200, '关闭设置面板后胶囊上残留了焦点环'

    # ---------- 7. 键盘 Tab 仍可到达并有提示 ----------
    window.activateWindow()
    app.processEvents()
    # 必须先 clearFocus：Qt 对"已经有焦点"的 setFocus 不再发 FocusIn，
    # 焦点来源就不会更新（真实场景里按 Tab 是移走再移回，一定会有 FocusIn）
    pill.clearFocus()
    app.processEvents()
    pill.setFocus(Qt.TabFocusReason)
    app.processEvents()
    assert pill.hasFocus(), 'Tab 未能聚焦到「设置」胶囊'
    assert pill._kb_focus is True, '键盘聚焦没被识别'
    tabshot = window.centralWidget().grab().toImage().copy(
        pill.mapTo(window.centralWidget(), QPoint(0, 0)).x(),
        pill.mapTo(window.centralWidget(), QPoint(0, 0)).y(),
        pill.width(), pill.height())
    tab_click_diff = diff(before, tabshot)
    print("[12] Tab 聚焦到胶囊：差异 %d 像素" % tab_click_diff)
    assert tab_click_diff > 150, '键盘用户看不到焦点在哪'

    window.close()
    app.processEvents()

    print("\nSTEP 16 全部通过：鼠标焦点不再留虚线，键盘导航仍有实线细环。")

finally:
    import shutil
    shutil.rmtree(SANDBOX, ignore_errors=True)
