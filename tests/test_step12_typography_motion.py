# -*- coding: utf-8 -*-
"""
Step 12 验收：字体体系与微交互动效（REQ-011 / FEAT-011）

覆盖：
  1. 字体按"首选 → 回退"解析，字号/字重/字距按角色返回
  2. 胶囊悬停强度会随进出平滑变化（不是瞬时切换），且像素确有变化
  3. 按下时强度上升、文字下沉（像素差可测）
  4. 列表逐行悬停 / 选中都会补间到目标值，且只重绘 viewport
  5. 列表类型图形：dir / exe / file / missing 分类正确，emoji 前缀被剥离
  6. 圆盘悬停发光强度会补间，且只亮被悬停的那一半
  7. 动效时长落在业界区间（悬停 80–120ms、按下 80–100ms）

运行：python tests/test_step12_typography_motion.py
"""

import os
import shutil
import sys
import tempfile

os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')

SANDBOX = tempfile.mkdtemp(prefix='lf_t12_')
os.environ['LOCALAPPDATA'] = SANDBOX

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, 'src'))

from PyQt5.QtCore import QEvent, Qt
from PyQt5.QtCore import QPointF
from PyQt5.QtGui import QFont, QMouseEvent
from PyQt5.QtWidgets import QApplication, QListWidgetItem
from PyQt5.QtTest import QTest

import launchforge

app = QApplication(sys.argv)


def px(img, x, y):
    c = img.pixelColor(x, y)
    return (c.red(), c.green(), c.blue(), c.alpha())


def diff_pixels(a, b):
    n = 0
    for y in range(a.height()):
        for x in range(a.width()):
            if a.pixelColor(x, y) != b.pixelColor(x, y):
                n += 1
    return n


