# -*- coding: utf-8 -*-
"""
T-015 多语言（v1.14.0）验收。

覆盖四件事：
  1. 译文表本身：四种语言键集合一致、占位符一致、无漏翻；
  2. 主窗口：四语言 × 两端字号（11px / 17px）下文案、胶囊宽度、越界情况；
  3. 圆盘：中文竖排两字、英文横排整词，字盒全部落在鱼身内且离盘沿 ≥5px；
  4. 设置面板：语言切换就地重建（不关窗）、两个下拉框左对齐、文字不被裁；
  5. 持久化：save_config 写入 language，新窗口按它启动；坏值收敛到默认语言。

运行：python tests/test_step15_i18n.py（必须 QT_QPA_PLATFORM=windows，offscreen 在本机没有字体库）
"""
import os
import sys
import json
import math
import tempfile

os.environ['QT_QPA_PLATFORM'] = 'windows'
os.environ['LOCALAPPDATA'] = tempfile.mkdtemp(prefix='lf_i18n_')

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, 'src'))

from PyQt5.QtWidgets import QApplication, QWidget, QLabel
from PyQt5.QtCore import QPointF, Qt
from PyQt5.QtGui import QFont

import launchforge
from lf_i18n import Lang, t, STRINGS, LANGUAGES, LANGUAGE_CODES, DEFAULT_LANGUAGE, \
    missing_keys, language_name

app = QApplication(sys.argv)
launchforge.heal_autostart_path = lambda: None
CONFIG = os.path.join(tempfile.mkdtemp(), 'presets.json')
launchforge.CONFIG_FILE = CONFIG

CJK = set('简体中文 english'.replace(' ', ''))          # 仅用于提示，不做判定
CNG = ('\u4e00', '\u9fff')


def has_han(text):
    return any(CNG[0] <= ch <= CNG[1] for ch in text)


def rect_of(widget, ancestor):
    pos = widget.mapTo(ancestor, widget.rect().topLeft())
    return pos.x(), pos.y(), widget.width(), widget.height()


# ---------------------------------------------------------------- 1. 译文表
print('[1] 译文表完整性')
assert len(LANGUAGES) == 4, '应支持四种语言'
assert LANGUAGE_CODES == ('zh-Hans', 'en', 'ja', 'zh-Hant')
for code in LANGUAGE_CODES:
    missing = missing_keys(code)
    assert not missing, '%s 缺 %d 条译文：%s' % (code, len(missing), missing[:5])
print('    4 种语言 × %d 条文案，无缺译' % len(STRINGS))

# 占位符必须一致，否则换个语言就 KeyError（t() 会吞掉，但文案会带着 {} 出来）
for key, entry in STRINGS.items():
    base = entry[DEFAULT_LANGUAGE]
    import re
    fields = sorted(re.findall(r'\{(\w+)\}', base))
    for code in LANGUAGE_CODES:
        text = entry[code]
        got = sorted(re.findall(r'\{(\w+)\}', text))
        assert got == fields, '%s/%s 占位符不一致：%s vs %s' % (key, code, got, fields)
        assert '{}' not in text or key == 'settings.size_tip' or key == 'settings.command_tip', \
            '%s/%s 用了位置占位符' % (key, code)
print('    占位符跨语言一致')

# 英文界面里不该混进汉字（日文允许汉字，繁体是中文）
for key, entry in STRINGS.items():
    assert not has_han(entry['en']), '英文译文里混进汉字：%s → %s' % (key, entry['en'])
print('    英文译文无汉字残留')

# 缺语言时的回落：坏值收敛到默认语言
assert Lang.set('kl-Klingon') == DEFAULT_LANGUAGE, '非法语言码应收敛到默认'
Lang.set('en')
assert t('main.log') == 'Logs'
assert t('no.such.key') == 'no.such.key', '缺键应回落键名而不是抛错'
print('    非法语言码回落简体；缺键回落键名')

# ---------------------------------------------------------------- 2. 主窗口
print('[2] 主窗口：四语言 × 11/17px')


def build_window(code, size):
    """建窗口 → 再套字号：launchforge 的 load_config 会重置 FontPrefs，
    所以字号必须在窗口起来之后用 apply_font_prefs 走"设置面板改字号"那条真实路径。"""
    Lang.set(code)
    launchforge.CONFIG_FILE = os.path.join(tempfile.mkdtemp(), 'c.json')
    window = launchforge.LauncherWindow()
    window.resize(560, 700)
    launchforge.FontPrefs.set('classic', size)
    window.apply_font_prefs()
    window.move(-3000, 100)
    window.show()
    app.processEvents()
    return window


