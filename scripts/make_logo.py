# -*- coding: utf-8 -*-
"""
品牌图生成：把方形黑框改成圆角，并把框外米白底改成透明。

输入：`assets/logo.png`（780×780 母版，方块黑框 + 米白底）
输出：同尺寸 RGBA 母版（圆角 + 透明底）、`assets/logo.ico`（七档）

为什么需要这个脚本
------------------
v1.15.0 的 logo 是「方块黑框 + 满幅米白底」，放进任意界面都得带一块米白方块，
无法叠在深色/彩色背景上。这里做三件事：

1. **圆角**：黑框外轮廓换成圆角矩形。切角位置在黑框实心处，所以切出来的
   边缘要自己生成抗锯齿（源图在该处是硬边，没有可复用的 AA）。
2. **透明**：黑框以外（原米白底）alpha=0；黑框内部的米白底保留不透明。
3. **去白边**：源图边框外沿的抗锯齿像素是「黑 × 米白」的混色，直接保留
   会在深色背景上留下一圈浅灰。这里对这些像素做颜色替换（取最近的实心色），
   让 alpha 单独表达边缘覆盖率，混色不再参与。

几何全部实测：黑框外沿 x≈49.5–700.0 / y≈78.8–707.5，边框厚约 41px；
箭头在右侧 y≈397–452 处穿出黑框，尖端到 x≈736。所以「透明」不是简单裁到
黑框范围内，而是「框外只保留那支箭头」。裁到黑框会把箭头截断（见 BUG-008）。

用法
----
    python scripts/make_logo.py                # 用默认半径重新生成 png + ico
    python scripts/make_logo.py --radius 64    # 试别的圆角
    python scripts/make_logo.py --dry-run      # 只打印几何，不写文件

依赖 Pillow + numpy（仅开发期，不进打包依赖）。
"""

import argparse
import os
import struct
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SRC = os.path.join(ROOT, 'assets', 'logo_src.png')   # 原始母版（RGB，方角 + 米白底）
PNG = os.path.join(ROOT, 'assets', 'logo.png')       # 产出（RGBA，圆角 + 透明底）
ICO = os.path.join(ROOT, 'assets', 'logo.ico')

ICO_SIZES = (16, 24, 32, 48, 64, 128, 256)
SS = 8                      # 圆角遮罩超采样倍数（8 → 64 级 alpha，不出现阶梯）
DEFAULT_RADIUS = 72         # 圆角半径（px，780 画布）；边框厚 41，内圆角约 31。
                            # 40/56/72/88 四档对比后定 72：56 与直角差别不大，
                            # 88 的弧已经压到内框抖动处，72 最接近原稿观感。

BG = (241, 234, 221)        # 米白底（实测）
INK = (14, 19, 18)          # 黑框实色（实测）
ARROW = (247, 187, 32)      # 箭头黄（实测）


# ---------------------------------------------------------------- 几何测量
def _edge(values, start, stop, step):
    """在 values 的一维切片里找 0.5 覆盖率交叉点，返回亚像素位置。"""
    idx = range(start, stop, step)
    prev_i, prev_v = None, None
    for i in idx:
        v = values[i]
        if prev_v is not None and (prev_v - 0.5) * (v - 0.5) <= 0 and prev_v != v:
            # 线性插值到 0.5
            t = (0.5 - prev_v) / (v - prev_v)
            return prev_i + t * (i - prev_i) + 0.5   # +0.5：像素 i 覆盖 [i, i+1)
        prev_i, prev_v = i, v
    raise RuntimeError('找不到边缘（%d..%d）' % (start, stop))


def _coverage(rgb):
    """把像素投影到「米白→黑」与「米白→黄」两条色轴上，取较大者作为前景覆盖率。

    投影比「按亮度归一」准：任何黑/米白、黄/米白的混色都能解出正确比例，
    而框内的米白底（与背景几乎同色）会得到约 0，正好留给 interior 遮罩去覆盖。
    """
    import numpy as np
    bg = np.array(BG, dtype=np.float64)
    out = None
    for fg in (INK, ARROW):
        fg = np.array(fg, dtype=np.float64)
        axis = fg - bg
        t = ((rgb - bg) @ axis) / float(axis @ axis)
        t = np.clip(t, 0.0, 1.0)
        out = t if out is None else np.maximum(out, t)
    return out


