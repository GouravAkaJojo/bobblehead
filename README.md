# bobblehead

A character for the top of your page that watches the cursor and reacts when you poke it.

**16 head directions** instead of nine, a spring that keeps it moving between them, idle
breathing, and blinking that works in whatever direction it is already facing.

Reverse-engineered from [nilbuild/page-mascot](https://github.com/nilbuild/page-mascot),
whose art pipeline this builds on. The runtime is rewritten.

| | original | here |
| --- | --- | --- |
| Head directions | 8 sectors, 45 degrees | **16 sectors, 22.5 degrees** |
| Between sectors | frozen | **spring: parallax, yaw, pitch, roll** |
| At rest | frozen | **breathing, and a blink every 4-9s** |
| Blinking | snaps front to blink | **blinks facing wherever it is looking** |
| Reactions reachable | 5 of 9 | **9 of 9** |

## Install

```bash
npm i bobblehead
```

React 18 or newer. Or copy `src/mascot.tsx` into your project: it is one file, needs only
React, and uses inline styles so it drops into any setup without a CSS framework.

## Use

```tsx
import { Mascot } from 'bobblehead'

<Mascot
  directions="/mascots/me-directions.webp"
  reactions="/mascots/me-reactions.webp"
  blink="/mascots/me-blink.webp"
  size={160}
  label="Cola"
/>
```

| prop | type | default | |
| --- | --- | --- | --- |
| `directions` | `string` | required | the 6x3 sheet of head angles |
| `reactions` | `string` | required | the 3x3 sheet of expressions |
| `blink` | `string` | — | the 6x3 eyes-shut ring. Without it, blinking falls back to the front-facing expressions sheet |
| `size` | `number` | `140` | rendered width and height in px |
| `label` | `string` | `'mascot'` | what a screen reader calls it |
| `className` | `string` | — | applied to the button |
| `idle` | `boolean` | `true` | breathing and idle blinking |

Put it where a head watching the cursor reads best, usually the header or hero, above or
beside the title.

### Behaviour

Cursor tracking is desktop only, gated on `(hover: hover) and (pointer: fine)`. On touch
the mascot renders and stays clickable, it just does not follow anything.

Under `prefers-reduced-motion` the spring, breathing, idle blinking and the click squash
all drop out. The head still turns.

The render loop stops when the mascot scrolls out of view or the tab is hidden, and a
head turn never goes through a React render.

## Reactions

| reaction | trigger |
| --- | --- |
| `heart` `sparkle` `delighted` `wink` `bashful` | click, advancing one per click |
| `dizzy` | four clicks within 1.6s |
| `surprised` | the pointer rushing into a 160px radius at over 1200px/s |
| `sleepy` | the pointer completely still for 12s, clears on the next movement |
| `blink` | the first 120ms of a click, and idle blinking when no `blink` sheet is given |

Reactions hold for 2.5s and come off the front-facing expressions sheet, so the head does
face the viewer while one is showing. Idle blinking is the exception and uses the blink
ring, so it keeps tracking with its eyes shut.

## The sheets

**Directions** are a 6x3 ring. Cells 0-15 are head angles clockwise from east, 16 is the
resting pose used inside the dead zone, 17 is padding. The cell index is just the rounded
angle, so there is no lookup table:

```
cell = round(atan2(dy, dx) / (2 * PI / 16)) mod 16
```

**Blink** is a 6x3 ring matching it cell for cell, with the eyes shut.

**Expressions** are a 3x3 sheet of nine, in the order `blink, heart, sparkle, surprised,
wink, bashful, sleepy, dizzy, delighted`.

## Making your own character

Needs Python 3 and an `OPENAI_API_KEY`.

```bash
python3 -m venv .venv && .venv/bin/pip install pillow numpy scipy openai
export OPENAI_API_KEY=sk-...

.venv/bin/python scripts/mascot.py me --reference ~/photo.jpg \
  --describe "short dark hair, a trimmed beard, black round glasses, a navy tee"
```

That runs generate, screen, build and verify, retrying the sheet that failed. Then:

```bash
.venv/bin/python scripts/mascot.py me --only lower    # the downward arc
.venv/bin/python scripts/mascot.py me --only blink    # the eyes-shut ring
```

Built atlases land in `public/mascots/`. Source sheets stay in `characters/<name>/` so a
character can be rebuilt without redrawing it.

**Describing the character matters more than anything else here.** Name the colours and
two or three distinguishing features in one sentence. Avoid long loose hair over the
shoulders: it gets drawn differently in each sheet and the mascot lurches when clicked.
Tied back or under a hat is safe.

### Styles

`--style colour` (default), `anime`, `jjba`, `ink`, `sketch`, `riso`, `paper`, `pixel`.

A style changes only how the character is drawn. The framing, the head-to-shoulder
proportions and the one reused body stay fixed, because the alignment depends on them.

### Source sheets

| file | |
| --- | --- |
| `directions.png` | 3x3, eight primary angles plus centre |
| `directions-b.png` | 3x3, the eight in-between angles (optional) |
| `directions-c.png` | 3x3, the lower arc with a real downward tilt (optional) |
| `directions-blink.png`, `-b-blink`, `-c-blink` | the same sheets with eyes shut (optional) |
| `reactions.png` | 3x3, nine expressions |

Only `directions.png` and `reactions.png` are required. Without `directions-b.png` the
build fills the odd cells from the even ones and the mascot runs at eight directions.

### Checking a character

```bash
.venv/bin/python scripts/verify.py me   # does it move or change size when clicked
.venv/bin/python scripts/ring.py me     # is any pose in the wrong cell
```

`verify.py` refuses more than **2px** of shift on click, a palette match below **22%**
between the two sheets, or a shoulder-width change above **12%**, and reports blink-ring
drift. Most characters land well inside all three: under 1px, 45-86%, and under 8%.

`ring.py` catches a correct drawing sitting in the wrong cell, which every other check
scores as perfect. Read its **ordering**, not its angles, and trust your eyes over both.

### Trying it without art

```bash
.venv/bin/python scripts/testsheet.py --source
.venv/bin/python scripts/mascot.py test --skip-generate
npm run dev
```

`testsheet.py` draws a crude 16-angle character so the atlas geometry and the spring can
be exercised without spending image credits.

## Notes

[NOTES.md](NOTES.md) covers why it is built this way: what blending does to a sprite
sheet and why frames are cut instead, why the downward arc needs its own sheet, why
blinking needs its own ring, and which measurements catch which failures.

## Credit

The art pipeline, the sprite-sheet approach and the prompt engineering behind it are from
[nilbuild/page-mascot](https://github.com/nilbuild/page-mascot).
