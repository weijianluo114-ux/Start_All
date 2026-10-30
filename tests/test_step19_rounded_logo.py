# -*- coding: utf-8 -*-
"""
Step 19 验收：Logo 圆角与透明背景（REQ-016 / v1.16.0）

覆盖：
  1. `assets/logo.png` 是 RGBA，四角与外圈 3px 全透明（背景已去掉）
  2. 内容几何不变：黑框仍是圆角矩形、位置与 v1.15.0 一致（±4px），
     箭头仍穿出右边框（x 到 ~738）
  3. 半透明像素只出现在边缘（数量少、颜色贴近黑/黄实心色，无白色残边）
  4. 框内不透明：中心、米白底都是 alpha=255（不会在深色背景上"漏底"）
  5. `assets/logo.ico` 各档：四角透明、合成到深底后无浅色非黄残留
  6. `scripts/make_logo.py` 存在，且 `--dry-run` 能从 `assets/logo_src.png`
     复现出一致结果（可复现性，防止"脚本和成品脱节"）

运行：python tests/test_step19_rounded_logo.py
（依赖 Pillow；不启动程序）
"""

import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PNG = os.path.join(ROOT, 'assets', 'logo.png')
ICO = os.path.join(ROOT, 'assets', 'logo.ico')
SRC = os.path.join(ROOT, 'assets', 'logo_src.png')
SCRIPT = os.path.join(ROOT, 'scripts', 'make_logo.py')

# v1.15.0 母版量出的几何（REQ-015），圆角化不允许移动主体
EXPECT_OUTER = (49, 79, 700, 709)     # 黑框外沿 (x0, y0, x1, y1)
EXPECT_ARROW_TIP = 730                # 箭头尖最右（穿出边框）
INK = (14, 19, 18)                    # 黑框实心色
ARROW = (247, 187, 32)                # 箭头黄

try:
    from PIL import Image
    import numpy as np
except ImportError:
    print('需要 Pillow 与 numpy 才能跑本测试')
    sys.exit(1)

# ---------- 1. 母版 RGBA 与外圈透明 ----------
im = Image.open(PNG)
assert im.mode == 'RGBA', '母版应为 RGBA（现在是 %s）' % im.mode
a = np.asarray(im).astype(int)
h, w = a.shape[:2]
al = a[..., 3]
print('[1] %s：%d×%d RGBA，透明 %d / 半透明 %d / 不透明 %d px'
      % (os.path.basename(PNG), w, h, (al == 0).sum(),
         ((al > 0) & (al < 255)).sum(), (al == 255).sum()))
assert (w, h) == (780, 780), '尺寸应保持 780×780 不变'

corners = [al[0, 0], al[0, -1], al[-1, 0], al[-1, -1]]
assert max(corners) == 0, '四角没有透明： %s' % corners
ring = 3
mask = np.ones_like(al, dtype=bool)
mask[ring:-ring, ring:-ring] = False
assert (al[mask] > 8).sum() == 0, '外圈 %dpx 还有不透明像素' % ring
print('    四角与外圈 %dpx 全透明' % ring)

# ---------- 2. 内容几何不变 ----------
ys, xs = np.nonzero(al > 8)
x0, x1 = xs.min(), xs.max()
y0, y1 = ys.min(), ys.max()
print('[2] 不透明包围盒 x %d..%d  y %d..%d' % (x0, x1, y0, y1))
assert abs(x0 - EXPECT_OUTER[0]) <= 4 and abs(y0 - EXPECT_OUTER[1]) <= 4, \
    '黑框左/上沿移动了：%s' % ((x0, y0),)
assert abs(y1 - EXPECT_OUTER[3]) <= 4, '黑框下沿移动了：%d' % y1
assert x1 >= EXPECT_ARROW_TIP, '箭头不再穿出边框（最右只到 %d）' % x1

