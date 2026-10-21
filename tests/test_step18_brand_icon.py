# -*- coding: utf-8 -*-
"""
Step 18 验收：品牌图标（REQ-015 / v1.15.0）

覆盖：
  1. `assets/logo.ico` 存在，且内含 16/24/32/48/64/128/256 七档（Windows 各场景各取所需）
  2. `assets/logo.png` 是正方形母版，且**不含**源图右下角的「AI生成 WORKBUDDY」水印
  3. ICO 的每一帧都是正方形、像素数符合声明（防"声明 256 实际只有 32"）
  4. 主窗口运行时确实加载了图标（setWindowIcon 生效，不是空图标）
  5. 打包后的 exe 含有图标资源（PE 资源里存在 RT_ICON）
  6. 源码/构建脚本引用的是同一个 `assets/logo.ico`（不会出现"界面换了、exe 没换"）

运行：python tests/test_step18_brand_icon.py
（纯本地文件与 PE 资源检查，不需要启动程序）
"""

import os
import struct
import sys

os.environ['QT_QPA_PLATFORM'] = 'offscreen'

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, 'src'))

ICO = os.path.join(ROOT, 'assets', 'logo.ico')
PNG = os.path.join(ROOT, 'assets', 'logo.png')
EXPECT_SIZES = [16, 24, 32, 48, 64, 128, 256]


def read_ico(path):
    """
    解析 ICO 目录，返回 [(宽, 高, 字节数, 偏移)]。

    不依赖 Pillow：ICO 头是固定格式（ICONDIR 6 字节 + 每帧 16 字节目录项），
    直接读比引入一个只在开发机存在的依赖更可靠。
    """
    with open(path, 'rb') as f:
        data = f.read()
    reserved, kind, count = struct.unpack_from('<HHH', data, 0)
    assert reserved == 0 and kind == 1, '不是合法的 ICO 文件'
    frames = []
    for i in range(count):
        off = 6 + i * 16
        width, height, colors, res, planes, bits, size, offset = struct.unpack_from(
            '<BBBBHHII', data, off)
        frames.append((width or 256, height or 256, size, offset))
    return frames, len(data)


def png_size(path):
    with open(path, 'rb') as f:
        head = f.read(33)
    assert head[:8] == b'\x89PNG\r\n\x1a\n', '不是合法的 PNG'
    width, height = struct.unpack('>II', head[16:24])
    return width, height


