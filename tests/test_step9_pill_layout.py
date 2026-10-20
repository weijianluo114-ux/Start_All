"""
验收 T-010：圆两侧胶囊按钮的布局规则 + 宏功能已封存（源码保留、运行时不存在）。

对应需求 REQ-007（宏封存）与 REQ-008（圆侧胶囊操作区）。

检查项：
  1. 六枚胶囊都存在，且宽度随字数递增（短条 / 长条）
  2. 每列三枚：中间那枚中心与侧列中心重合，上下两枚各偏移 CENTER_GAP
  3. 左右两列与圆在同一水平线上居中（圆心 y == 侧列中心 y）
  4. 左列右边缘贴圆、右列左边缘贴圆（不重叠、不留大缝）
  5. 「设置」点了只弹"尚未实现"，不产生任何副作用
  6. 宏功能确实已封存：主程序没有 MacroRecorderDialog / global_macro，
     legacy 模块没有被 import

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
app.processEvents()

# ---------- 1. 六枚胶囊与宽度递减关系 ----------
pills = {
    '添加程序': win.btn_add,
    '添加文件夹': win.btn_add_folder,
    '输入路径': win.btn_add_path,
    '删除选中': win.btn_del,
    '日志': win.btn_log,
    '设置': win.btn_settings,
}
widths = {name: b.width() for name, b in pills.items()}
print("[1] 胶囊宽度：%s" % widths)
assert all(isinstance(b, launchforge.PillButton) for b in pills.values()), "应全部是 PillButton"
assert widths['日志'] <= widths['添加程序'] <= widths['添加文件夹'], "宽度应按字数递增"
assert widths['日志'] < widths['添加文件夹'], "2 字条必须比 5 字条短"

# ---------- 2/3. 每列三枚的位置 ----------
for name, column, align in (('左列', win.left_pills, 'right'),
                            ('右列', win.right_pills, 'left')):
    centers = [b.geometry().center().y() for b in column._buttons]
    col_center = column.height() / 2.0
    gap = launchforge.PillColumn.CENTER_GAP
    print("[2] %s 三枚中心 y=%s，侧列中心=%.0f，CENTER_GAP=%d"
          % (name, centers, col_center, gap))
    assert abs(centers[1] - col_center) <= 1, "中间那枚应与侧列中心同高"
    assert abs(centers[0] - (col_center - gap)) <= 1
    assert abs(centers[2] - (col_center + gap)) <= 1
    # 贴圆一侧对齐
    if align == 'right':
        assert all(b.geometry().x() + b.geometry().width() == column.width()
                   for b in column._buttons), "左列应右对齐"
    else:
        assert all(b.geometry().x() == 0 for b in column._buttons), "右列应左对齐"

# 圆心与两列中心同高（同一行、等高，应严格一致）
taiji_center = win.taiji.geometry().center().y()
col_centers = [win.left_pills.geometry().center().y(), win.right_pills.geometry().center().y()]
print("[3] 圆心 y=%d，两列中心 y=%s" % (taiji_center, col_centers))
assert abs(taiji_center - col_centers[0]) <= 1 and abs(taiji_center - col_centers[1]) <= 1

# ---------- 4. 两列与圆之间的水平关系 ----------
left_right_edge = win.left_pills.geometry().right()
right_left_edge = win.right_pills.geometry().left()
taiji_left = win.taiji.geometry().left()
taiji_right = win.taiji.geometry().right()
print("[4] 左列右缘=%d | 圆左=%d | 圆右=%d | 右列左缘=%d"
      % (left_right_edge, taiji_left, taiji_right, right_left_edge))
assert left_right_edge <= taiji_left, "左列不应压到圆"
assert right_left_edge >= taiji_right, "右列不应压到圆"
assert taiji_left - left_right_edge <= 24, "左列与圆之间不应留过大空隙"
assert right_left_edge - taiji_right <= 24, "右列与圆之间不应留过大空隙"

# ---------- 5. 设置按钮只是占位 ----------
FakeMessageBox.calls.clear()
config_before = open(launchforge.CONFIG_FILE, 'rb').read() if os.path.exists(launchforge.CONFIG_FILE) else b''
win.btn_settings.click()
app.processEvents()
titles = [c[1] for c in FakeMessageBox.calls]
print("[5] 点「设置」→ 弹窗 %s" % titles)
assert '设置' in titles, "应弹出设置提示"
assert '尚未实现' in FakeMessageBox.calls[0][2], "应说明尚未实现"
config_after = open(launchforge.CONFIG_FILE, 'rb').read() if os.path.exists(launchforge.CONFIG_FILE) else b''
assert config_before == config_after, "占位按钮不应改动配置"

# ---------- 6. 宏确实被封存 ----------
print("[6] 模块里 MacroRecorderDialog =", hasattr(launchforge, 'MacroRecorderDialog'),
      '| 窗口里 global_macro =', hasattr(win, 'global_macro'),
      '| legacy 已加载 =', 'macro_feature' in sys.modules)
assert not hasattr(launchforge, 'MacroRecorderDialog'), "主程序不应再定义宏录制框"
assert not hasattr(win, 'global_macro'), "主程序不应再持有 global_macro 字段"
assert 'macro_feature' not in sys.modules, "主程序不应 import legacy 宏模块"
assert not hasattr(win, 'btn_record_global'), "不应再有录制宏按钮"

legacy = os.path.join(SRC, 'legacy', 'macro_feature.py')
assert os.path.exists(legacy), "封存的源码文件必须保留"
print("    legacy 源码存在：%s（%d 字节）" % (legacy, os.path.getsize(legacy)))

win.close()
try:
    shutil.rmtree(SANDBOX, ignore_errors=True)
except Exception:
    pass

print("\n需求 7/8 验收通过：胶囊按字数定长、中间对齐圆心、宏功能已封存。")