pill_pairs = [('btn_add_folder', 'main.add_folder'), ('btn_add', 'main.add_program'),
              ('btn_add_path', 'main.add_path'), ('btn_del', 'main.remove_selected'),
              ('btn_log', 'main.log'), ('btn_settings', 'main.settings')]

for code in LANGUAGE_CODES:
    for size in (11, 17):
        window = build_window(code, size)
        central = window.centralWidget()
        assert window.windowTitle() == t('app.title'), '%s 标题未翻译' % code

        # 胶囊文案与当前语言一致；文字不被裁、不超出胶囊
        for attr, key in pill_pairs:
            btn = getattr(window, attr)
            assert btn.text() == t(key), '%s/%dpx: %s 文案是 %r' % (code, size, attr, btn.text())
            need = btn.fontMetrics().horizontalAdvance(btn.text()) + 2 * btn._padding
            assert btn.width() >= need, '%s/%dpx: 胶囊 %r 文字被裁（%d < %d）' % (
                code, size, btn.text(), btn.width(), need)
            assert btn.height() >= btn.fontMetrics().height() + 4, '%s/%dpx: 胶囊高度压到文字' % (
                code, size)

        # 三列（左胶囊 / 圆盘 / 右胶囊）互不重叠，且都在客户区内
        left = window.left_pills
        right = window.right_pills
        taiji = window.taiji
        lx, ly, lw, lh = rect_of(left, central)
        rx, ry, rw, rh = rect_of(right, central)
        tx, ty, tw, th = rect_of(taiji, central)
        assert lx + lw <= tx + 1, '%s/%dpx: 左胶囊压到圆盘' % (code, size)
        assert tx + tw <= rx + 1, '%s/%dpx: 圆盘压到右胶囊' % (code, size)
        assert rx + rw <= central.width() + 1, '%s/%dpx: 右胶囊越出窗口' % (code, size)
        assert lx >= 0, '%s/%dpx: 左胶囊越出窗口' % (code, size)
        assert ly >= 0 and ry + rh <= central.height() + 1, '%s/%dpx: 胶囊纵向越界' % (code, size)

        # 中排胶囊与圆心齐平（语言换了，这条规则不能破）
        mid_left = window.btn_add
        my = mid_left.mapTo(central, mid_left.rect().center()).y()
        assert abs(my - (ty + th / 2.0)) <= 2, '%s/%dpx: 中间胶囊未与圆心对齐（%s vs %s）' % (
            code, size, my, ty + th / 2.0)

        # 预设行文案
        assert window.preset_label.text() == t('main.preset')
        assert window.btn_new_preset.text() == t('main.new')
        assert window.btn_del_preset.text() == t('main.delete')

        # 无 Han 字符的语种：主界面可见文案里不能残留中文
        if code == 'en':
            seen = [window.preset_label.text()] + [getattr(window, a).text() for a, _ in pill_pairs]
            for text in seen:
                assert not has_han(text), '英文界面残留中文：%r' % text

        print('    %-8s %2dpx | 胶囊宽 %3d | 窗口 %dx%d | 上中下 %s' % (
            code, size, left.width(), window.width(), window.height(),
            [btn.height() for btn in left._buttons]))
        window.close()
        app.processEvents()

# ---------------------------------------------------------------- 3. 圆盘文字
print('[3] 圆盘盘面文字：竖排/横排自动切换')


def taiji_report(window):
    button = window.taiji
    font, sides = button._text_layout()
    _big, left_path, right_path, _eyes, eye_r, radius, cx, cy = button._geometry()
    rows = []
    for side, items in sides:
        path = left_path if side == 'run' else right_path
        for text, box in items:
            outside = 0
            for gx in range(5):
                for gy in range(5):
                    pt = QPointF(box.left() + box.width() * gx / 4.0,
                                 box.top() + box.height() * gy / 4.0)
                    if not path.contains(pt):
                        outside += 1
            margin = min(radius - math.hypot(x - cx, y - cy) for x, y in
                         ((box.left(), box.top()), (box.right(), box.top()),
                          (box.left(), box.bottom()), (box.right(), box.bottom())))
            rows.append((side, text, outside, margin, box))
    return font, rows


