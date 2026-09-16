"""Draw a synthetic 16-direction character so the runtime can be tested without art.

Not a mascot anyone would ship. It exists to prove the atlas geometry, the
crossfade and the tilt spring behave before real sheets are generated.
"""
import math
import os
import sys

from PIL import Image, ImageDraw

TILE = 288
COLS, ROWS = 6, 3
DIRECTIONS = 16
SS = 4  # supersample, then downscale, so edges are clean

FUR = (236, 137, 62)
FUR_DARK = (198, 100, 36)
CREAM = (252, 238, 214)
LINE = (58, 40, 30)
BLUSH = (240, 150, 150)


def head(draw, cx, cy, r, dx, dy, expression='calm'):
    """One head, turned by the unit vector (dx, dy)."""
    shift_x, shift_y = dx * r * 0.30, dy * r * 0.24

    # Ears: the one the head turns away from reads smaller.
    for side in (-1, 1):
        near = 1.0 + side * dx * 0.35
        ex = cx + side * r * 0.66 + shift_x * 0.7
        ey = cy - r * 0.72 + shift_y * 0.7
        w, h = r * 0.34 * near, r * 0.46 * near
        draw.polygon(
            [(ex - w, ey + h), (ex, ey - h), (ex + w, ey + h)],
            fill=FUR, outline=LINE, width=int(SS * 2.5),
        )

    draw.ellipse([cx - r, cy - r, cx + r, cy + r], fill=FUR, outline=LINE, width=int(SS * 3))

    # Muzzle follows the turn, which is what sells the direction.
    mx, my = cx + shift_x, cy + shift_y + r * 0.22
    draw.ellipse(
        [mx - r * 0.52, my - r * 0.34, mx + r * 0.52, my + r * 0.40],
        fill=CREAM, outline=LINE, width=int(SS * 2),
    )

    for side in (-1, 1):
        bx = cx + side * r * 0.60 + shift_x * 0.8
        by = cy + shift_y + r * 0.16
        draw.ellipse([bx - r * 0.20, by - r * 0.11, bx + r * 0.20, by + r * 0.11], fill=BLUSH)

    for side in (-1, 1):
        ex = cx + side * r * 0.33 + shift_x
        ey = cy - r * 0.12 + shift_y
        w = r * 0.19 * (1.0 - abs(dx) * 0.22 * (1 if side * dx < 0 else -0.1))
        if expression in ('blink', 'heart', 'sparkle', 'bashful', 'sleepy', 'delighted'):
            draw.arc(
                [ex - w, ey - w * 0.9, ex + w, ey + w * 0.9],
                start=200, end=340, fill=LINE, width=int(SS * 3),
            )
            continue
        if expression == 'dizzy':
            for k in range(3):
                q = w * (1 - k * 0.3)
                draw.arc([ex - q, ey - q, ex + q, ey + q], start=0, end=300,
                         fill=LINE, width=int(SS * 2))
            continue
        big = 1.35 if expression == 'surprised' else 1.0
        draw.ellipse([ex - w * big, ey - w * 1.25 * big, ex + w * big, ey + w * 1.25 * big],
                     fill=(255, 255, 255), outline=LINE, width=int(SS * 2))
        pupil = w * 0.62 * big
        px, py = ex + dx * w * 0.30, ey + dy * w * 0.34
        draw.ellipse([px - pupil, py - pupil, px + pupil, py + pupil], fill=LINE)
        draw.ellipse([px - pupil * 0.75, py - pupil * 0.9, px - pupil * 0.1, py - pupil * 0.25],
                     fill=(255, 255, 255))

    nx, ny = cx + shift_x, cy + shift_y + r * 0.12
    draw.ellipse([nx - r * 0.11, ny - r * 0.08, nx + r * 0.11, ny + r * 0.08], fill=LINE)

    if expression == 'surprised':
        draw.ellipse([nx - r * 0.13, ny + r * 0.20, nx + r * 0.13, ny + r * 0.50],
                     fill=(120, 60, 60), outline=LINE, width=int(SS * 2))
    elif expression == 'delighted':
        draw.chord([nx - r * 0.30, ny + r * 0.08, nx + r * 0.30, ny + r * 0.52],
                   start=0, end=180, fill=(150, 70, 70), outline=LINE, width=int(SS * 2))


def body(draw, cx, cy, r):
    """Drawn once, identical in every cell. This is what the head moves on top of."""
    w = r * 0.66
    top = cy + r * 0.80
    draw.rounded_rectangle(
        [cx - w, top, cx + w, top + r * 0.95],
        radius=r * 0.34, fill=FUR_DARK, outline=LINE, width=int(SS * 3),
    )
    draw.ellipse([cx - w * 0.52, top + r * 0.10, cx + w * 0.52, top + r * 0.92], fill=CREAM)