def measure(rgb):
    """返回 (外框矩形, 内框矩形)，均为连续坐标 (x0, y0, x1, y1)。"""
    import numpy as np
    bg_l = sum(BG) / 3.0
    ink_l = sum(INK) / 3.0
    lum = rgb.mean(axis=2)
    # 只用亮度判断「深色」，避免把黄色箭头算成框
    dark = np.clip((bg_l - lum) / (bg_l - ink_l), 0.0, 1.0)
    h, w = dark.shape

    # 外沿：取远离箭头的行/列（箭头在 y≈397–452 打断右边框）
    y_probe = int(h * 0.35)                     # 273 → 穿过左右边框
    x_probe = int(w * 0.25)                     # 195 → 穿过上下边框
    x0 = _edge(dark[y_probe], 0, w, 1)
    x1 = _edge(dark[y_probe], w - 1, 0, -1)
    y0 = _edge(dark[:, x_probe], 0, h, 1)
    y1 = _edge(dark[:, x_probe], h - 1, 0, -1)

    # 内沿：必须从边框「实心处」起步，否则一上来就命中同一条边
    pad = 10
    x0i = _edge(dark[y_probe], int(x0) + pad, int(x1) - pad, 1)
    x1i = _edge(dark[y_probe], int(x1) - pad, int(x0) + pad, -1)
    y0i = _edge(dark[:, x_probe], int(y0) + pad, int(y1) - pad, 1)
    y1i = _edge(dark[:, x_probe], int(y1) - pad, int(y0) + pad, -1)
    return (x0, y0, x1, y1), (x0i, y0i, x1i, y1i)


def _erode(mask, radius):
    """二值腐蚀（radius 为像素数），用来把「圆角矩形」整体内缩。"""
    import numpy as np

    out = mask.copy()
    for _ in range(int(radius)):
        shrunk = out.copy()
        shrunk[1:, :] &= out[:-1, :]
        shrunk[:-1, :] &= out[1:, :]
        shrunk[:, 1:] &= out[:, :-1]
        shrunk[:, :-1] &= out[:, 1:]
        out = shrunk
    return out


# ---------------------------------------------------------------- 遮罩构建
def build_alpha(rgb, radius):
    import numpy as np
    from PIL import Image, ImageDraw

    h, w = rgb.shape[:2]
    (x0, y0, x1, y1), (ix0, iy0, ix1, iy1) = measure(rgb)

    # 1. 圆角几何遮罩（超采样后 BOX 降采样 = 面积平均，边缘天然抗锯齿）
    mask = Image.new('L', (w * SS, h * SS), 0)
    ImageDraw.Draw(mask).rounded_rectangle(
        [x0 * SS, y0 * SS, x1 * SS - 1, y1 * SS - 1],
        radius=radius * SS, fill=255)
    geom = np.asarray(mask.resize((w, h), Image.BOX), dtype=np.float64) / 255.0

    # 2. 真实边缘覆盖率（源图自带的那 1px 抗锯齿）
    #    源图米白底本身有 ±6 的噪点，投影后会得到 0.03 左右的假覆盖率，
    #    在深色背景上表现为一圈极淡的米白雾；这里减掉噪声底再拉伸。
    cov = np.clip((_coverage(rgb) - 0.06) / 0.94, 0.0, 1.0)

    # 3. 箭头穿出黑框的那一截：不受圆角遮罩约束，只按自身边缘取 alpha
    yy, xx = np.mgrid[0:h, 0:w]
    protrude = (xx >= x1 - 1.0) & (yy > y0) & (yy < y1)

    alpha = np.where(protrude, cov, np.minimum(geom, cov))

    # 4. 框内一律不透明：内容与米白底都保留。
    #    做法是「圆角矩形内缩 2px」整块补实——
    #      * 源图边框内沿有 ±8px 的手绘抖动，用「内框矩形」近似一定开缝或溢出；
    #      * 也不能靠连通性补洞：箭头把黑框打断了，框内米白与画布外的米白
    #        本来就是连通的（实测过），按连通性判断会把整块米白底判成背景。
    #    箭头打断边框处的那圈米白一并补实：它是原画里「箭头顶开黑框」的留白，
    #    留着才是原设计；清掉反而让断口露出背景，箭头像浮在外面。
    fill = _erode(geom > 0.5, 2)
    alpha = np.maximum(alpha, fill)
    return np.clip(alpha, 0.0, 1.0), (x0, y0, x1, y1), (ix0, iy0, ix1, iy1)


