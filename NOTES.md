# Notes

Why this is built the way it is. [README.md](README.md) covers how to use it.

Everything here was arrived at by measuring something that looked fine and was not.

---

## Frames are cut, not blended

Upstream blends nothing. Its only `animate()` is the click squash, its two layers swap
opacity with no transition, and a head turn is a plain `background-position` jump. That is
the right call, and it took two failed attempts here to understand why.

### Crossing two CSS layers' opacities does not cross-dissolve

Stacking composites source-over. With the layers at 0.32 and 0.68 the character's own
alpha comes out at `0.32 + 0.68 * (1 - 0.32)`, about **0.78**. The two opacities sum to 1
and the mascot still goes translucent, pulsing once per turn. Measured on the page mid
turn, the count of fully opaque pixels collapsed to zero.

### Dissolving on a canvas fixed the pulse and smeared instead

A canvas can cross-dissolve properly: draw the outgoing frame at `1 - t`, then the
incoming at `t` with `globalCompositeOperation = 'lighter'`, which adds premultiplied
colour *and* alpha, so the interior holds alpha 1. That worked.

What did not work was how an interrupted turn was handled. To avoid a pop, it dissolved
out of a *snapshot of the canvas*. Every snapshot taken mid-dissolve captures a blend, and
the next dissolve then starts from it. A cursor circling the mascot changes direction
faster than a dissolve finishes, so each pose was averaged into the last and the character
smeared into a cloud that never resolved while the cursor kept moving.

Constraining it to two real frames bounded the smear but still blended on every turn.

### What actually carries the smoothness

Sixteen directions rather than nine, which halves the angular step to 22.5 degrees, and
the tilt spring, which keeps the character moving continuously between the steps. Blending
was never load-bearing. A cut cannot pulse and cannot smear.

### Measure sharpness, not just alpha

The smear survived a full pass of alpha checks, because a smear keeps its alpha perfectly.
It is opaque. It just has no edges left.

Mean luminance gradient over the opaque pixels is what catches it:

| | sharpness | semi-transparent pixels |
| --- | --- | --- |
| One crisp cell | 100% | baseline |
| Two-cell blend | 79% | +82% |
| Eight-pose smear | 52% | +82% |
| Cutting, circling the cursor | **100%** | **+1.8%** |

Anything that can go wrong with a frame change needs both numbers. Alpha catches a
translucency dip, sharpness catches a smear, and neither sees the other.

---

## Blinking needs its own ring

The expressions sheet faces front in all nine cells. Upstream only shows it on a click,
where snapping the head straight reads as part of the boop. An *idle* blink is different:
a mascot watching the cursor snaps front, blinks, and snaps back, several times a minute.

So there is a second 6x3 ring with the eyes shut. A blink swaps sheet at the same cell
index, so the head cannot move, and aiming still writes through while the eyes are closed,
so it keeps tracking mid-blink.

The three blink sheets are asked for as **edits**, not fresh drawings. The model is handed
a finished direction sheet and told to change one thing. Asking for sixteen head angles
again and hoping they land in the same places is far less reliable than handing over poses
that are already correct and already aligned.

They are built in the same pass as the open ring, never separately, so every blink frame
is normalised against the same anchors. `verify.py` reports the worst per-cell drift
between the two rings, against a 2px limit.

---

## Why the lower arc is drawn separately

Asked for nine directions at once, the model turns the head sideways for "down-left" and
"down-right" and forgets the tilt entirely. Measured on a real character, sheet A's
down-left came back all but identical to its plain left, and down-right to plain right, so
the whole bottom of the ring collapsed onto the two horizontal poses and the mascot
stopped tracking below itself.

Naming the tilt does not fix it, because "looking down" reads as an eye movement. What
works is specifying the geometry that changes when a head really drops, so the sheet asks
for what becomes *visible* rather than for a direction:

- more of the top of the head and hair shows, filling more of the cell
- the forehead looks larger and the chin is foreshortened, tucked toward the chest
- the brows and eyes sit lower in the face
- the ears sit higher than the eyes and the jawline shortens

Sheet C draws that whole arc in one go, east through south to west, with the three
headings that already work (3, 6 and 9 o'clock) included purely as calibration so the
model can see the sweep has to pass smoothly between them. Those three are not used in the
atlas. The build takes cells 0 to 8 from sheet C so the tilt progression is consistent
across the arc, rather than stitched from two sheets that disagree about how far down
"down" is.

## Why the in-between sheet is phrased as clock hours

The first version asked for the angles "halfway between" the ones in the attached sheet.
With sheet A attached as a reference, the model reproduced sheet A's own eight angles
exactly: the grid it can see beats an instruction to interpolate between its cells.

The eight odd clock hours (1, 2, 4, 5, 7, 8, 10, 11) are concrete headings, and because
none of them is 12, 3, 6 or 9, the framing excludes sheet A's angles by construction
rather than by asking.

## Why two 3x3 sheets and not one 4x4

The image API caps a square image at 1024x1024. Sixteen cells there leaves 256px each,
soft once the build normalises and crops. Two 3x3 sheets keep the full 341px per cell, and
the cross-sheet fit that already seats the expressions sheet seats sheet B too, using the
shoulders only (`FIT_BAND`) so a head turn does not drag the scale.

---

## Styles fight the pipeline in predictable ways

A style is supposed to change only the rendering. Two things kept leaking past that.

**The restyle sentence was hardcoded.** The reference prompt told the model to restyle a
photo into "round friendly eyes, soft cheek blush, children's sticker" whatever the style,
which fights any sharp or severe look and makes every character resemble every other one.
That sentence now comes from a per-style `RESTYLE` map. What the build actually requires,
the head dominating the shoulders, stays hardcoded and separate.

**Detailed styles fill the frame and re-pose the body.** A dramatic style draws a
full-bleed portrait bust with shoulders that turn with the head, which is the single most
load-bearing thing the build cannot tolerate. The fix is to demand the simplest possible
body, one plain shape copied identically across cells, and to state the framing
quantitatively rather than as an adjective.

---

## Reading the checks

### `ring.py` detects order, not angle

It exists for the one defect everything else is blind to: a correct drawing in the wrong
cell. Shift, palette, width and overlap all read perfect when every pose is right and only
the ORDER is wrong, which is how upstream shipped a mirrored character.

It works because the face is lighter and warmer than the hair around it, so the skin
centroid's offset from the head centroid points where the head is turned. Two details
matter: the offset is taken as each cell's deviation from the sheet's **mean** pose,
because the face always sits below the hair and that constant otherwise swamps the turn,
and each axis is normalised by its own spread, because a head turns further horizontally
than it nods.

Which is also its limit. **Read the ordering, not the angles.** Adding sheet C genuinely
moved the mean downward across nine of sixteen cells, and every reported angle shifted with
it even though the art had plainly improved. It is a detector for poses in the wrong slot,
not a protractor. Watch `non-monotonic steps`, which are places where the head turns
backwards as the cursor sweeps forwards. When it disagrees with your eyes, trust your eyes,
and check the arc as a strip in cursor-sweep order.

### `screen.py` measures the character, not the cell

The shoulder band is taken upward from the lowest opaque pixel. A single stray speck below
the bust drags that band off the body and the width collapses to the speck. A detailed
style throws off plenty of specks: one sheet measured 103% spread on widths of
`[256, 257, 255, 73, 62, 70, 264, 263, 264]`, where the three odd ones were flecks rather
than shoulders. Cleaned to the largest connected component, the same sheet measured 3.9%.

It now measures on that largest component, matching what the build itself uses, which is
what makes it a prediction of the build rather than a lottery. Blob count and edge contact
still look at the raw mask, because a speck touching an edge is a real bleed signal.