for code in LANGUAGE_CODES:
    for size in (11, 17):
        window = build_window(code, size)
        font, rows = taiji_report(window)
        expected = 2 if code == 'en' else 4     # 英文整词一项；中日文逐字一项
        assert len(rows) == expected, '%s/%dpx: 文字项数应为 %d（得到 %d）' % (
            code, size, expected, len(rows))
        for side in ('run', 'close'):
            joined = ''.join(r[1] for r in rows if r[0] == side)
            want = t('main.taiji_run') if side == 'run' else t('main.taiji_close')
            assert joined == want, '%s/%dpx: %s 侧文字是 %r，应为 %r' % (
                code, size, side, joined, want)
        for side, text, outside, margin, box in rows:
            assert outside == 0, '%s/%dpx: %r 有 %d 个采样点越出鱼身' % (code, size, text, outside)
            assert margin >= 5.0, '%s/%dpx: %r 离盘沿只剩 %.1fpx' % (code, size, text, margin)
        # 中文/日文竖排（逐字），英文横排（整词）
        if code == 'en':
            for side, text, _, _, box in rows:
                assert len(text) > 1 and text.isupper(), '英文应为横排整词'
        else:
            for side, text, _, _, box in rows:
                assert len(text) == 1, '%s 应为逐字竖排' % code
        # 两个词不能跨过中线贴在一起（按两侧各自的外接矩形判）
        run_boxes = [r[4] for r in rows if r[0] == 'run']
        close_boxes = [r[4] for r in rows if r[0] == 'close']
        run_right = max(b.right() for b in run_boxes)
        close_left = min(b.left() for b in close_boxes)
        assert run_right < close_left, '%s/%dpx: 两侧文字重叠（%.1f >= %.1f）' % (
            code, size, run_right, close_left)
        print('    %-8s %2dpx | 字径 %2d | %s / %s | 最小盘沿余量 %.1f' % (
            code, size, font.pixelSize(), rows[0][1], rows[1][1],
            min(r[3] for r in rows)))
        window.close()
        app.processEvents()

# ---------------------------------------------------------------- 4. 设置面板
print('[4] 设置面板：语言行、就地重译、不越界')
Lang.set('zh-Hans')
window = build_window('zh-Hans', 13)
dialog = launchforge.SettingsDialog(
    window, key_path=r'Software\MultiLauncherSelfTest\Run', value_name='SelfTest',
    on_font_changed=window.on_font_changed, on_language_changed=window.on_language_changed)
dialog.move(-3000, 100)
dialog.show()
app.processEvents()

assert dialog.lang_combo.count() == 4, '语言下拉应有四项'
assert [dialog.lang_combo.itemData(i) for i in range(4)] == list(LANGUAGE_CODES)
native = [language_name(c) for c in LANGUAGE_CODES]
assert [dialog.lang_combo.itemText(i) for i in range(4)] == native, '语言名应保持原生写法'
print('    语言下拉：%s' % ' / '.join(native))

# 两个下拉框左边缘对齐（网格布局的意义）
assert dialog.lang_combo.x() == dialog.family_combo.x(), '语言/字体下拉未左对齐'

# 卡片内没有子控件越界（弹出列表是独立窗口，按 window() 排除）
card = dialog.font_card
for child in card.findChildren(QWidget):
    if child.window() is not dialog or child.width() == 0 or child.height() == 0:
        continue
    x, y, w, h = rect_of(child, card)
    assert x >= -1 and y >= -1 and x + w <= card.width() + 1 and y + h <= card.height() + 1, \
        '%s 越出字体卡片：%s' % (type(child).__name__, (x, y, w, h))

# 下拉框文字不能被裁（右侧还要留 22px 给箭头）
for combo, label in ((dialog.lang_combo, '语言'), (dialog.family_combo, '字体')):
    need = combo.fontMetrics().horizontalAdvance(combo.currentText())
    assert need <= combo.width() - 34, '%s 下拉文字过长（%d > %d）' % (
        label, need, combo.width() - 34)

