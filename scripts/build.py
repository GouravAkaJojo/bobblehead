"""Turn a character's two 3x3 source sheets into the two atlases in public/mascots.

Scratchpad copy of the pipeline that used to live in scripts/, with one fix: the
'content' anchor now measures the character's largest connected blob rather than the
whole alpha bounding box. The old version included floating hearts and sparkles in
that box, which shoved the character down in exactly those cells.

    python build.py <name> [--anchor face|head|content]
"""
import os
import sys

import numpy as np
from PIL import Image, ImageFilter
from scipy import ndimage

# Where the project lives. Defaults to the current working directory so the skill
# works in whatever repo it is invoked from; override with MASCOT_ROOT.
ROOT = os.environ.get('MASCOT_ROOT', os.getcwd())
SRC = os.environ.get('MASCOT_SRC', os.path.join(ROOT, 'characters'))
DEST = os.environ.get('MASCOT_DEST', os.path.join(ROOT, 'public', 'mascots'))
os.makedirs(DEST, exist_ok=True)

TILE = 360
HEAD_BAND = 0.55
BODY_BAND = 0.40
SHOULDER_BAND = 0.05   # fraction of the TILE, not of the character
FACE_TOLERANCE = 34
SCALE_CLAMP = 0.10
MATCH_CLAMP = float(__import__('os').environ.get('MATCH_CLAMP', 0.20))  # how far the reactions sheet may be rescaled to match the directions sheet
FIT_BAND = 0.86       # how far down the character the cross-sheet fit starts looking. Must
                      # clear hair that reaches the shoulders, or the fit shrinks the body to
                      # make bushier expression-sheet hair agree.
SETTLE = 26           # how far a single reaction frame may be nudged onto the shoulders
FADE_DEPTH = float(__import__('os').environ.get('FADE_DEPTH', 0.12))   # depth of the bottom fade, as a fraction of the tile
BOTTOM_ANCHOR = 0.93  # where every character's bottom edge lands down the tile
BLUR_RADII = [1.5, 3, 6, 12]

# The runtime atlas is a 6x3 ring: cells 0..15 are head directions clockwise from
# east, 16 is the resting pose and 17 is padding. Sheet A (the upstream nine) fills
# the even cells, sheet B the odd ones, so A alone still produces a valid atlas.
COLS, ROWS = 6, 3
#          ul  u   ur  l  c   r  dl  d  dr
RING_A = {0: 10, 1: 12, 2: 14, 3: 8, 4: 16, 5: 0, 6: 6, 7: 4, 8: 2}
# Sheet B is drawn as one clockwise sweep of the eight in-between angles, starting
# north-north-west, with a straight-ahead ninth cell that lands in the padding slot.
RING_B = {0: 11, 1: 13, 2: 15, 3: 1, 4: 3, 5: 5, 6: 7, 7: 9, 8: 17}
# Sheet C, optional, redraws the whole lower arc east-through-south-to-west. Asked
# for nine directions at once the model draws the down-diagonals as plain sideways
# turns, so the bottom of the ring collapses onto the horizontal poses. Drawn on its
# own the arc keeps a consistent tilt, and it overrides A and B across cells 0..8.
RING_C = {i: i for i in range(9)}


def drop_bleed(tile):
    """Erase anything that runs off an edge of the cell.

    Neighbouring cells leak into each other: a character drawn too tall leaves a sliver
    along the next cell's top edge, and whiskers or ears reaching sideways leave specks
    down its sides. Once alignment shifts the frame, those become marks floating beside
    the mascot. Hearts, sparkles and zzz are safe, because the art brief requires a clear
    margin and a legitimate symbol therefore never reaches an edge.
    """
    a = np.array(tile)
    opaque = a[..., 3] > 40
    edges = np.concatenate([opaque[:2, :].ravel(), opaque[-2:, :].ravel(),
                            opaque[:, :2].ravel(), opaque[:, -2:].ravel()])
    if not edges.any():
        return tile
    labels, count = ndimage.label(opaque)
    if count == 0:
        return tile
    keep = int(np.argmax(ndimage.sum(opaque, labels, range(1, count + 1)))) + 1
    touching = set(np.unique(np.concatenate([
        labels[:2, :].ravel(), labels[-2:, :].ravel(),
        labels[:, :2].ravel(), labels[:, -2:].ravel(),
    ]))) - {0, keep}
    if not touching:
        return tile
    a[np.isin(labels, list(touching)), 3] = 0
    return Image.fromarray(a, 'RGBA')


