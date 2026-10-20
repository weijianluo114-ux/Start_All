"""
验收 T-010：圆两侧胶囊按钮的布局规则 + 宏功能已封存（源码保留、运行时不存在）。

对应需求 REQ-007（宏封存）与 REQ-008/REQ-009（圆侧胶囊、对齐与圆角修正）。

检查项：
  1. 左右两列等宽；同一排左右等宽；上排 == 下排（垂直镜像）
  2. 左列三枚左边缘对齐、右列三枚右边缘对齐
  3. 每列三枚：中间那枚与侧列中心重合，上下两枚各偏移 CENTER_GAP
  4. 圆心 y == 两列中心 y
  5. 两列与圆之间有空隙但不脱节
  6. 圆角：外侧收小、内侧保持大圆角；边框无单独上色（无白色上沿）
  7. 「设置」点了只弹"尚未实现"，不产生任何副作用
  8. 宏功能确实已封存

运行：python tests/test_step9_pill_layout.py
"""

import os
import shutil
import sys
import tempfile

os.environ['QT_QPA_PLATFORM'] = 'offscreen'

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SRC = os.path.join(ROOT, 'src')

SANDBOX = tempfile.mkdtemp(prefix='lf_t9_')
os.environ['LOCALAPPDATA'] = SANDBOX

sys.path.insert(0, SRC)

from PyQt5.QtWidgets import QApplication, QMessageBox      # noqa: E402
from PyQt5.QtCore import Qt                                # noqa: E402

import launchforge                                          # noqa: E402


app = QApplication(sys.argv)


class FakeMessageBox:
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
        return QMessageBox.No


launchforge.QMessageBox = FakeMessageBox

win = launchforge.LauncherWindow()
win.resize(560, 700)
win.show()
for _ in range(3):
    app.processEvents()

# ---------- 1. 宽度对称 ----------
left_w = [b.width() for b in win.left_pills._buttons]
right_w = [b.width() for b in win.right_pills._buttons]
print("[1] 左列宽度=%s | 右列宽度=%s | 列宽=%d/%d"
      % (left_w, right_w, win.left_pills.width(), win.right_pills.width()))
assert win.left_pills.width() == win.right_pills.width(), "左右两列必须等宽"
assert left_w == right_w, "同一排左右两枚必须等长"
assert left_w[0] == left_w[2], "上排与下排必须等长（垂直镜像）"

# ---------- 2. 边缘对齐 ----------
for label, column in (('左列', win.left_pills), ('右列', win.right_pills)):
    geos = [b.geometry() for b in column._buttons]
    print("[2] %s 几何 x/w = %s" % (label, [(g.x(), g.width()) for g in geos]))
    if label == '左列':
        assert all(g.x() == 0 for g in geos), "左列三枚必须左边缘对齐"
    else:
        assert all(g.x() + g.width() == column.width() for g in geos), "右列三枚必须右边缘对齐"

# ---------- 3/4. 垂直位置与圆心 ----------
for label, column in (('左列', win.left_pills), ('右列', win.right_pills)):
    centers = [b.geometry().center().y() for b in column._buttons]
    col_center = column.height() / 2.0
    gap = launchforge.PillColumn.CENTER_GAP
    print("[3] %s 三枚中心 y=%s，侧列中心=%.0f" % (label, centers, col_center))
    assert abs(centers[1] - col_center) <= 1, "中间那枚应与侧列中心同高"
    assert abs(centers[0] - (col_center - gap)) <= 1
    assert abs(centers[2] - (col_center + gap)) <= 1

taiji_center = win.taiji.geometry().center().y()
print("[4] 圆心 y=%d | 左列中心 y=%d | 右列中心 y=%d"
      % (taiji_center, win.left_pills.geometry().center().y(),
         win.right_pills.geometry().center().y()))
assert abs(taiji_center - win.left_pills.geometry().center().y()) <= 1
assert abs(taiji_center - win.right_pills.geometry().center().y()) <= 1

# ---------- 5. 两列与圆 ----------
left_edge = win.left_pills.geometry().right()
right_edge = win.right_pills.geometry().left()
print("[5] 左列右缘=%d | 圆 %d..%d | 右列左缘=%d"
      % (left_edge, win.taiji.geometry().left(), win.taiji.geometry().right(), right_edge))
assert left_edge < win.taiji.geometry().left(), "左列不应压到圆"
assert right_edge > win.taiji.geometry().right(), "右列不应压到圆"

# ---------- 6. 圆角与边框 ----------
for label, column, small_side in (('左列', win.left_pills, 'left'),
                                  ('右列', win.right_pills, 'right')):
    for b in column._buttons:
        qss = b.styleSheet()
        big = b.height() // 2
        small = launchforge.PillButton.SMALL_RADIUS
        if small_side == 'left':
            assert 'border-top-left-radius: %dpx' % small in qss, "左列左侧应为小圆角"
            assert 'border-top-right-radius: %dpx' % big in qss, "左列右侧应保持大圆角"
        else:
            assert 'border-top-left-radius: %dpx' % big in qss, "右列左侧应保持大圆角"
            assert 'border-top-right-radius: %dpx' % small in qss, "右列右侧应为小圆角"
        assert 'border-top-color' not in qss, "不应再给上沿单独上色（会出现白色描边）"
        assert 'border-bottom-color' not in qss, "四周边框颜色应统一"
print("[6] 圆角：左列 左小(r=%d)/右大(r=%d)，右列反之；边框无单独上色 ✅"
      % (launchforge.PillButton.SMALL_RADIUS, launchforge.PillButton.HEIGHT // 2))

# ---------- 7. 设置按钮只是占位 ----------
FakeMessageBox.calls.clear()
cfg = launchforge.CONFIG_FILE
before = open(cfg, 'rb').read() if os.path.exists(cfg) else b''
win.btn_settings.click()
app.processEvents()
titles = [c[1] for c in FakeMessageBox.calls]
print("[7] 点「设置」→ 弹窗 %s" % titles)
assert '设置' in titles, "应弹出设置提示"
assert '尚未实现' in FakeMessageBox.calls[0][2], "应说明尚未实现"
after = open(cfg, 'rb').read() if os.path.exists(cfg) else b''
assert before == after, "占位按钮不应改动配置"

# ---------- 8. 宏确实被封存 ----------
print("[8] MacroRecorderDialog=%s | global_macro=%s | legacy 已加载=%s"
      % (hasattr(launchforge, 'MacroRecorderDialog'), hasattr(win, 'global_macro'),
         'macro_feature' in sys.modules))
assert not hasattr(launchforge, 'MacroRecorderDialog')
assert not hasattr(win, 'global_macro')
assert 'macro_feature' not in sys.modules
assert not hasattr(win, 'btn_record_global')

legacy = os.path.join(SRC, 'legacy', 'macro_feature.py')
assert os.path.exists(legacy), "封存的源码文件必须保留"
print("    legacy 源码存在：%s（%d 字节）" % (legacy, os.path.getsize(legacy)))

win.close()
try:
    shutil.rmtree(SANDBOX, ignore_errors=True)
except Exception:
    pass

print("\n需求 7/8/9 验收通过：胶囊成对等宽、边缘对齐、内外圆角呼应、宏已封存。")