def symbol(draw, cx, cy, r, kind):
    if kind == 'heart':
        sx, sy, s = cx, cy - r * 1.55, r * 0.20
        draw.ellipse([sx - s, sy - s * 0.8, sx, sy + s * 0.4], fill=(226, 70, 90))
        draw.ellipse([sx, sy - s * 0.8, sx + s, sy + s * 0.4], fill=(226, 70, 90))
        draw.polygon([(sx - s, sy + s * 0.05), (sx + s, sy + s * 0.05), (sx, sy + s * 1.3)],
                     fill=(226, 70, 90))
    elif kind == 'sparkle':
        for k, (ox, oy, s) in enumerate([(-0.55, -1.70, 0.13), (0.0, -1.88, 0.17),
                                         (0.58, -1.62, 0.12)]):
            sx, sy, q = cx + ox * r, cy + oy * r, s * r
            draw.polygon([(sx, sy - q), (sx + q * 0.32, sy - q * 0.32), (sx + q, sy),
                          (sx + q * 0.32, sy + q * 0.32), (sx, sy + q),
                          (sx - q * 0.32, sy + q * 0.32), (sx - q, sy),
                          (sx - q * 0.32, sy - q * 0.32)], fill=(247, 199, 62))
    elif kind == 'sleepy':
        for k, s in enumerate([0.16, 0.21, 0.27]):
            zx, zy, q = cx + r * (0.45 + k * 0.30), cy - r * (1.25 + k * 0.34), s * r
            draw.line([(zx - q, zy - q), (zx + q, zy - q), (zx - q, zy + q), (zx + q, zy + q)],
                      fill=(80, 130, 200), width=int(SS * 3), joint='curve')


def cell(expression, dx, dy, sym=None, size=TILE):
    im = Image.new('RGBA', (size * SS, size * SS), (0, 0, 0, 0))
    d = ImageDraw.Draw(im)
    cx, cy, r = size * SS / 2, size * SS * 0.42, size * SS * 0.235
    body(d, cx, cy, r)
    head(d, cx, cy, r, dx, dy, expression)
    if sym:
        symbol(d, cx, cy, r, sym)
    return im.resize((size, size), Image.LANCZOS)


RING_A = [10, 12, 14, 8, 16, 0, 6, 4, 2]   # ul u ur l c r dl d dr
RING_B = [11, 13, 15, 1, 3, 5, 7, 9, 17]   # clockwise sweep from NNW, then straight ahead
ORDER = ['blink', 'heart', 'sparkle', 'surprised', 'wink',
         'bashful', 'sleepy', 'dizzy', 'delighted']
SYMBOLS = {'heart': 'heart', 'sparkle': 'sparkle', 'sleepy': 'sleepy'}


def ring_vector(ring):
    """Unit direction for a ring cell. 16 and 17 both mean straight ahead."""
    if ring >= DIRECTIONS:
        return 0.0, 0.0
    a = ring * (2 * math.pi / DIRECTIONS)
    return math.cos(a), math.sin(a)


def source(dest='characters/test', px=1024):
    """Raw 3x3 sheets in the shape the real pipeline consumes, for testing build.py."""
    os.makedirs(dest, exist_ok=True)
    w = px // 3
    for fname, ring in (('directions.png', RING_A), ('directions-b.png', RING_B)):
        sheet = Image.new('RGBA', (w * 3, w * 3), (0, 0, 0, 0))
        for i, cellno in enumerate(ring):
            dx, dy = ring_vector(cellno)
            sheet.paste(cell('calm', dx, dy, size=w), ((i % 3) * w, (i // 3) * w))
        sheet.save(os.path.join(dest, fname))
        print(f'  {fname}  {sheet.size}')
    sheet = Image.new('RGBA', (w * 3, w * 3), (0, 0, 0, 0))
    for i, e in enumerate(ORDER):
        sheet.paste(cell(e, 0.0, 0.0, SYMBOLS.get(e), size=w), ((i % 3) * w, (i // 3) * w))
    sheet.save(os.path.join(dest, 'reactions.png'))
    print(f'  reactions.png  {sheet.size}')


def main():
    if '--source' in sys.argv:
        source()
        return
    dest = sys.argv[1] if len(sys.argv) > 1 else 'public/mascots'
    name = sys.argv[2] if len(sys.argv) > 2 else 'test'
    os.makedirs(dest, exist_ok=True)

    atlas = Image.new('RGBA', (TILE * COLS, TILE * ROWS), (0, 0, 0, 0))
    for i in range(DIRECTIONS):
        a = i * (2 * math.pi / DIRECTIONS)
        atlas.paste(cell('calm', math.cos(a), math.sin(a)),
                    ((i % COLS) * TILE, (i // COLS) * TILE))
    atlas.paste(cell('calm', 0.0, 0.0), ((16 % COLS) * TILE, (16 // COLS) * TILE))
    atlas.save(os.path.join(dest, f'{name}-directions.webp'), quality=92, method=6)

    order = ['blink', 'heart', 'sparkle', 'surprised', 'wink',
             'bashful', 'sleepy', 'dizzy', 'delighted']
    symbols = {'heart': 'heart', 'sparkle': 'sparkle', 'sleepy': 'sleepy'}
    react = Image.new('RGBA', (TILE * 3, TILE * 3), (0, 0, 0, 0))
    for i, name_ in enumerate(order):
        react.paste(cell(name_, 0.0, 0.0, symbols.get(name_)),
                    ((i % 3) * TILE, (i // 3) * TILE))
    react.save(os.path.join(dest, f'{name}-reactions.webp'), quality=92, method=6)

    for f in (f'{name}-directions.webp', f'{name}-reactions.webp'):
        p = os.path.join(dest, f)
        print(f'  {f}  {Image.open(p).size}  {os.path.getsize(p) // 1024} KB')


if __name__ == '__main__':
    main()