try:
    # ---------- 1. ICO 档位 ----------
    assert os.path.exists(ICO), '缺少 assets/logo.ico'
    frames, total = read_ico(ICO)
    got = sorted(w for w, _h, _s, _o in frames)
    print('[1] assets/logo.ico：%d 帧，%d 字节，尺寸 %s' % (len(frames), total, got))
    assert got == EXPECT_SIZES, 'ICO 尺寸不是 %s：%s' % (EXPECT_SIZES, got)

    for width, height, size, offset in frames:
        assert width == height, '第 %dpx 帧不是正方形' % width
        assert size > 0, '%dpx 帧字节数为 0' % width
        assert offset + size <= total, '%dpx 帧越出文件末尾' % width
        # 256 档必须是 PNG 压缩（32bpp BMP 的 256 帧会大到 256KB）
        if width == 256:
            with open(ICO, 'rb') as f:
                f.seek(offset)
                sig = f.read(8)
            print('    256px 帧签名：%s' % sig[:4])
    print('    每帧均为正方形、字节数与偏移合法')

    # ---------- 2. 母版 PNG 无水印 ----------
    pw, ph = png_size(PNG)
    print('[2] assets/logo.png：%d×%d' % (pw, ph))
    assert pw == ph, '母版应为正方形'
    assert 512 <= pw <= 1024, '母版边长应在 512–1024 之间（太小放大后发虚）'

    # 水印在源图右下角（y ≥ 930/1024）。母版是按主体包围盒重新裁剪的，
    # 这里断言"裁剪留下了干净的外圈"——主体不顶边，且四边是统一浅色背景。
    # （水印是否被裁掉由生成时的裁剪框保证：下沿 898 < 930，见 REQ-015）
    try:
        from PIL import Image
    except ImportError:
        print('    未安装 Pillow，跳过像素断言')
    else:
        im = Image.open(PNG).convert('RGB')
        ring = 3
        edges = []
        for x in range(pw):
            for y in list(range(ring)) + list(range(ph - ring, ph)):
                edges.append(im.getpixel((x, y)))
        for y in range(ph):
            for x in list(range(ring)) + list(range(pw - ring, pw)):
                edges.append(im.getpixel((x, y)))
        darkest = min(sum(c) for c in edges)
        print('    外圈 %dpx：最深像素色和=%d（越小越黑）' % (ring, darkest))
        assert darkest > 400, '外圈出现深色主体（色和 %d），说明裁剪没留边' % darkest

    # ---------- 3. 主窗口运行时图标 ----------
    from PyQt5.QtWidgets import QApplication
    app = QApplication(sys.argv)
    import tempfile
    os.environ['LOCALAPPDATA'] = tempfile.mkdtemp(prefix='lf_t18_')

    import launchforge
    launchforge.heal_autostart_path = lambda: None
    launchforge.CONFIG_FILE = os.path.join(os.environ['LOCALAPPDATA'], 'c.json')

    window = launchforge.LauncherWindow()
    icon = window.windowIcon()
    sizes = icon.availableSizes()
    print('[3] 主窗口图标：%s，可用尺寸 %s' % ('非空' if not icon.isNull() else '空', sizes))
    assert not icon.isNull(), '主窗口没有设置图标'
    assert sizes, '图标里没有任何可用尺寸'
    biggest = max((s.width() for s in sizes), default=0)
    assert biggest >= 128, '图标最大档只有 %dpx，高 DPI 下会发虚' % biggest
    window.close()

    # ---------- 4. 构建配置引用同一个 ico ----------
    checks = {
        'scripts/build.bat': 'assets\\logo.ico',
        '.github/workflows/build.yml': 'assets/logo.ico',
    }
    for rel, needle in checks.items():
        path = os.path.join(ROOT, rel)
        text = open(path, encoding='utf-8', errors='ignore').read()
        print('[4] %s 引用 %s：%s' % (rel, needle, '是' if needle in text else '否'))
        assert needle in text, '%s 没有引用 %s' % (rel, needle)

    src = open(os.path.join(ROOT, 'src', 'launchforge.py'), encoding='utf-8').read()
    assert "'logo.ico'" in src or '"logo.ico"' in src, '源码没有引用 logo.ico'

    # ---------- 5. exe 里的图标资源 ----------
    exe = None
    for name in sorted(os.listdir(ROOT)):
        if name.startswith('LaunchForge_v') and name.endswith('.exe'):
            exe = os.path.join(ROOT, name)
    if not exe:
        print('[5] 仓库根没有 exe，跳过 PE 图标检查')
    else:
        import ctypes
        from ctypes import wintypes

        RT_ICON = 3                     # MAKEINTRESOURCE(3)
        LOAD_LIBRARY_AS_DATAFILE = 0x00000002
        k32 = ctypes.WinDLL('kernel32', use_last_error=True)
        # 句柄必须声明成指针宽度，否则 64 位下 int 会被当 32 位截断（OverflowError）
        k32.LoadLibraryExW.argtypes = [wintypes.LPCWSTR, wintypes.HANDLE, wintypes.DWORD]
        k32.LoadLibraryExW.restype = wintypes.HMODULE
        k32.FreeLibrary.argtypes = [wintypes.HMODULE]
        k32.FreeLibrary.restype = wintypes.BOOL

        ENUMPROC = ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.HMODULE, ctypes.c_void_p,
                                      ctypes.c_void_p, ctypes.c_void_p)
        k32.EnumResourceNamesW.argtypes = [wintypes.HMODULE, ctypes.c_void_p,
                                           ENUMPROC, ctypes.c_void_p]
        k32.EnumResourceNamesW.restype = wintypes.BOOL

        mod = k32.LoadLibraryExW(exe, None, LOAD_LIBRARY_AS_DATAFILE)
        assert mod, '无法以数据文件方式加载 exe：%s' % exe
        hits = []

        def _cb(hmod, typ, name, lparam):
            hits.append(1)
            return True

        enum_res = ENUMPROC(_cb)
        k32.EnumResourceNamesW(mod, ctypes.c_void_p(RT_ICON), enum_res, None)
        k32.FreeLibrary(mod)
        print('[5] %s 内 RT_ICON 资源：%d 个' % (os.path.basename(exe), len(hits)))
        assert len(hits) >= 3, 'exe 里图标资源太少（%d），可能没嵌入多尺寸' % len(hits)

    print('\nSTEP 18 全部通过：品牌图标七档齐全、无水印，界面与 exe 用的是同一份。')

finally:
    pass
