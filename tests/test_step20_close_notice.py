# -*- coding: utf-8 -*-
"""
Step 20 验收：关闭结果提示「5 秒自动关闭」（REQ-017 / v1.16.0）

覆盖：
  1. 全成功的提示**没有任何按钮**（不是原来那个要点的 information），非模态、不挡主界面
  2. 倒计时到点自己关闭（测试用 1 秒档，不必真等 5 秒）
  3. 失败时**保留** `QMessageBox.information`（要人点确认）
  4. 倒计时文案四种语言都有、且带秒数、没有静默回落成中文
  5. `close_all_programs` 结尾把失败项数传给了 `_show_close_result`

真实进程跑一趟见 `test_step20_close_notice_e2e.py`。
为什么不用 `QMessageBox` + `NoButton`：Qt 在 `exec_()` 阶段仍会补一个 OK 按钮
（e2e 实测结果框上照样冒出 OK），达不到"不用点"。

运行：python tests/test_step20_close_notice.py
"""

import os
import sys
import time
from unittest import mock

os.environ['QT_QPA_PLATFORM'] = 'offscreen'

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, 'src'))

from PyQt5.QtWidgets import QApplication, QMessageBox, QPushButton, QDialog

app = QApplication(sys.argv)
import tempfile
os.environ['LOCALAPPDATA'] = tempfile.mkdtemp(prefix='lf_t20_')

import launchforge
from launchforge import AutoCloseNotice
from lf_i18n import LANGUAGES, t, Lang

launchforge.heal_autostart_path = lambda: None
launchforge.CONFIG_FILE = os.path.join(os.environ['LOCALAPPDATA'], 'c.json')

win = launchforge.LauncherWindow()

# ---------- 1. 成功路径：无按钮 + 非模态 + 到点自己关 ----------
notice = win._make_close_notice('已关闭 3 个程序。', seconds=1)
assert isinstance(notice, AutoCloseNotice)
assert notice.findChildren(QPushButton) == [], '提示里出现了按钮，用户还得点'
assert not notice.isModal(), '提示不该是模态的（会挡住主界面）'
assert notice.windowFlags() & launchforge.Qt.Tool, '提示应设为 Tool（不占任务栏）'
print('[1] 成功提示：无按钮 / 非模态 / Tool 窗口')

# 主界面在提示期间仍然可用（非模态的直接证据）
notice.popup()
win.show()
for _ in range(5):
    app.processEvents()
    time.sleep(0.02)
assert win.isEnabled(), '提示弹出后主界面被禁用了（说明还是模态）'
assert notice.isVisible(), '提示没有显示出来'
print('    弹出后主界面仍可用（isEnabled=True），提示可见')

# ---------- 1b. 四周留白 + 渐变外框（用户 2026-10-30 的诉求） ----------
img = notice.grab().toImage()
W, H = img.width(), img.height()
assert notice.GAP >= 12, '四周空隙只有 %dpx，卡片会顶到窗口边缘' % notice.GAP


def a_of(x, y):
    return img.pixelColor(x, y).alpha()