def unmix_edge_color(rgb, alpha):
    """按覆盖率反解前景色，消掉米白边。

    源图边缘像素是 `前景 × 米白` 的混合（`observed = a·fg + (1-a)·bg`）。
    既然 alpha 已经由投影算出来了，就可以直接把 fg 解出来：
    `fg = (observed - (1-a)·bg) / a`。反解出的 fg 在米白底上合成回去与源图
    逐像素相等，换到深色/彩色背景上则是一条干净的前景边——
    既不会留下米白雾，也不会像「取最近实心色」那样把边缘涂成发灰的中间色。
    """
    import numpy as np

    bg = np.array(BG, dtype=np.float64)
    a = alpha[..., None]
    safe = np.maximum(a, 0.05)                     # 低 alpha 时除法会放大噪点
    fg = np.clip((rgb - (1.0 - safe) * bg) / safe, 0.0, 255.0)
    out = np.where(a >= 0.995, rgb, fg)
    out = np.where(a < 0.03, np.array(INK, dtype=np.float64), out)

    # 反解在两种地方会过冲出离谱的颜色（比如箭头边缘解出 [255,255,0]）：
    #   * alpha 很小时除法放大噪点；
    #   * 源图那圈 AA 不是严格「前景 × 米白」的混合（箭头内部有自己的明暗）。
    # 这些像素半透明带里颜色离两个实心色都远（>50），直接吸附到较近的实心色——
    # 半透明带只出现在「黑框/箭头 vs 米白」的边缘，前景本来就该是这两色之一。
    band = (alpha > 0.03) & (alpha < 0.97)
    d_ink = np.linalg.norm(out - np.array(INK, dtype=np.float64), axis=2)
    d_arr = np.linalg.norm(out - np.array(ARROW, dtype=np.float64), axis=2)
    stray = band & (np.minimum(d_ink, d_arr) > 50)
    snap = np.where((d_ink <= d_arr)[..., None],
                    np.array(INK, dtype=np.float64),
                    np.array(ARROW, dtype=np.float64))
    out = np.where(stray[..., None], snap, out)
    return out


# ---------------------------------------------------------------- ICO 打包
def _premul_resize(img, size):
    """预乘 alpha 再缩放，避免透明像素的颜色渗进边缘（深色描边/浅色光晕）。

    两个坑都要防：
      * 不预乘直接缩，透明区的颜色会被平均进来，边缘发白；
      * LANCZOS 会在高对比边缘过冲，预乘值可能大于 alpha，反解后颜色溢出成纯白，
        在深色背景上就是一圈白点。所以缩放后把预乘值夹到 alpha 以内。
    反解时用 32 作为分母下限，避免极低 alpha 处把噪点放大成纯色。
    """
    from PIL import Image
    import numpy as np

    a = np.asarray(img, dtype=np.float64)
    pm = a.copy()
    pm[..., :3] *= a[..., 3:4] / 255.0
    small = Image.fromarray(np.clip(pm + 0.5, 0, 255).astype('uint8'), 'RGBA')
    # 缩得太狠（780→16/32，二十多倍）时不能用 LANCZOS：它的支撑域是 3×缩放倍数，
    # 相当于把上下 140 多像素一起平均，黑框边缘会被框内的米白底"洗"成灰色；
    # 过冲还会让预乘值超过 alpha，反解后变成一圈纯白（32px 下肉眼可见）。
    # 这种倍数改用 BOX（按面积平均），256 这种只缩 3 倍才用 LANCZOS 保锐度。
    factor = img.width / float(size)
    small = small.resize((size, size),
                         Image.BOX if factor >= 4 else Image.LANCZOS)
    b = np.asarray(small, dtype=np.float64)
    al = b[..., 3:4]
    rgb = b[..., :3]
    rgb = np.minimum(rgb, al)                       # 掐掉过冲，保证不溢白
    rgb = rgb * 255.0 / np.maximum(al, 32.0)
    out = np.concatenate([np.clip(rgb, 0, 255), al], axis=2)
    return Image.fromarray(np.clip(out + 0.5, 0, 255).astype('uint8'), 'RGBA')