# 自启动说明不被裁：行高 >= 文字实际需要
need_h = dialog.row_autostart.desc_label.heightForWidth(dialog._row_text_width())
assert dialog.row_autostart.height() >= need_h + 2 * dialog.row_autostart.PAD_V, \
    '自启动说明被裁（行高 %d，需要 %d）' % (dialog.row_autostart.height(), need_h)
print('    面板 %dx%d，卡片 %dx%d，自启动行高 %d' % (
    dialog.width(), dialog.height(), card.width(), card.height(),
    dialog.row_autostart.height()))


def texts_snapshot(dlg):
    return (dlg.windowTitle(), dlg.title.text(), dlg.row_autostart.title_label.text(),
            dlg.lang_label.text(), dlg.family_label.text(), dlg.size_label.text(),
            dlg.preview.text(), dlg.btn_close.text(), dlg.family_combo.currentText())


seen = {texts_snapshot(dialog)}
for index in range(1, 4):
    code = LANGUAGE_CODES[index]
    dialog.lang_combo.setCurrentIndex(index)
    app.processEvents()
    assert Lang.CODE == code, '切换后 Lang 未更新'
    # 面板就地重建：仍是同一个对话框对象，标题与标签都换了
    assert dialog.windowTitle() == t('app.settings_title')
    assert dialog.lang_label.text() == t('settings.language')
    assert dialog.family_combo.currentText() == t('font.classic.name')
    # 主窗口也同步换了（回调生效）
    assert window.btn_add.text() == t('main.add_program'), '主窗口未跟随切换语言'
    assert window.windowTitle() == t('app.title')
    # 「默认方案」这个名字是我们起的，换语言要跟着换（用户自建的不动）
    assert window.current_preset_name == t('main.default_preset'), \
        '默认预设名未随语言变化：%r' % window.current_preset_name
    assert window.preset_combo.itemText(0) == t('main.default_preset')
    # 换完语言面板高度重算，说明文字不被裁
    need_h = dialog.row_autostart.desc_label.heightForWidth(dialog._row_text_width())
    assert dialog.row_autostart.height() >= need_h, '%s：说明文字被裁' % code
    for combo, label in ((dialog.lang_combo, '语言'), (dialog.family_combo, '字体')):
        need = combo.fontMetrics().horizontalAdvance(combo.currentText())
        assert need <= combo.width() - 34, '%s：%s 下拉文字过长' % (code, label)
    seen.add(texts_snapshot(dialog))
    print('    切到 %-8s → %r / %r' % (code, dialog.title.text(),
                                       dialog.family_combo.currentText()))
assert len(seen) == 4, '四次快照应各不相同'
dialog.close()
app.processEvents()

# ---------------------------------------------------------------- 5. 持久化
print('[5] 持久化')
Lang.set('ja')
window = build_window('ja', 13)
window.save_config()
with open(launchforge.CONFIG_FILE, 'r', encoding='utf-8') as f:
    data = json.load(f)
assert data['settings']['language'] == 'ja', '语言未写入配置：%s' % data['settings']
print('    写入 settings.language = %s' % data['settings']['language'])

# 新窗口（同一份配置）应以日语启动，且默认预设名也是日语
window.close()
window2 = launchforge.LauncherWindow()
app.processEvents()
assert Lang.CODE == 'ja', '重启后语言未恢复'
assert window2.btn_log.text() == t('main.log')
# 标题也要跟着配置走：setWindowTitle 在 load_config 之前调过一次，
# 若不在读配置后再设一次，英文/日文用户会看到中文标题
assert window2.windowTitle() == t('app.title'), '标题未按配置语言设置：%r' % window2.windowTitle()
print('    重开窗口仍是日语，预设名 %r' % window2.current_preset_name)
window2.close()

# 坏值：配置里写了不存在的语言码，应回落简体而不是崩
with open(launchforge.CONFIG_FILE, 'r', encoding='utf-8') as f:
    data = json.load(f)
data['settings']['language'] = 'xx-YY'
with open(launchforge.CONFIG_FILE, 'w', encoding='utf-8') as f:
    json.dump(data, f, ensure_ascii=False)
window3 = launchforge.LauncherWindow()
app.processEvents()
assert Lang.CODE == DEFAULT_LANGUAGE, '非法语言码未收敛'
print('    非法语言码 → %s' % Lang.CODE)
window3.close()

# 收尾：恢复默认语言，免得后续脚本继承
Lang.set(DEFAULT_LANGUAGE)
print('\n全部通过')