core = [a_of(W // 2, d) for d in range(0, notice.GAP - 4)]
sides = [a_of(d, H // 2) for d in range(0, notice.GAP - 4)]
sides += [a_of(W - 1 - d, H // 2) for d in range(0, notice.GAP - 4)]
sides += [a_of(W // 2, H - 1 - d) for d in range(0, notice.GAP - 4)]
assert max(core + sides) == 0, \
    '距边 %dpx 内还有不透明像素（最外圈 %d），没有留出空隙' % (notice.GAP - 4, max(core + sides))
print('    四周 %dpx 透明空隙：外圈 alpha 全 0' % (notice.GAP - 4))

# 外框：画在「卡片外 3px」，即距窗口边 GAP + RING - 3 的那一圈
RING = launchforge.NoticeCard.RING
ring_edge = int(notice.GAP + RING)          # 卡片本体边缘
warm = []
for x in range(ring_edge, W - ring_edge):
    for y in range(ring_edge - 4, ring_edge - 1):
        c = img.pixelColor(x, y)
        if c.alpha() > 20 and c.red() - c.blue() > 18:
            warm.append((c.red(), c.green(), c.blue()))
assert len(warm) >= 40, '卡片外侧没找到暖色外框（只 %d 个像素）' % len(warm)

# 渐变：外框是「上亮下淡」的竖向渐变，要在同一侧比较上下两端，
# 取左右中点会比不出差异（同一 y 上的两点颜色本来就一样）。
ring_col = ring_edge - 3
ring_px = [(y, img.pixelColor(ring_col, y)) for y in range(H)]
ring_px = [(y, c) for y, c in ring_px if c.alpha() > 25]
assert len(ring_px) >= 20, '左侧外框像素太少（%d），外框没画出来' % len(ring_px)
top_c, bottom_c = ring_px[0][1], ring_px[-1][1]
spread = max(abs(top_c.red() - bottom_c.red()),
             abs(top_c.green() - bottom_c.green()),
             abs(top_c.blue() - bottom_c.blue()))
print('    外框暖色像素 %d 个，上下两端色差 %d（>0 表示是渐变而非单色）'
      % (len(warm), spread))
assert spread >= 6, '外框上下色差只有 %d，看起来是单色描边而不是渐变' % spread

# 四角在留白区内必须透明（圆角没被窗口边界切掉）
corner_a = [a_of(notice.GAP, notice.GAP), a_of(W - 1 - notice.GAP, notice.GAP),
            a_of(notice.GAP, H - 1 - notice.GAP), a_of(W - 1 - notice.GAP, H - 1 - notice.GAP)]
assert max(corner_a) < 200, '四角不透明（%s），圆角被窗口边界裁掉了' % corner_a
print('    四角透明（圆角完整）')

t0 = time.time()
while notice.isVisible() and time.time() - t0 < 4.0:
    app.processEvents()
    time.sleep(0.05)
elapsed = time.time() - t0
print('    1 秒档：%.2fs 后自己关闭（未点任何按钮）' % elapsed)
assert not notice.isVisible(), '4 秒都没自己关掉，自动关闭没生效'
assert elapsed < 2.0, '耗时 %.2fs，不像 1 秒档' % elapsed

# ---------- 2. 失败路径：保留按钮，等用户确认 ----------
calls = []


def fake_information(parent, title, text, *a, **kw):
    calls.append((title, text))
    return QMessageBox.Ok


with mock.patch.object(QMessageBox, 'information', staticmethod(fake_information)):
    win._show_close_result('关闭失败 1 项：\n· X — 进程仍在运行', has_failure=True)
assert len(calls) == 1, '失败时应弹一次确认框，实际 %d 次' % len(calls)
assert '失败' in calls[0][1], '失败内容没进提示'
print('[2] 失败提示：走 QMessageBox.information（%d 次），标题=%r' % (len(calls), calls[0][0]))

calls2 = []
with mock.patch.object(QMessageBox, 'information',
                       staticmethod(lambda *a, **kw: calls2.append(a))):
    n2 = win._make_close_notice('已关闭 2 个程序。', seconds=1)
assert not calls2, '成功路径不该弹确认框'
assert n2.findChildren(QPushButton) == [], '成功路径不该有按钮'
print('    成功路径不弹确认框、且无按钮')

# ---------- 3. 倒计时文案四语言齐全 ----------
print('[3] 倒计时文案：')
texts = {}
for lang in LANGUAGES:
    code = lang['code']                 # LANGUAGES 是字典列表，别直接拿它当语言码
    Lang.set(code)
    s = t('close.auto_close_hint', sec=3)
    assert s and '3' in s, '%s 的倒计时文案异常：%r' % (code, s)
    texts[code] = s
    print('    %-8s %s' % (code, s))
Lang.set('zh-Hans')
for code in ('en', 'ja', 'zh-Hant'):
    assert texts[code] != texts['zh-Hans'], '%s 的倒计时文案没翻译（回落到中文）' % code
print('    四种语言各不相同（没有静默回落）')

# ---------- 4. 接线 ----------
src = open(os.path.join(ROOT, 'src', 'launchforge.py'), encoding='utf-8').read()
assert '_show_close_result(msg, has_failure=bool(all_failed))' in src, \
    'close_all_programs 结尾没有把失败项数传给 _show_close_result'
assert 'CLOSE_NOTICE_SECONDS = 5' in src, '缺少 5 秒常量'
print('[4] 接线：失败项数已传入，停留时长 5 秒')

win.close()
print('\nSTEP 20 全部通过：成功提示无按钮、非模态、5 秒自关；失败提示保留按钮。')