def write_ico(master, path):
    """手写 ICO：≤128 用 32bpp BMP 帧，256 用 PNG（和 v1.15.0 一致）。"""
    import io
    from PIL import Image
    import numpy as np

    frames = []
    for size in ICO_SIZES:
        img = _premul_resize(master, size)
        if size >= 256:
            buf = io.BytesIO()
            img.save(buf, format='PNG', optimize=True)
            frames.append((size, buf.getvalue()))
            continue

        a = np.asarray(img)                       # RGBA
        bgra = a[..., [2, 1, 0, 3]][::-1]          # 自下而上
        hdr = struct.pack('<IiiHHIIiiII', 40, size, size * 2, 1, 32, 0, 0, 0, 0, 0, 0)
        # AND 掩码：32bpp 有 alpha，掩码全 0（Windows 以 alpha 为准）
        row_bytes = ((size + 31) // 32) * 4
        and_mask = b'\x00' * (row_bytes * size)
        frames.append((size, hdr + bgra.tobytes() + and_mask))

    head = struct.pack('<HHH', 0, 1, len(frames))
    offset = 6 + 16 * len(frames)
    entries, blobs = b'', b''
    for size, data in frames:
        entries += struct.pack('<BBBBHHII', size % 256, size % 256, 0, 0, 1, 32,
                               len(data), offset)
        blobs += data
        offset += len(data)
    with open(path, 'wb') as f:
        f.write(head + entries + blobs)
    return len(head + entries + blobs)


# ---------------------------------------------------------------- 主流程
def make(src=SRC, radius=DEFAULT_RADIUS, dry_run=False):
    from PIL import Image
    import numpy as np

    rgb = np.asarray(Image.open(src).convert('RGB'), dtype=np.float64)
    alpha, outer, inner = build_alpha(rgb, radius)
    alpha = np.where(alpha < 0.03, 0.0, alpha)      # 噪声底以下直接判背景
    fixed = unmix_edge_color(rgb, alpha)

    out = np.dstack([fixed, alpha * 255.0])
    img = Image.fromarray(np.clip(out + 0.5, 0, 255).astype('uint8'), 'RGBA')

    print('外框：(%.1f, %.1f) - (%.1f, %.1f)  %d×%d，边框厚约 %.0fpx'
          % (outer[0], outer[1], outer[2], outer[3],
             outer[2] - outer[0], outer[3] - outer[1],
             (inner[0] - outer[0] + inner[1] - outer[1]) / 2))
    print('内框：(%.1f, %.1f) - (%.1f, %.1f)' % inner)
    print('圆角半径：%dpx（占外框宽 %.1f%%）' % (radius, radius / (outer[2] - outer[0]) * 100))
    if dry_run:
        return img

    img.save(PNG)
    size = write_ico(img, ICO)
    print('写出 %s（%d×%d RGBA）' % (os.path.relpath(PNG, ROOT), img.width, img.height))
    print('写出 %s（%d 帧，%d 字节）' % (os.path.relpath(ICO, ROOT), len(ICO_SIZES), size))
    return img


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--radius', type=int, default=DEFAULT_RADIUS)
    ap.add_argument('--src', default=SRC)
    ap.add_argument('--dry-run', action='store_true')
    args = ap.parse_args()
    make(args.src, args.radius, args.dry_run)


if __name__ == '__main__':
    sys.exit(main())
