# -*- coding: utf-8 -*-
"""
Step 14 验收：圆盘文字（REQ-013）

覆盖：
  1. 圆盘放大到 184（控件 216），左右列仍与圆心对齐
  2. 盘面字体是圆体（幼圆），且**不跟随**界面字体搭配变成宋体
  3. 每个字盒都完整落在自己那半鱼身内：不跨 S 缝隙、不压鱼眼、离盘沿 ≥4px
  4. 11px / 13px / 17px 全局字号下都成立（字号自适应）
  5. 文字不是纯白：暖金字芯 + 深可可描边
  6. 悬停时字本身会高亮（字芯变亮 + 出现柔光），且只亮被悬停的那一半
  7. 禁用态文字转灰；布局按 (直径, 字号, 字族) 缓存

运行：python tests/test_step14_taiji_text.py
（必须真实字体平台：offscreen 没有字体库，字宽会退化成 Arial）
"""

import math
import os
import shutil
import sys
import tempfile

os.environ['QT_QPA_PLATFORM'] = 'windows'

SANDBOX = tempfile.mkdtemp(prefix='lf_t14_')
os.environ['LOCALAPPDATA'] = SANDBOX

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, 'src'))

from PyQt5.QtCore import QPointF
from PyQt5.QtGui import QColor, QFontDatabase
from PyQt5.QtWidgets import QApplication

import launchforge

app = QApplication(sys.argv)
launchforge.heal_autostart_path = lambda: None


def luminance(color):
    c = QColor(color) if not isinstance(color, QColor) else color
    return 0.2126 * c.red() + 0.7152 * c.green() + 0.0722 * c.blue()