def tiles(path):
    sheet = Image.open(path).convert('RGBA')
    w = sheet.size[0] // 3
    return w, [drop_bleed(sheet.crop((c * w, r * w, (c + 1) * w, (r + 1) * w)))
               for r in range(3) for c in range(3)]


def body_mask(opaque):
    """The character itself: the largest connected blob, so floating symbols are excluded."""
    labels, count = ndimage.label(opaque)
    if count == 0:
        return opaque
    sizes = ndimage.sum(opaque, labels, range(1, count + 1))
    return labels == int(np.argmax(sizes)) + 1


def anchor_box(tile, mode):
    a = np.array(tile)
    rgb, alpha = a[..., :3].astype(int), a[..., 3]
    opaque = alpha > 128
    body = body_mask(opaque)
    ys, xs = np.where(body)

    if mode == 'content':
        return xs.min(), ys.min(), xs.max(), ys.max()

    if mode == 'shoulders':
        # A fixed-height sliver measured up from the character's bottom edge. Using a
        # fraction of the character's HEIGHT instead makes the band grow and shrink as
        # the head tilts, and since alignment centres this box, a changing box height
        # leaves the bottom edge wobbling a couple of pixels between frames.
        floor = ys.max()
        band = max(0, floor - int(alpha.shape[0] * SHOULDER_BAND))
        yy, xx = np.where(body[band:, :])
        return xx.min(), yy.min() + band, xx.max(), yy.max() + band

    if mode == 'body':
        # The lower part of the character. Pinning THIS is what keeps a mascot planted
        # while its head turns -- anchoring on the whole silhouette instead lets the
        # head's movement drag the body sideways to compensate.
        floor = ys.max()
        band = floor - int((ys.max() - ys.min()) * BODY_BAND)
        yy, xx = np.where(body[band:, :])
        return xx.min(), yy.min() + band, xx.max(), yy.max() + band

    cut = ys.min() + int((ys.max() - ys.min()) * HEAD_BAND)
    if mode == 'head':
        yy, xx = np.where(body[:cut, :])
        return xx.min(), yy.min(), xx.max(), yy.max()

    head = np.zeros_like(body)
    head[ys.min():cut, :] = True
    quantised = rgb // 24
    keys = quantised[..., 0] * 10000 + quantised[..., 1] * 100 + quantised[..., 2]
    values, counts = np.unique(keys[body & head], return_counts=True)
    fill = rgb[body & head & (keys == values[np.argmax(counts)])].mean(axis=0)
    match = body & (np.abs(rgb - fill) < FACE_TOLERANCE).all(axis=2)
    labels, count = ndimage.label(match)
    sizes = ndimage.sum(match, labels, range(1, count + 1))
    ys, xs = np.where(labels == int(np.argmax(sizes)) + 1)
    return xs.min(), ys.min(), xs.max(), ys.max()


def blur_premultiplied(image, radius):
    a = np.array(image).astype(np.float32)
    alpha = a[..., 3:4] / 255.0
    colour = Image.fromarray(np.clip(a[..., :3] * alpha, 0, 255).astype(np.uint8), 'RGB')
    colour = colour.filter(ImageFilter.GaussianBlur(radius))
    faded = Image.fromarray(a[..., 3].astype(np.uint8), 'L').filter(ImageFilter.GaussianBlur(radius))
    blurred = np.array(colour).astype(np.float32)
    weight = np.array(faded).astype(np.float32)[..., None] / 255.0
    rgb = np.where(weight > 0.004, blurred / np.maximum(weight, 0.004), 0)
    return Image.fromarray(np.dstack([np.clip(rgb, 0, 255), weight[..., 0] * 255]).astype(np.uint8), 'RGBA')


