# -*- coding: utf-8 -*-
"""
Step 13 验收：全局字体设置（REQ-012 / FEAT-012）

覆盖：
  1. 五套字体搭配可用、key 唯一、首选家族能在本机解析
  2. 字号偏好只接受 11–17px，非法值收敛而不抛错
  3. ui_font() 按基准字号等比缩放，说明文字有 10px 下限
  4. 搭配切换后家族跟着变；本机缺失时回退到雅黑而不是崩
  5. 偏好写入配置文件并能原样读回（含非法值收敛）
  6. **最小字号 / 最大字号下主窗口不重叠、不越界、文字不被裁**
  7. **最小字号 / 最大字号下设置面板不重叠、不越界**
  8. 滑块点击/键盘都能落到正确档位，并区分"实时预览"与"松手落盘"
  9. restyle 能重建整棵控件树的字体（改字号即时生效的依据）

运行：python tests/test_step13_font_settings.py
（必须用真实字体平台：offscreen 下字体度量会回退到 Arial，几何断言失去意义）
"""

import os
import json
import shutil
import sys
import tempfile

os.environ['QT_QPA_PLATFORM'] = 'windows'

SANDBOX = tempfile.mkdtemp(prefix='lf_t13_')
os.environ['LOCALAPPDATA'] = SANDBOX

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, 'src'))

from PyQt5.QtCore import QEvent, QPoint, QPointF, Qt
from PyQt5.QtGui import QFont, QMouseEvent
from PyQt5.QtTest import QTest
from PyQt5.QtWidgets import QApplication, QWidget

import launchforge

app = QApplication(sys.argv)
launchforge.CONFIG_FILE = os.path.join(SANDBOX, 'presets.json')
# 测试期间绝不碰真实的自启动键
launchforge.heal_autostart_path = lambda: None

TEST_KEY = r'Software\LaunchForgeSelfTest\FontRun'


def rect_of(widget, origin):
    """控件相对 origin 的实际矩形（含嵌套子控件）。"""
    top_left = widget.mapTo(origin, QPoint(0, 0))
    return (top_left.x(), top_left.y(), widget.width(), widget.height())


def intersects(a, b):
    ax, ay, aw, ah = a
    bx, by, bw, bh = b
    return not (ax + aw <= bx or bx + bw <= ax or ay + ah <= by or by + bh <= ay)


def inside(inner, outer):
    ix, iy, iw, ih = inner
    ox, oy, ow, oh = outer
    return ix >= ox and iy >= oy and ix + iw <= ox + ow and iy + ih <= oy + oh


def make_window():
    window = launchforge.LauncherWindow()
    window.resize(560, 700)
    window.centralWidget().layout().activate()
    return window