try:
    # ---------- 1. 直径 ----------
    btn = launchforge.TaijiLaunchButton()
    print("[1] 默认直径 %d，控件 %dx%d（160 时字放不进鱼身）"
          % (btn._d, btn.width(), btn.height()))
    assert launchforge.TaijiLaunchButton.DIAMETER >= 176, '圆盘需要比 160 更大'
    assert btn.width() == btn._d + 2 * btn._margin

    # ---------- 2. 盘面字体 ----------
    installed = set(QFontDatabase().families())
    family = btn._pick_text_family()
    print("[2] 盘面字体 = %s（候选 %s）" % (family, '、'.join(btn.TAIJI_FONTS)))
    if any(f in installed for f in btn.TAIJI_FONTS):
        assert family in btn.TAIJI_FONTS, '本机有圆体时应优先用圆体'

    # 不跟随「设置 → 字体搭配」：切到衬线，盘面仍是圆体
    launchforge.FontPrefs.set('serif', 13)
    serif_disc = launchforge.TaijiLaunchButton()
    print("[3] 界面切到「书卷衬线」后盘面字体 = %s（不被带跑）" % serif_disc._text_family)
    assert serif_disc._text_family == family
    launchforge.FontPrefs.set('classic', 13)

    # ---------- 3. 文字位置：三档字号都要在鱼身内 ----------
    for size in (launchforge.FONT_SIZE_MIN, launchforge.FONT_SIZE_BASE,
                 launchforge.FONT_SIZE_MAX):
        launchforge.FontPrefs.set('classic', size)
        disc = launchforge.TaijiLaunchButton()
        font, sides = disc._text_layout()
        _big, left_path, right_path, eyes, eye_r, radius, cx, cy = disc._geometry()
        assert len(sides) == 2, '两侧都要排字'

        for side, items in sides:
            path = left_path if side == 'run' else right_path
            assert len(items) == 2
            xs = []
            for ch, box in items:
                xs.append(box.center().x())
                # 5×5 采样点必须都在本侧鱼身内
                for gx in range(5):
                    for gy in range(5):
                        pt = QPointF(box.left() + box.width() * gx / 4.0,
                                     box.top() + box.height() * gy / 4.0)
                        assert path.contains(pt), '%s 的「%s」越到另一半（%dpx）' % (side, ch, size)
                # 角落离盘沿至少 4px
                for corner in (box.topLeft(), box.topRight(),
                               box.bottomLeft(), box.bottomRight()):
                    gap = radius - math.hypot(corner.x() - cx, corner.y() - cy)
                    assert gap >= 4.0, '%s 的「%s」贴到盘沿：%.1fpx' % (side, ch, gap)
                # 不许压鱼眼
                eye = eyes[0] if side == 'run' else eyes[1]
                dx = max(box.left() - (eye.x() + eye_r), eye.x() - eye_r - box.right(), 0.0)
                dy = max(box.top() - (eye.y() + eye_r), eye.y() - eye_r - box.bottom(), 0.0)
                assert math.hypot(dx, dy) >= 1.0, '%s 的「%s」压到鱼眼' % (side, ch)
            # 两字共线（同一竖列），不是各自乱飘
            assert abs(xs[0] - xs[1]) < 0.5, '两字应共用一条竖列'

        print("[4] %dpx：字号 %dpx · 字盒全在鱼身内（离盘沿 ≥4px、不压鱼眼）"
              % (size, font.pixelSize()))

    launchforge.FontPrefs.set('classic', 13)

    # ---------- 4. 配色：不是纯白 ----------
    run_base, run_hover = launchforge.TaijiLaunchButton.RUN_TEXT
    close_base, _ = launchforge.TaijiLaunchButton.CLOSE_TEXT
    print("[5] 字芯 %s / %s，描边 %s" %
          (run_base, close_base, launchforge.TaijiLaunchButton.TEXT_OUTLINE))
    for color in (run_base, close_base):
        c = QColor(color)
        assert not (c.red() > 245 and c.green() > 245 and c.blue() > 245), '文字不应是纯白'
        assert c.red() > c.blue(), '暖色字芯才配绿/红盘面'
    outline = launchforge.TaijiLaunchButton.TEXT_OUTLINE
    assert outline and QColor(outline[0]).lightness() < 90, '亮字需要深色描边'
    assert luminance(run_hover) > luminance(run_base), '悬停色应比常态更亮'

    # ---------- 5. 悬停高亮（像素级） ----------
    disc = launchforge.TaijiLaunchButton()
    disc.show()
    app.processEvents()
    font, sides = disc._text_layout()
    target = [box for side, items in sides if side == 'close' for _ch, box in items]
    region_left = int(min(b.left() for b in target)) - 6
    region_top = int(min(b.top() for b in target)) - 6
    region_right = int(max(b.right() for b in target)) + 6
    region_bottom = int(max(b.bottom() for b in target)) + 6

    def text_pixels():
        img = disc.grab().toImage()
        return {(x, y): img.pixelColor(x, y).rgb()
                for x in range(region_left, region_right)
                for y in range(region_top, region_bottom)}

    rest = text_pixels()
    disc._hover = 'close'
    disc._hover_t = 1.0
    disc.update()
    app.processEvents()
    hover = text_pixels()
    changed = sum(1 for key in rest if rest[key] != hover[key])
    print("[6] 悬停「关闭」时字区变化像素 = %d（区域 %dx%d）"
          % (changed, region_right - region_left, region_bottom - region_top))
    assert changed > 120, '悬停时文字本身应该高亮'

    # 只亮被悬停的那一半：左半区像素基本不变
    left_box = [box for side, items in sides if side == 'run' for _ch, box in items]
    lx0 = int(min(b.left() for b in left_box)) - 3
    ly0 = int(min(b.top() for b in left_box)) - 3
    lx1 = int(max(b.right() for b in left_box)) + 3
    ly1 = int(max(b.bottom() for b in left_box)) + 3
    img_rest = disc.grab().toImage()
    before = {(x, y): img_rest.pixelColor(x, y).rgb()
              for x in range(lx0, lx1) for y in range(ly0, ly1)}
    disc._hover = 'run'
    disc._hover_t = 0.0
    disc.update()
    app.processEvents()
    img_other = disc.grab().toImage()
    after = {(x, y): img_other.pixelColor(x, y).rgb()
             for x in range(lx0, lx1) for y in range(ly0, ly1)}
    same = sum(1 for key in before if before[key] == after[key])
    print("[7] 未悬停侧（启动）字区未变像素 = %d/%d" % (same, len(before)))
    assert same / len(before) > 0.9, '不该同时点亮另一侧的字'

    # ---------- 6. 禁用态转灰 ----------
    disc.set_run_enabled(False)
    idle_base, _idle_hover = disc._text_colors('run', False)
    print("[8] 禁用态文字色 = %s" % idle_base.name())
    assert idle_base.lightness() < 140 and abs(idle_base.red() - idle_base.blue()) < 12, \
        '禁用应是灰字'
    disc.close()

    # ---------- 7. 布局缓存 ----------
    cache_btn = launchforge.TaijiLaunchButton()
    first = cache_btn._text_layout()
    second = cache_btn._text_layout()
    assert first is second, '同参数应命中缓存（每帧重算会拖慢悬停动画）'
    launchforge.FontPrefs.set('classic', launchforge.FONT_SIZE_MAX)
    third = cache_btn._text_layout()
    assert third is not first, '字号变了必须重算'
    print("[9] 布局缓存命中；改字号后自动失效")
    launchforge.FontPrefs.set('classic', 13)
finally:
    shutil.rmtree(SANDBOX, ignore_errors=True)

print("\n需求 13 验收通过：圆盘放大、圆体字、字全在鱼身内，悬停时字会自己亮起来。")