name = sys.argv[1]
mode = sys.argv[sys.argv.index('--anchor') + 1] if '--anchor' in sys.argv else 'face'
# The vignette exists to dissolve a bust that is cut off at the bottom of its cell.
# A character drawn as a complete shape has nothing to hide, so skip it.
VIGNETTE = '--no-vignette' not in sys.argv

W, direction_tiles = tiles(os.path.join(SRC, name, 'directions.png'))
_, reaction_tiles = tiles(os.path.join(SRC, name, 'reactions.png'))

between_path = os.path.join(SRC, name, 'directions-b.png')
between_tiles = tiles(between_path)[1] if os.path.exists(between_path) else None
print('  in-between sheet ' + ('found' if between_tiles else 'absent, filling odd cells from sheet A'))

lower_path = os.path.join(SRC, name, 'directions-c.png')
lower_tiles = tiles(lower_path)[1] if os.path.exists(lower_path) else None
print('  lower-arc sheet ' + ('found, overriding cells 0-8' if lower_tiles else 'absent'))

# The eyes-shut ring. Built here rather than on its own so every blink frame is
# normalised against the SAME anchors as the open frames: aligned apart, the head
# would shift the instant the character blinks.
def shut(stem):
    path = os.path.join(SRC, name, f'{stem}-blink.png')
    return tiles(path)[1] if os.path.exists(path) else None

blink_tiles = shut('directions')
blink_b_tiles = shut('directions-b')
blink_c_tiles = shut('directions-c')
print('  blink sheets ' + (', '.join(n for n, t in (('A', blink_tiles), ('B', blink_b_tiles),
      ('C', blink_c_tiles)) if t) or 'absent, blinking will fall back to the expressions sheet'))

boxes = [anchor_box(t, mode) for t in direction_tiles]
target_cx = sum((b[0] + b[2]) / 2 for b in boxes) / 9
target_cy = sum((b[1] + b[3]) / 2 for b in boxes) / 9
target_w = sum(b[2] - b[0] for b in boxes) / 9

# The clamp guards against a noisy anchor distorting frames, so tie it to how noisy
# the anchor actually is. When the anchor is rock-steady within the sheet, a large
# correction is real -- the two sheets were simply drawn at different scales -- and
# refusing it leaves the character changing size when the boop swaps atlases.
widths = [b[2] - b[0] for b in boxes]
anchor_noise = (max(widths) - min(widths)) / target_w
clamp = SCALE_CLAMP if anchor_noise > 0.03 else 0.35
print(f'  anchor noise {anchor_noise*100:.1f}% -> scale clamp +-{clamp*100:.0f}%')


# Headroom around the aligned canvas. Without it, a frame that shifts up to match the
# anchor gets pasted at a negative offset and loses whatever is at its top -- which is
# exactly where floating hearts, sparkles and zzz live.
PAD = W // 2


def align(tile):
    box = anchor_box(tile, mode)
    scale = min(1 + clamp, max(1 - clamp, target_w / (box[2] - box[0])))
    scaled = tile.resize((round(W * scale), round(W * scale)), Image.LANCZOS)
    cx, cy = (box[0] + box[2]) / 2 * scale, (box[1] + box[3]) / 2 * scale
    canvas = Image.new('RGBA', (W + 2 * PAD, W * 2 + 2 * PAD), (0, 0, 0, 0))
    canvas.alpha_composite(scaled, (PAD + round(target_cx - cx), PAD + round(target_cy - cy)))
    return canvas


def blob_bounds(frame):
    """Top and bottom rows of the character in an aligned frame, symbols excluded."""
    body = body_mask(np.array(frame)[..., 3] > 100)
    rows = np.where(body.any(axis=1))[0]
    return rows.min(), rows.max()


def head_width(frame):
    """Widest row in the upper part of the character.

    Overall silhouette height is the wrong thing to match the two sheets on: an
    expression sheet that draws the hair a little bushier is taller without the
    character being any bigger, and scaling to compensate drags the shoulders out of
    place. The head is both the dominant shape and the part the eye follows, so its
    width is what has to agree between the sheets.
    """
    body = body_mask(np.array(frame)[..., 3] > 100)
    rows = np.where(body.any(axis=1))[0]
    upper = body[rows.min():rows.min() + int((rows.max() - rows.min()) * HEAD_BAND), :]
    return upper.sum(axis=1).max()


