"""Measure which way each cell of a ring atlas is actually looking.

The one defect the rest of the pipeline cannot see is a pose sitting in the wrong
cell. Shift, palette, width and overlap are all perfect when every drawing is
correct and correctly aligned but the ORDER is wrong, which is how upstream shipped
a mirrored character: "the one defect that has to be looked at rather than measured".

It can be measured. The face is lighter and warmer than the hair around it, so the
offset of the skin centroid from the head centroid points where the head is turned.
That vector is compared against the heading each cell is supposed to carry.
"""
import os
import sys

import numpy as np
from PIL import Image

ROOT = os.environ.get('MASCOT_ROOT', os.getcwd())
DEST = os.environ.get('MASCOT_DEST', os.path.join(ROOT, 'public', 'mascots'))
COLS, ROWS, DIRECTIONS = 6, 3, 16
HEAD_BAND = 0.62      # top of the character only: the shirt below is light too
TOLERANCE = 42.0      # degrees a cell may sit from its nominal heading


def cells(path):
    im = Image.open(path).convert('RGBA')
    t = im.size[0] // COLS
    return [np.array(im.crop(((i % COLS) * t, (i // COLS) * t,
                              (i % COLS + 1) * t, (i // COLS + 1) * t)))
            for i in range(COLS * ROWS)]


def gaze(cell):
    """Unit vector from the head's centre toward the face, y pointing down."""
    a = cell.astype(np.float32)
    opaque = a[..., 3] > 100
    rows = np.where(opaque.any(axis=1))[0]
    if not len(rows):
        return None
    cut = rows.min() + int((rows.max() - rows.min()) * HEAD_BAND)
    head = opaque.copy()
    head[cut:] = False
    if head.sum() < 50:
        return None

    r, g, b = a[..., 0], a[..., 1], a[..., 2]
    # Skin: warm and mid-to-light. Hair, brows and beard are dark and near-neutral.
    skin = head & (r > 120) & (r - b > 28) & (r + g + b > 300)
    if skin.sum() < 50:
        return None

    ys, xs = np.mgrid[0:cell.shape[0], 0:cell.shape[1]]
    hx, hy = xs[head].mean(), ys[head].mean()
    sx, sy = xs[skin].mean(), ys[skin].mean()
    # Scale by the head's own size so cells of different crops stay comparable.
    span = max(head.sum() ** 0.5, 1)
    return (sx - hx) / span, (sy - hy) / span


def wrap(d):
    return (d + 180) % 360 - 180


name = sys.argv[1]
frames = cells(os.path.join(DEST, f'{name}-directions.webp'))
vectors = [gaze(f) for f in frames]

# The face always sits below the hair mass, so the raw offset points downward in
# every cell and that constant swamps the turn. The signal is each cell's DEVIATION
# from the sheet's mean pose. Each axis is then normalised by its own spread, because
# a head turns further horizontally than it nods vertically and the check is about the
# ORDER poses go round in, not how far each one travels.
ref = np.array([v for v in vectors[:DIRECTIONS] if v])
mean = ref.mean(axis=0)
spread = ref.std(axis=0)
spread[spread == 0] = 1.0


def heading(v):
    d = (np.array(v) - mean) / spread
    return np.degrees(np.arctan2(d[1], d[0])) % 360, float(np.hypot(*d))


scale = np.mean([heading(v)[1] for v in ref]) or 1.0

print(f'{"cell":>4} {"want":>7} {"measured":>9} {"error":>7} {"strength":>9}')
errors, weak = [], []
for i in range(DIRECTIONS):
    v = vectors[i]
    if v is None:
        print(f'{i:>4} {"?":>7} {"no face":>9}')
        continue
    want = i * (360 / DIRECTIONS)
    got, mag = heading(v)
    err = wrap(got - want)
    strength = mag / scale
    flag = '  <-- off' if abs(err) > TOLERANCE else ''
    if abs(err) > TOLERANCE:
        errors.append(i)
    if strength < 0.45:
        weak.append(i)
    print(f'{i:>4} {want:6.1f}d {got:8.1f}d {err:+6.1f}d {strength:8.2f}{flag}')

order = [heading(v)[0] for v in vectors[:DIRECTIONS] if v]
steps = [wrap(b - a) for a, b in zip(order, order[1:] + order[:1])]
backwards = [i for i, s in enumerate(steps) if s <= 0]

print(f'\ncells off heading (>{TOLERANCE:.0f}d): {errors or "none"}')
print(f'cells with a weak turn (<0.45 of mean): {weak or "none"}')
print(f'non-monotonic steps around the ring: {backwards or "none"}')
print(f'mean absolute heading error: '
      f'{np.mean([abs(wrap(heading(v)[0] - i * (360 / DIRECTIONS))) for i, v in enumerate(vectors[:DIRECTIONS]) if v]):.1f}d')
rest = vectors[16]
if rest:
    print(f'resting cell 16 deviates {heading(rest)[1] / scale:.2f} of a mean turn '
          f'(should be small)')