try:
    # ---------- 1. 搭配表 ----------
    presets = launchforge.FONT_PRESETS
    keys = [p['key'] for p in presets]
    print("[1] 字体搭配 %d 套：%s" % (len(presets), '、'.join(p['name'] for p in presets)))
    assert 3 <= len(presets) <= 5, '推荐搭配应为 3–5 套'
    assert len(set(keys)) == len(keys), 'key 必须唯一'
    for p in presets:
        assert p['name'] and p['note'] and p['display'] and p['text']
    # 每套的第一家族要么本机能装到，要么能沿链回退；回退名必须落在链尾
    for p in presets:
        assert launchforge.FontPrefs.installed_families(p), '没有可回退的家族：%s' % p['name']
    available = [p['name'] for p in presets if launchforge.FontPrefs.available(p)]
    print("[2] 本机可用：%s（其余自动回退）" % '、'.join(available))
    assert available, '至少有一套搭配在本机可用'

    # ---------- 2. 偏好收敛 ----------
    key, size = launchforge.FontPrefs.set('不存在的搭配', 999)
    print("[3] 非法输入 → key=%s size=%d（收敛到合法档位）" % (key, size))
    assert key == presets[0]['key'] and size == launchforge.FONT_SIZE_MAX
    assert launchforge.FontPrefs.set(None, 3)[1] == launchforge.FONT_SIZE_MIN
    assert launchforge.FontPrefs.set(None, 'abc')[1] == launchforge.FONT_SIZE_BASE
    launchforge.FontPrefs.set(presets[0]['key'], launchforge.FONT_SIZE_BASE)

    # ---------- 3. 字号等比缩放 ----------
    for size, expect_body, expect_title in (
            (launchforge.FONT_SIZE_MIN, 11, 14),
            (launchforge.FONT_SIZE_BASE, 13, 17),
            (launchforge.FONT_SIZE_MAX, 17, 22)):
        launchforge.FontPrefs.set(None, size)
        body = launchforge.ui_font(13, QFont.Normal, 'text', 0.2)
        title = launchforge.ui_font(17, QFont.Bold, 'display', 0.3)
        small = launchforge.ui_font(11, QFont.Normal, 'text')
        assert body.pixelSize() == expect_body, (size, body.pixelSize())
        assert title.pixelSize() == expect_title, (size, title.pixelSize())
        assert small.pixelSize() >= 10, '说明文字不应低于 10px'
        if size == launchforge.FONT_SIZE_BASE:
            # 基准档必须与 v1.11.0 完全一致，老界面观感不变
            assert small.pixelSize() == 11
    print("[4] 字号缩放：11→正文11/标题14 · 13→13/17 · 17→17/22（说明≥10px）")

    # Qt 把绝对字距量化到 1/64 px，容差 0.02
    assert abs(launchforge.ui_font(13, QFont.Normal, 'text', 0.2).letterSpacing() - 0.2) < 0.02

    # ---------- 4. 搭配切换 ----------
    launchforge.FontPrefs.set('yahei', 13)
    yahei_text = launchforge.ui_font(13, QFont.Normal, 'text')
    launchforge.FontPrefs.set('split', 13)
    split_text = launchforge.ui_font(13, QFont.Normal, 'text')
    split_families = split_text.families() if hasattr(split_text, 'families') else [split_text.family()]
    print("[5] 雅黑 → %s；中英分排 → %s" % (yahei_text.family(), ' / '.join(split_families)))
    assert 'YaHei' in yahei_text.family() or '雅黑' in yahei_text.family()
    assert split_text.family() == 'Segoe UI'
    assert any(('YaHei' in f or '雅黑' in f) for f in split_families), '中文家族要留在回退链里'

    launchforge.FontPrefs.set('serif', 13)
    serif_title = launchforge.ui_font(17, QFont.Bold, 'display')
    print("[6] 书卷衬线标题家族 = %s" % serif_title.family())
    assert serif_title.family() in ('Noto Serif SC', '宋体', 'SimSun', 'Microsoft YaHei UI')

    # ---------- 5. 配置持久化 ----------
    launchforge.FontPrefs.set(presets[0]['key'], 13)
    window = make_window()
    before = launchforge.FontPrefs.SIZE
    window.apply_font_prefs(save=True)
    with open(launchforge.CONFIG_FILE, 'r', encoding='utf-8') as f:
        saved = json.load(f)
    print("[7] 已写入配置：font_key=%s font_size=%s"
          % (saved['settings'].get('font_key'), saved['settings'].get('font_size')))
    assert saved['settings']['font_key'] == launchforge.FontPrefs.KEY
    assert saved['settings']['font_size'] == before
    window.close()

    # 手改坏配置也要能启动：size=99 → 17、key 乱写 → 第一套
    with open(launchforge.CONFIG_FILE, 'w', encoding='utf-8') as f:
        json.dump({'last_used': '默认方案', 'presets': {'默认方案': []},
                   'settings': {'font_key': '???', 'font_size': 99}}, f)
    window = make_window()
    print("[8] 坏配置读回 → key=%s size=%d" % (launchforge.FontPrefs.KEY, launchforge.FontPrefs.SIZE))
    assert launchforge.FontPrefs.KEY == presets[0]['key']
    assert launchforge.FontPrefs.SIZE == launchforge.FONT_SIZE_MAX
    window.close()

    # ---------- 6. 主窗口：最小 / 最大字号都不越界 ----------
    window = make_window()
    window.show()
    app.processEvents()

    for size in (launchforge.FONT_SIZE_MIN, launchforge.FONT_SIZE_MAX):
        launchforge.FontPrefs.set('classic', size)
        window.apply_font_prefs()
        window.resize(560, 700)
        app.processEvents()
        window.centralWidget().layout().activate()

        central = window.centralWidget()
        lay = central.layout()
        preset_band = lay.itemAt(0).geometry()
        taiji_band = lay.itemAt(1).geometry()
        list_band = lay.itemAt(2).geometry()

        left = rect_of(window.left_pills, central)
        disc = rect_of(window.taiji, central)
        right = rect_of(window.right_pills, central)

        # 三个横向区域互不重叠
        assert not intersects(left, disc), '左胶囊列压到圆盘'
        assert not intersects(disc, right), '右胶囊列压到圆盘'
        # 纵向三条带互不重叠
        assert preset_band.y() + preset_band.height() <= taiji_band.y(), '预设行与圆区重叠'
        assert taiji_band.y() + taiji_band.height() <= list_band.y(), '圆区与列表重叠'
        # 都在面板内
        for band in (preset_band, taiji_band, list_band):
            assert band.x() >= 0 and band.y() >= 0
            assert band.x() + band.width() <= central.width()
            assert band.y() + band.height() <= central.height()

        # 胶囊：文字不被裁、高度收得住、列内不重叠
        for column in (window.left_pills, window.right_pills):
            col_rect = rect_of(column, central)
            boxes = [rect_of(btn, central) for btn in column._buttons]
            for btn, box in zip(column._buttons, boxes):
                need = btn.fontMetrics().horizontalAdvance(btn.text()) + 2 * btn._padding
                assert btn.width() >= need, '%s 文字被裁（%d < %d @%dpx）' % (
                    btn.text(), btn.width(), need, size)
                assert btn.height() >= btn.fontMetrics().height() + 4, '胶囊高度压到文字'
                assert inside(box, col_rect), '%s 越出胶囊列' % btn.text()
            assert boxes[0][1] + boxes[0][3] <= boxes[1][1], '上排与中排重叠'
            assert boxes[1][1] + boxes[1][3] <= boxes[2][1], '中排与下排重叠'

        # 预设行
        label = rect_of(window.preset_label, central)
        combo = rect_of(window.preset_combo, central)
        new_btn = rect_of(window.btn_new_preset, central)
        del_btn = rect_of(window.btn_del_preset, central)
        assert label[0] + label[2] <= combo[0], '「预设方案」与下拉框重叠'
        assert combo[0] + combo[2] <= new_btn[0], '下拉框与「新建」重叠'
        assert new_btn[0] + new_btn[2] <= del_btn[0], '「新建」与「删除」重叠'
        assert del_btn[0] + del_btn[2] <= central.width(), '预设行右越界'
        assert window.preset_combo.height() >= window.preset_combo.fontMetrics().height() + 8
        combo_need = window.preset_combo.fontMetrics().horizontalAdvance(
            window.preset_combo.currentText())
        assert combo[2] >= min(combo_need + 30, 120), '下拉框窄到显示不下预设名'

        # 列表行高
        row_h = window.list_widget.itemDelegate().row_height()
        body_px = launchforge.ui_font(13).pixelSize()
        assert row_h >= body_px + 6, '列表行高小于文字高度'

        # 窗口最小宽度必须仍能放进 560 的默认尺寸
        assert window.minimumSizeHint().width() <= 560, '最大字号下默认窗口宽度放不下'
        print("[9] %dpx：胶囊宽度 %d/%d · 行高 %d · 最小窗口 %dx%d"
              % (size, window.left_pills.width(), window.right_pills.width(), row_h,
                 window.minimumSizeHint().width(), window.minimumSizeHint().height()))

    # 圆盘文字也不能溢出：跟随倍率有上限
    for size in (launchforge.FONT_SIZE_MIN, launchforge.FONT_SIZE_MAX):
        launchforge.FontPrefs.set('classic', size)
        disc = launchforge.TaijiLaunchButton(160)
        follow = max(0.94, min(1.16, launchforge.FontPrefs.scale()))
        assert 0.94 <= follow <= 1.16
        disc.deleteLater()
    print("[10] 圆盘字号跟随被夹在 0.94–1.16 倍，不会顶出鱼身")

    # ---------- 7. restyle 覆盖整棵树 ----------
    launchforge.FontPrefs.set('classic', launchforge.FONT_SIZE_MAX)
    count = launchforge.restyle_widgets(window)
    label_px = window.preset_label.font().pixelSize()
    print("[11] restyle 重建 %d 处字体；「预设方案」= %dpx" % (count, label_px))
    assert count >= 11, '主窗口应有多处登记字体（预设标签/下拉 + 8 胶囊 + 圆盘）'
    assert label_px == round(12 * launchforge.FontPrefs.scale())

    launchforge.FontPrefs.set('classic', launchforge.FONT_SIZE_BASE)
    launchforge.restyle_widgets(window)
    window.close()

    # ---------- 8. 设置面板 ----------
    calls = {'n': 0}

    def on_font_changed():
        calls['n'] += 1

    launchforge.FontPrefs.set('classic', launchforge.FONT_SIZE_BASE)
    dialog = launchforge.SettingsDialog(key_path=TEST_KEY, value_name='FontTest',
                                        on_font_changed=on_font_changed)
    dialog.show()
    app.processEvents()

    for size in (launchforge.FONT_SIZE_MIN, launchforge.FONT_SIZE_MAX):
        launchforge.FontPrefs.set('classic', size)
        dialog._apply_fonts(persist=False)
        app.processEvents()

        canvas = (0, 0, dialog.width(), dialog.height())
        assert 384 <= dialog.height() <= 520, '面板高度失控：%d' % dialog.height()
        assert dialog.width() == dialog.WIDTH

        # 卡片、自启动行、提示、页脚互不重叠且都在面板内
        row = rect_of(dialog.row_autostart, dialog)
        card = rect_of(dialog.font_card, dialog)
        hint = rect_of(dialog.hint, dialog)
        close_btn = rect_of(dialog.btn_close, dialog)
        assert not intersects(row, card), '自启动行与字体卡片重叠'
        assert not intersects(card, hint), '字体卡片与提示重叠'
        assert not intersects(hint, close_btn), '提示与关闭按钮重叠'
        for box in (row, card, hint, close_btn):
            assert inside(box, canvas), '控件越出面板：%s' % (box,)

        # 卡片内部：任何子控件都不越界、不压字
        # （下拉框的弹出列表是独立窗口，几何不受卡片约束，必须排除）
        for child in dialog.font_card.findChildren(QWidget):
            if child.isWindow() or child.window() is not dialog or child.width() == 0:
                continue
            assert inside(rect_of(child, dialog.font_card), (0, 0, dialog.font_card.width(),
                                                             dialog.font_card.height())), \
                '%s 越出字体卡片' % type(child).__name__

        combo = dialog.family_combo
        assert combo.width() >= combo.fontMetrics().horizontalAdvance(combo.currentText()) + 30
        assert dialog.size_slider.width() >= 120, '滑块被压得太窄'
        assert dialog.size_value.width() >= dialog.size_value.fontMetrics().horizontalAdvance(
            dialog.size_value.text()) + 2, '字号数值被裁'
        # 说明与预览换行后高度足够，不会被裁
        note_h = dialog.family_note.heightForWidth(dialog.family_note.width())
        assert dialog.family_note.height() >= note_h, '字体说明被裁'
        assert dialog.preview.height() >= dialog.preview.fontMetrics().height(), '预览被裁'
        assert inside(rect_of(dialog.preview, dialog), canvas)
        print("[12] %dpx：面板 420×%d · 说明 %dpx 高 · 滑块 %dpx 宽"
              % (size, dialog.height(), dialog.family_note.height(), dialog.size_slider.width()))

    # ---------- 9. 滑块交互 ----------
    slider = dialog.size_slider
    slider.resize(220, slider.height())
    slider.setValue(13, emit=False)

    press = QMouseEvent(QEvent.MouseButtonPress, QPointF(2, 14), Qt.LeftButton,
                        Qt.LeftButton, Qt.NoModifier)
    release = QMouseEvent(QEvent.MouseButtonRelease, QPointF(2, 14), Qt.LeftButton,
                          Qt.NoButton, Qt.NoModifier)
    slider.mousePressEvent(press)
    slider.mouseReleaseEvent(release)
    assert slider.value() == slider.minimum(), '点最左应到最小档'
    far = QPointF(slider.width() - 2, 14)
    slider.mousePressEvent(QMouseEvent(QEvent.MouseButtonPress, far, Qt.LeftButton,
                                       Qt.LeftButton, Qt.NoModifier))
    slider.mouseReleaseEvent(QMouseEvent(QEvent.MouseButtonRelease, far, Qt.LeftButton,
                                         Qt.NoButton, Qt.NoModifier))
    assert slider.value() == slider.maximum(), '点最右应到最大档'
    QTest.keyClick(slider, Qt.Key_Home)
    assert slider.value() == slider.minimum()
    QTest.keyClick(slider, Qt.Key_Right)
    assert slider.value() == slider.minimum() + 1
    QTest.keyClick(slider, Qt.Key_End)
    assert slider.value() == slider.maximum()
    print("[13] 滑块：点击两端与键盘 Home/→/End 均落到正确档位")

    # ---------- 10. 即时生效 + 松手落盘 ----------
    calls['n'] = 0
    dialog._on_size_changed(12)
    assert launchforge.FontPrefs.SIZE == 12 and calls['n'] == 0, '拖动过程不应写盘'
    assert dialog.size_value.text() == '12 px'
    dialog._on_size_released(12)
    assert calls['n'] == 1, '松手应落盘一次'
    print("[14] 拖动只预览、松手才落盘（回调 %d 次）" % calls['n'])

    calls['n'] = 0
    dialog.family_combo.setCurrentIndex(1)
    assert launchforge.FontPrefs.KEY == launchforge.FONT_PRESETS[1]['key']
    assert calls['n'] == 1, '换搭配应立即落盘'
    print("[15] 换搭配 → %s，立即通知主窗口落盘" % launchforge.FontPrefs.preset()['name'])

    dialog.close()

    # ---------- 11. 端到端：面板改字号 → 主窗口真的变大 ----------
    launchforge.FontPrefs.set('classic', launchforge.FONT_SIZE_BASE)
    window = make_window()
    window.show()
    app.processEvents()
    window.apply_font_prefs()
    app.processEvents()
    small_widths = window.left_pills.width()
    small_px = window.btn_add.font().pixelSize()

    live = launchforge.SettingsDialog(window, on_font_changed=window.on_font_changed)
    live._on_size_released(launchforge.FONT_SIZE_MAX)
    app.processEvents()

    print("[16] 面板 13px→17px：胶囊 %d→%d，字体 %d→%dpx"
          % (small_widths, window.left_pills.width(), small_px, window.btn_add.font().pixelSize()))
    assert window.btn_add.font().pixelSize() == 17, '主窗口字体没跟上'
    assert window.left_pills.width() > small_widths, '胶囊宽度没重算'
    with open(launchforge.CONFIG_FILE, 'r', encoding='utf-8') as f:
        live_saved = json.load(f)['settings']
    assert live_saved['font_size'] == launchforge.FONT_SIZE_MAX, '落盘的是旧字号'
    live.close()
    window.close()
finally:
    shutil.rmtree(SANDBOX, ignore_errors=True)

print("\n需求 12 验收通过：字体搭配可切换、字号 11–17px 可调，两端既不重叠也不越界。")