direction_frames = [align(t) for t in direction_tiles]
reaction_frames = [align(t) for t in reaction_tiles]
between_frames = [align(t) for t in between_tiles] if between_tiles else []
lower_frames = [align(t) for t in lower_tiles] if lower_tiles else []
blink_frames = [align(t) for t in blink_tiles] if blink_tiles else []
blink_b_frames = [align(t) for t in blink_b_tiles] if blink_b_tiles else []
blink_c_frames = [align(t) for t in blink_c_tiles] if blink_c_tiles else []

# Match the two sheets to each other. Each sheet is normalised against its own anchor,
# so a reactions sheet drawn at a different scale survives that untouched and the
# character visibly changes size and drops the moment a boop swaps atlases. The
# per-frame anchor still does the work WITHIN a sheet; this is one scale and one
# vertical offset applied to all nine reaction frames, measured from the silhouettes.
def silhouette(group):
    """Mean mask of a sheet's BODY, symbols excluded, at quarter resolution.

    Only the shoulders, because the fit below scales one sheet onto the other and the hair
    must not get a vote. FIT_BAND has to sit below where hair reaches, not merely below the
    face: at 0.55 the band still caught hair on every long-haired character and the fit kept
    shrinking them. Expression sheets routinely draw hair bushier
    than the direction sheet does; fitting on the whole silhouette then shrinks the frame
    until the hair agrees, and takes the shoulders down with it -- which reads as the body
    shrinking the moment you click. The body is the part that is supposed to be identical,
    so it is the part that decides the fit.
    """
    frames = []
    for frame in group:
        mask = body_mask(np.array(frame)[..., 3] > 100)
        rows = np.where(mask.any(axis=1))[0]
        cut = rows.min() + int((rows.max() - rows.min()) * FIT_BAND)
        body = np.zeros_like(mask)
        body[cut:rows.max() + 1] = mask[cut:rows.max() + 1]
        frames.append(body.astype(np.float32))
    return np.mean(frames, axis=0)[::4, ::4]


# Fit the reactions sheet onto the directions sheet. Every heuristic tried before this
# -- silhouette height, head width -- measures one feature and gets fooled by whatever
# else the expression sheet drew differently: bushier hair, a bigger hat, a wider
# collar. Searching directly for the scale and offset that make the two silhouettes
# overlap best optimises what a viewer actually sees when the boop swaps atlases.
direction_mask = silhouette(direction_frames)
H, Wm = direction_mask.shape


def overlap(other_mask, scale, dy):
    zoomed = ndimage.zoom(other_mask, scale, order=1)
    canvas = np.zeros_like(direction_mask)
    oy = round((H - zoomed.shape[0]) / 2 + dy)
    ox = round((Wm - zoomed.shape[1]) / 2)
    sy, sx = max(0, -oy), max(0, -ox)
    ey = min(zoomed.shape[0], H - oy)
    ex = min(zoomed.shape[1], Wm - ox)
    if ey <= sy or ex <= sx:
        return 0.0
    canvas[oy + sy:oy + ey, ox + sx:ox + ex] = zoomed[sy:ey, sx:ex]
    union = np.maximum(canvas, direction_mask).sum()
    return float(np.minimum(canvas, direction_mask).sum() / max(union, 1e-6))


def fit(group, label):
    """Scale and vertical offset that seat `group` on the directions sheet."""
    other = silhouette(group)
    score, correction, shift_quarter = max(
        ((overlap(other, sc / 1000, dy), sc / 1000, dy)
         for sc in range(1000 - int(MATCH_CLAMP * 1000), 1000 + int(MATCH_CLAMP * 1000) + 1, 5)
         for dy in range(-40, 41)))
    shift = shift_quarter * 4
    print(f'  cross-sheet fit [{label}]  scale {correction:.3f}  '
          f'shift {shift:+d}px  overlap {score*100:.1f}%')
    return correction, shift