# 黑框中部行：左边界与右边界应与 v1.15.0 一致
mid = al[EXPECT_OUTER[1] + 100]
dark = np.nonzero(mid > 200)[0]
assert abs(dark.min() - EXPECT_OUTER[0]) <= 4, '黑框左边界移动了'
# 圆角确实存在：角落 (x0+2, y0+2) 应透明，直线段处 (x0+2, 中部) 应不透明
assert al[y0 + 2, x0 + 2] <= 8, '左上角 (x0+2,y0+2) 不透明——圆角没生效'
assert al[(y0 + y1) // 2, x0 + 2] > 200, '黑框左边缘中部反而透明了'
print('    黑框位置不变、圆角生效、箭头穿出到 x=%d' % x1)

# ---------- 3. 边缘无白边 ----------
# 半透明像素的颜色必须贴近黑或黄实心色（抗锯齿混色），出现"亮且不黄"的就是白边
rgb = a[..., :3].astype(float)
aln = al / 255.0
band = (aln > 0.03) & (aln < 0.97)
d_ink = np.linalg.norm(rgb - np.array(INK, dtype=float), axis=2)
d_arr = np.linalg.norm(rgb - np.array(ARROW, dtype=float), axis=2)
bad = band & (np.minimum(d_ink, d_arr) > 60)
print('[3] 半透明 %d px，其中颜色异常（白边嫌疑）%d px' % (band.sum(), bad.sum()))
assert bad.sum() < 30, '边缘有 %d 个异常混色像素（白边）' % bad.sum()

# ---------- 4. 框内不透明 ----------
print('[4] 中心 alpha=%d  米白底样本 alpha=%d' % (al[400, 400], al[200, 300]))
assert al[400, 400] == 255 and al[200, 300] == 255, '框内出现透明区（漏底）'

# ---------- 5. ICO 各档 ----------
ico = Image.open(ICO)
sizes = sorted(s[0] for s in ico.info.get('sizes', []))
assert sizes == [16, 24, 32, 48, 64, 128, 256], 'ICO 档位不对：%s' % sizes
# 母版轮廓（按档位缩小）：浅色像素只允许出现在轮廓内——
# 16px 下边框只有 0.84px，框内米白底本来就贴着透明区，
# 按"贴透明区"判定会把设计保留的米白底误判成白边；
# 真正的缩放白边一定落在轮廓**外**（母版 alpha=0 的地方）。
master_al = Image.fromarray(((al > 128) * 255).astype('uint8'), 'L')
print('[5] ICO 七档齐全，逐档检查：')
bg_dark = np.array([27, 27, 31], dtype=float)
for s in sizes:
    ico.size = (s, s)
    fr = np.asarray(ico.convert('RGBA')).astype(float)
    fal = fr[..., 3] / 255.0
    # 四角透明
    cs = [fr[0, 0, 3], fr[0, -1, 3], fr[-1, 0, 3], fr[-1, -1, 3]]
    assert max(cs) <= 8, '%dpx 帧四角不透明' % s
    # 合成到深底：亮且非黄的像素就是白边
    comp = fr[..., :3] * fal[..., None] + bg_dark * (1 - fal[..., None])
    lum = comp.mean(axis=2)
    yellow = (comp[..., 0] > 150) & (comp[..., 2] < 140)
    sil = np.asarray(master_al.resize((s, s), Image.BOX)) > 128
    whiteish = ((lum > 150) & ~yellow & ~sil).sum()
    print('    %3dpx：四角透明，轮廓外浅色非黄残留 %d px' % (s, whiteish))
    assert whiteish == 0, \
        '%dpx 帧轮廓外有 %d 个浅色非黄像素（白边）' % (s, whiteish)

# ---------- 6. 可复现 ----------
assert os.path.exists(SCRIPT), '缺少 scripts/make_logo.py'
assert os.path.exists(SRC), '缺少 assets/logo_src.png（母版源）'
sys.path.insert(0, os.path.join(ROOT, 'scripts'))
import make_logo
regen = make_logo.make(SRC, make_logo.DEFAULT_RADIUS, dry_run=True)
regen_a = np.asarray(regen).astype(int)
diff = (np.abs(regen_a - a) > 8).any(axis=2).sum()
print('[6] make_logo.py dry-run 复现：与成品差异 %d px' % diff)
assert diff == 0, '脚本复现结果与成品不一致（%d px）' % diff

print('\nSTEP 19 全部通过：圆角 + 透明背景 + 几何不变 + 无白边 + ICO 各档干净 + 可复现。')