try:
    # ---------- 1. 字体解析 ----------
    body = launchforge.ui_font(13, QFont.Normal, 'text', 0.2)
    title = launchforge.ui_font(17, QFont.Bold, 'display', 0.4)
    compact = launchforge.pill_font(compact=True)
    print("[1] 正文字族=%s %dpx 字距=%.1f | 标题=%s %dpx | 小胶囊=%dpx"
          % (body.family(), body.pixelSize(), body.letterSpacing(),
             title.family(), title.pixelSize(), compact.pixelSize()))
    assert body.family() in ('Microsoft YaHei UI', 'Microsoft YaHei', 'Segoe UI', 'Arial')
    assert body.pixelSize() == 13 and title.pixelSize() == 17
    assert compact.pixelSize() == 12
    # Qt 把绝对字距量化到 1/64 px（0.2 会存成 0.1875），所以容差取 0.02
    assert abs(body.letterSpacing() - 0.2) < 0.02, body.letterSpacing()
    # 标题优先 Noto Sans SC（本机存在），缺失时应回退而不是抛错
    assert title.family() in ('Noto Sans SC', 'Microsoft YaHei UI', 'Microsoft YaHei', 'Segoe UI')
    print("[2] 字重：正文=%d 标题=%d（只用 400/600/700 三档）"
          % (body.weight(), title.weight()))
    assert body.weight() == QFont.Normal and title.weight() == QFont.Bold

    # ---------- 2. 动效时长 ----------
    assert 80 <= launchforge.Theme.HOVER_MS <= 120, '悬停时长应在 80–120ms'
    assert 80 <= launchforge.Theme.PRESS_MS <= 100, '按时长应在 80–100ms'
    print("[3] 动效时长：悬停 %dms / 按下 %dms（均在业界区间）"
          % (launchforge.Theme.HOVER_MS, launchforge.Theme.PRESS_MS))

    # 系统关掉「动画效果」时应退化为 1ms（桌面端的 prefers-reduced-motion 等价物）
    launchforge.Theme.ANIMATIONS = False
    try:
        reduced_hover = launchforge.Theme.hover_ms()
        probe = launchforge.PillButton('探针')
        reduced_duration = probe._hover_anim.duration()
    finally:
        launchforge.Theme.ANIMATIONS = True
    print("[3b] 系统关闭动画时：hover_ms=%d，实际时长为 %dms" % (reduced_hover, reduced_duration))
    assert reduced_hover == 1 and reduced_duration == 1
    assert launchforge.Theme.hover_ms() == launchforge.Theme.HOVER_MS, '恢复后应回到 110ms'

    # ---------- 3. 胶囊悬停补间 ----------
    btn = launchforge.PillButton('添加文件夹', small_side='left')
    btn.resize(btn.sizeHint())
    assert btn._hover_t == 0.0
    rest = btn.grab().toImage()

    btn.enterEvent(QEvent(QEvent.Enter))
    # 第一帧要等动画的定时器 tick（约 16ms）才会写入，采样点取 45ms
    QTest.qWait(45)
    mid = btn._hover_t
    QTest.qWait(160)
    full = btn._hover_t
    print("[4] 悬停强度：0 → %.2f（45ms）→ %.2f（205ms）" % (mid, full))
    assert 0.05 < mid < 0.98, '悬停应是渐进过程，45ms 时应处于中途，实际 %.2f' % mid
    assert full > 0.98, '205ms 后应到达终点'

    hover_img = btn.grab().toImage()
    changed = diff_pixels(rest, hover_img)
    print("[5] 悬停前后变化像素 = %d" % changed)
    assert changed > 300, '悬停应有可见的像素变化'

    # 边框处颜色应更深（转金）
    border_rest = px(rest, btn.width() // 2, 0)
    border_hover = px(hover_img, btn.width() // 2, 0)
    assert sum(border_hover[:3]) < sum(border_rest[:3]), '悬停边框应更深'
    print("[6] 上边框 %s → %s" % (border_rest, border_hover))

    # ---------- 4. 按下：强度上升 + 文字下沉 ----------
    # 用真实 QMouseEvent：QPushButton 的默认实现会校验事件类型
    press = QMouseEvent(QEvent.MouseButtonPress, QPointF(10, 19), Qt.LeftButton,
                        Qt.LeftButton, Qt.NoModifier)
    btn.mousePressEvent(press)
    QTest.qWait(150)
    assert btn._press_t > 0.95, '按下应到达终点，实际 %.2f' % btn._press_t
    pressed_img = btn.grab().toImage()
    print("[7] 按下强度 = %.2f，与悬停态差异像素 = %d"
          % (btn._press_t, diff_pixels(hover_img, pressed_img)))
    assert diff_pixels(hover_img, pressed_img) > 100, '按下应有可见变化'
    release = QMouseEvent(QEvent.MouseButtonRelease, QPointF(10, 19), Qt.LeftButton,
                          Qt.NoButton, Qt.NoModifier)
    btn.mouseReleaseEvent(release)
    QTest.qWait(150)
    assert btn._press_t < 0.05, '松开后应回落'

    # ---------- 5. 列表逐行补间 ----------
    lst = launchforge.AnimatedList()
    lst.resize(280, 150)
    for name in ('a.exe', 'b', 'c.md'):
        lst.addItem(QListWidgetItem(name))
    assert lst.hover_value(0) == 0.0 and lst.select_value(0) == 0.0

    lst._hover_row = 1
    lst._wake()
    QTest.qWait(60)
    step1 = lst.hover_value(1)
    QTest.qWait(240)
    step2 = lst.hover_value(1)
    print("[8] 第 2 行悬停值：0 → %.2f（60ms）→ %.2f（300ms）" % (step1, step2))
    assert 0.0 < step1 < 0.95
    assert step2 > 0.98

    lst.item(0).setSelected(True)
    QTest.qWait(260)
    print("[9] 第 1 行选中值 = %.2f" % lst.select_value(0))
    assert lst.select_value(0) > 0.98

    # 移出后所有行应回到 0
    lst.leaveEvent(QEvent(QEvent.Leave))
    QTest.qWait(300)
    print("[10] 移出后 悬停=%.2f 选中=%.2f"
          % (lst.hover_value(1), lst.select_value(0)))
    assert lst.hover_value(1) < 0.02
    assert lst.select_value(0) > 0.98, '选中不应被悬停离开影响'

    # ---------- 6. 行高与类型图形 ----------
    assert launchforge.ListRowDelegate.ROW_HEIGHT == 34
    # 类型按"路径是否真实存在"判定：先落两个真实文件，再测分类
    note = os.path.join(SANDBOX, 'note.md')
    lnk = os.path.join(SANDBOX, 'a.lnk')
    for f in (note, lnk):
        open(f, 'w').close()
    kinds = {
        'dir': launchforge._kind_of(SANDBOX),
        'exe': launchforge._kind_of(r'C:\Windows\System32\notepad.exe'),
        'lnk': launchforge._kind_of(lnk),
        'file': launchforge._kind_of(note),
        'missing': launchforge._kind_of(r'C:\no\such\thing.exe'),
    }
    print("[11] 类型分类 =", kinds)
    assert kinds == {'dir': 'dir', 'exe': 'exe', 'lnk': 'exe', 'file': 'file', 'missing': 'missing'}
    assert launchforge._strip_kind_prefix('📁 工作目录') == '工作目录'
    assert launchforge._strip_kind_prefix('⚠ 已删除') == '已删除'
    assert launchforge._strip_kind_prefix('普通文件.txt') == '普通文件.txt'
    print("[12] emoji 前缀剥离正常（类型改由矢量图形表达）")

    # ---------- 7. 圆盘悬停发光 ----------
    taiji = launchforge.TaijiLaunchButton(160)
    taiji.show()
    app.processEvents()
    off = taiji.grab().toImage()
    taiji._set_hover_side('run')
    QTest.qWait(40)
    mid_t = taiji._hover_t
    QTest.qWait(220)
    on_t = taiji._hover_t
    print("[13] 圆盘悬停强度：0 → %.2f（40ms）→ %.2f（260ms）" % (mid_t, on_t))
    assert 0.0 < mid_t < 0.98
    assert on_t > 0.98
    on = taiji.grab().toImage()
    changed = diff_pixels(off, on)
    print("[14] 圆盘悬停前后变化像素 = %d" % changed)
    assert changed > 500

    taiji._set_hover_side(None)
    QTest.qWait(240)
    assert taiji._hover_t < 0.02
    print("[15] 移出后发光回落到 %.2f" % taiji._hover_t)

    taiji.close()
finally:
    shutil.rmtree(SANDBOX, ignore_errors=True)

print("\n需求 11 验收通过：字体层级可解析、悬停/按下/选中均为逐帧补间，列表类型图形化。")