def match(frame, correction, shift):
    w, h = frame.size
    scaled = frame.resize((round(w * correction), round(h * correction)), Image.LANCZOS)
    canvas = Image.new('RGBA', (w, h), (0, 0, 0, 0))
    canvas.alpha_composite(scaled, (round((w - scaled.size[0]) / 2),
                                    round((h - scaled.size[1]) / 2) + shift))
    return canvas


def lower_band(frame):
    """Bottom third of the character: shoulders and chest, which carry no expression."""
    mask = body_mask(np.array(frame)[..., 3] > 120)
    rows = np.where(mask.any(axis=1))[0]
    band = np.zeros_like(mask)
    start = rows.min() + int((rows.max() - rows.min()) * 0.66)
    band[start:rows.max() + 1] = mask[start:rows.max() + 1]
    return band


def settle(frame, reference):
    """Slide one reaction frame until its shoulders sit on the directions shoulders.

    The sheet-wide fit above is one correction for all nine frames, so whatever offset
    a single expression carries on top of it survives, and that frame alone twitches
    when the boop lands on it. This removes the remainder per frame. Only the shoulder
    band is matched -- the face is supposed to differ.
    """
    band = lower_band(frame)
    best = (-1.0, 0)
    for dy in range(-SETTLE, SETTLE + 1):
        shifted = np.roll(band, dy, axis=0)
        if dy > 0:
            shifted[:dy] = False
        elif dy < 0:
            shifted[dy:] = False
        union = (shifted | reference).sum()
        best = max(best, ((shifted & reference).sum() / max(union, 1), dy))
    dy = best[1]
    if dy == 0:
        return frame, dy
    canvas = Image.new('RGBA', frame.size, (0, 0, 0, 0))
    canvas.alpha_composite(frame, (0, dy))
    return canvas, dy


reference_band = lower_band(direction_frames[4])


def seat(group, label):
    correction, shift = fit(group, label)
    settled = [settle(match(f, correction, shift), reference_band) for f in group]
    print(f'  per-frame settle [{label}]  {[dy for _, dy in settled]}')
    return [f for f, _ in settled]


reaction_out = seat(reaction_frames, 'reactions')
between_out = seat(between_frames, 'in-between') if between_tiles else []
lower_out = seat(lower_frames, 'lower-arc') if lower_tiles else []
blink_out = seat(blink_frames, 'blink A') if blink_tiles else []
blink_b_out = seat(blink_b_frames, 'blink B') if blink_b_tiles else []
blink_c_out = seat(blink_c_frames, 'blink C') if blink_c_tiles else []
frames = (direction_frames + reaction_out + between_out + lower_out
          + blink_out + blink_b_out + blink_c_out)

top = min(f.getbbox()[1] for f in frames) - 8
left = min(f.getbbox()[0] for f in frames)
right = max(f.getbbox()[2] for f in frames)
# Crop to the WHOLE character, never to the shallowest frame -- letting the vignette
# hide the difference instead dissolved the body along with the cut. Where the fade
# lands is decided per frame below, not here: one shared line either clips deep frames
# or leaves shallow ones with a hard cut above it.
content_bottom = max(f.getbbox()[3] for f in frames)

# Put every character's feet on the same line. Sizing the square from the character
# and starting it at the top instead lets the bottom edge land wherever the head-to-
# body ratio puts it, so a row of mascots sits at a different height each -- which is
# what you see the moment you put them in a grid.
side = max(right - left + 16, round((content_bottom - top) / BOTTOM_ANCHOR))
centre = (left + right) / 2
# Round once and derive the far edges from it: rounding each edge independently can
# make the box a pixel wider than it is tall, and the fade mask then no longer
# matches the cropped frame.
crop_left = round(centre - side / 2)
crop_top = content_bottom - round(BOTTOM_ANCHOR * side)
crop = (crop_left, crop_top, crop_left + side, crop_top + side)
S = side

ys, xs = np.mgrid[0:S, 0:S].astype(np.float32)


def bottom_fade(cropped):
    """Fade ramp for one frame, anchored to where that frame's own body ends.

    The bust is cut off square at the foot of its source cell, so the fade has to land
    ON the body to hide that edge. Anchoring it to the frame rather than to a single
    shared line is what lets every frame keep its whole body AND still end softly: the
    depth stays constant, so the fade reads the same on every mascot, but it follows
    each frame down to wherever that frame actually stops.
    """
    if not VIGNETTE:
        return np.zeros((S, S), dtype=np.float32)
    # Measure against a real alpha threshold: getbbox() counts the faint antialiased
    # halo, which sits below the visible edge and puts the fade past the body, leaving
    # the outline still crisp.
    rows = np.where((np.array(cropped)[..., 3] > 40).any(axis=1))[0]
    end = rows.max() if len(rows) else S
    linear = np.clip((ys - (end - FADE_DEPTH * S)) / (FADE_DEPTH * S), 0, 1)
    return linear * linear * (3 - 2 * linear)


def dissolve(frame):
    stacked = frame.crop(crop)
    if not VIGNETTE:
        return stacked.resize((TILE, TILE), Image.LANCZOS)
    ramp = bottom_fade(stacked)
    for i, radius in enumerate(BLUR_RADII):
        band = np.clip((ramp - i / len(BLUR_RADII)) * len(BLUR_RADII), 0, 1)
        mask = Image.fromarray((band * 255).astype(np.uint8), 'L')
        stacked = Image.composite(blur_premultiplied(stacked, radius), stacked, mask)
    a = np.array(stacked).astype(np.float32)
    a[..., 3] *= 1 - ramp
    return Image.fromarray(a.astype(np.uint8), 'RGBA').resize((TILE, TILE), Image.LANCZOS)


# Build every atlas before replacing anything, then swap them in. Writing straight to
# the live path means an interrupt mid-write leaves a truncated file and the site loses
# a character -- which is exactly what happened once.
import tempfile

def assemble(a_group, b_group, c_group):
    """Lay three sheets into one 6x3 ring. Only the A sheet is required."""
    laid = [None] * (COLS * ROWS)
    for i, frame in enumerate(a_group):
        laid[RING_A[i]] = frame
    if b_group:
        for i, frame in enumerate(b_group):
            laid[RING_B[i]] = frame
    else:
        # No in-between sheet. Point each odd cell at the even one before it so the
        # atlas is still well formed and the component runs at eight effective
        # directions, exactly as upstream does, until sheet B arrives.
        for i in range(1, 16, 2):
            laid[i] = laid[i - 1]
        laid[17] = laid[16]
    # Last, so the arc drawn as one piece wins over the cells A and B put there.
    for i, frame in enumerate(c_group):
        laid[RING_C[i]] = frame
    return laid


ring = assemble(direction_frames, between_out, lower_out)
blink_ring = assemble(blink_out, blink_b_out, blink_c_out) if blink_out else None

# dissolve() is expensive, so a duplicated frame is rendered once and reused.
rendered = {}
def once(frame):
    if id(frame) not in rendered:
        rendered[id(frame)] = dissolve(frame)
    return rendered[id(frame)]

staged = []
outputs = [('directions', ring, COLS), ('reactions', reaction_out, 3)]
if blink_ring:
    outputs.append(('blink', blink_ring, COLS))
for kind, group, cols in outputs:
    rows = len(group) // cols
    atlas = Image.new('RGBA', (TILE * cols, TILE * rows), (0, 0, 0, 0))
    for i, frame in enumerate(group):
        atlas.paste(once(frame), ((i % cols) * TILE, (i // cols) * TILE))
    fd, tmp = tempfile.mkstemp(suffix='.webp', dir=DEST)
    os.close(fd)
    atlas.save(tmp, quality=92, method=6)
    os.chmod(tmp, 0o644)          # mkstemp makes it 0600, which a web server cannot read
    staged.append((tmp, os.path.join(DEST, f'{name}-{kind}.webp'), kind))

for tmp, final, kind in staged:
    os.replace(tmp, final)          # atomic on the same filesystem
    print(f'  {name}-{kind}.webp  {os.path.getsize(final) // 1024} KB  (anchor {mode})')
