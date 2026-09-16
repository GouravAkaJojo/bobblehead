import { useEffect, useRef, useState } from 'react'
import type { CSSProperties } from 'react'

/**
 * Sixteen head directions on a 6x3 atlas: cells 0..15 are the directions,
 * clockwise from east, and cell 16 is the resting pose used inside the dead
 * zone. Cell 17 is padding so the sheet stays a clean grid.
 *
 * Clockwise from east matches atan2 with y pointing down, so the cell index is
 * just the rounded angle and needs no lookup table.
 */
const COLS = 6
const DIRECTIONS = 16
const CENTER = 16

const SECTOR = (Math.PI * 2) / DIRECTIONS
/** Proportional to the upstream 0.12 at 45 degrees, so the feel carries over. */
const HYSTERESIS = 0.06
const DEAD_ZONE = 70

/** How far the cursor travels before the tilt is at full strength. */
const TILT_RANGE = 420
const SHIFT_X = 5
const SHIFT_Y = 4
const YAW = 7
const PITCH = 5
const ROLL = 3
const PERSPECTIVE = 600

/** Semi-implicit spring. Critically damped enough to settle without ringing. */
const STIFFNESS = 90
const DAMPING = 14
const MAX_STEP = 1 / 30
const SETTLED = 0.0005

const BREATH_PERIOD = 4200
const BREATH_AMOUNT = 0.012

const REACTIONS = [
  'blink',
  'heart',
  'sparkle',
  'surprised',
  'wink',
  'bashful',
  'sleepy',
  'dizzy',
  'delighted',
] as const

type Reaction = (typeof REACTIONS)[number]

/** How long a reaction holds once it has landed. */
const REACTION_HOLD = 2500

/**
 * The boop rotation. It advances on EVERY click, not with the rapid-click
 * counter that drives dizzy, because that counter resets after DIZZY_WINDOW and
 * anyone clicking at a normal pace would otherwise see nothing but the first
 * entry forever.
 */
const PAYOFFS: Reaction[] = ['heart', 'sparkle', 'delighted', 'wink', 'bashful']
const BOOP_PAYOFF = 120
const BOOP_END = BOOP_PAYOFF + REACTION_HOLD
const SQUASH_MS = 420
const DIZZY_AFTER = 4
const DIZZY_WINDOW = 1600
const DIZZY_END = REACTION_HOLD

/** Startled by something rushing into its personal space. */
const STARTLE_RADIUS = 160
const STARTLE_SPEED = 1200
const STARTLE_COOLDOWN = 7000

/** Dozes off after this long with the pointer completely still. */
const DOZE_AFTER = 12000

const BLINK_MIN = 4000
const BLINK_MAX = 9000
const BLINK_MS = 130

const SQUASH: Keyframe[] = [
  { transform: 'scale(1, 1)', easing: 'ease-in' },
  { transform: 'scale(1.10, 0.86)', offset: 0.18, easing: 'ease-out' },
  { transform: 'scale(0.95, 1.08)', offset: 0.45, easing: 'ease-in-out' },
  { transform: 'scale(1.03, 0.97)', offset: 0.72, easing: 'ease-in-out' },
  { transform: 'scale(1, 1)' },
]

function wrap(angle: number) {
  return Math.atan2(Math.sin(angle), Math.cos(angle))
}

function clamp(value: number, low: number, high: number) {
  return value < low ? low : value > high ? high : value
}

type Face = { sheet: 'directions' | 'reactions' | 'blink'; cell: number }

export type MascotProps = {
  /** The 6x3 sheet of head directions. A served path, or an imported image. */
  directions: string
  /** The 3x3 sheet of expressions. */
  reactions: string
  /**
   * Optional 6x3 sheet matching `directions`, drawn with the eyes shut.
   *
   * Without it an idle blink has to come off the expressions sheet, which faces
   * front in every cell, so a mascot watching the cursor snaps its head straight
   * to blink and then back. With it the blink keeps whatever direction the head
   * is already in, and keeps tracking while the eyes are closed.
   */
  blink?: string
  size?: number
  className?: string
  /** What a screen reader calls it. */
  label?: string
  /** Breathing and idle blinking. Off leaves cursor tracking untouched. */
  idle?: boolean
}

export function Mascot(props: MascotProps) {
  const { directions, reactions, size = 140, className, label = "mascot", idle = true, blink } = props;

  const buttonRef = useRef<HTMLButtonElement>(null);
  const squashRef = useRef<HTMLSpanElement>(null);
  const tiltRef = useRef<HTMLSpanElement>(null);
  const canvasRef = useRef<HTMLCanvasElement>(null);
  const timersRef = useRef<number[]>([]);
  const boopsRef = useRef({ count: 0, at: 0, turn: 0 });
  const fireRef = useRef<((next: Reaction | null, hold: number) => void) | null>(null);

  // Bridges between React state and the canvas loop. Declared before the loop
  // that closes over them so the wiring reads in the order it runs.
  const renderRef = useRef<(() => void) | null>(null);
  const reactionRef = useRef<Reaction | null>(null);
  const blinkingRef = useRef(false);
  const restRef = useRef<number>(CENTER);

  const sheetsRef = useRef<{
    directions?: HTMLImageElement
    reactions?: HTMLImageElement
    blink?: HTMLImageElement
  }>({});
  /**
   * The single cell on screen. Upstream blends nothing at all: its only
   * animate() is the click squash, and its two layers swap opacity with no
   * transition, so a head turn is a plain background-position jump.
   *
   * Two attempts at blending here both failed, in opposite directions. Crossing
   * two CSS layers' opacities composites source-over, so the character's alpha
   * dipped to about 0.78 and it flickered translucent on every turn. Dissolving
   * on a canvas out of a snapshot fixed that and smeared instead: each snapshot
   * caught a partial blend, the next dissolve started from it, and a circling
   * cursor averaged every pose it passed into a cloud. A cut cannot do either.
   *
   * What carries the smoothness is the other two changes: sixteen directions
   * rather than nine, which halves the step to 22.5 degrees, and the tilt spring
   * below, which keeps the character moving continuously between the steps.
   */
  const viewRef = useRef<{ face: Face; dirty: boolean }>({
    face: { sheet: "directions", cell: CENTER },
    dirty: true,
  });

  const [reaction, setReaction] = useState<Reaction | null>(null);
  const [blinking, setBlinking] = useState(false);

  const reduced = typeof window !== "undefined" && window.matchMedia("(prefers-reduced-motion: reduce)").matches;

  // Decode both sheets up front so the first turn and the first boop never wait.
  useEffect(() => {
    let live = true;
    const load = (src: string, key: "directions" | "reactions" | "blink") => {
      const img = new Image();
      img.decoding = "async";
      img.src = src;
      const ready = () => {
        if (live) {
          sheetsRef.current[key] = img;
          viewRef.current.dirty = true;
        }
      };
      if (img.complete) {
        ready();
      } else {
        img.addEventListener("load", ready, { once: true });
      }
    };
    load(directions, "directions");
    load(reactions, "reactions");
    if (blink) {
      load(blink, "blink");
    }
    return () => {
      live = false;
    };
  }, [directions, reactions, blink]);

  useEffect(() => {
    const canvas = canvasRef.current;
    if (!canvas) {
      return;
    }
    const context = canvas.getContext("2d");
    if (!context) {
      return;
    }

    let sector = -1;
    let pointer: { x: number; y: number } | null = null;
    let movedAt = performance.now();
    let startledAt = 0;
    let dozing = false;

    // Spring state for the continuous tilt, in normalised -1..1 cursor space.
    let nx = 0;
    let ny = 0;
    let vx = 0;
    let vy = 0;
    let targetX = 0;
    let targetY = 0;

    let frame = 0;
    let last = performance.now();
    let visible = true;
    const started = last;

    const pixels = () => {
      const dpr = Math.min(window.devicePixelRatio || 1, 3);
      return Math.max(1, Math.round(size * dpr));
    };

    const show = (face: Face) => {
      const view = viewRef.current;
      if (view.face.sheet === face.sheet && view.face.cell === face.cell) {
        return;
      }
      view.face = face;
      view.dirty = true;
    };
    /** The frame the current state calls for, at the direction last aimed at. */
    const resolve = (): Face => {
      const active = reactionRef.current;
      if (active) {
        return { sheet: "reactions", cell: REACTIONS.indexOf(active) };
      }
      if (blinkingRef.current) {
        // Without a blink ring this falls back to the front-facing expressions
        // sheet, which is upstream's behaviour and snaps the head straight.
        return sheetsRef.current.blink
          ? { sheet: "blink", cell: restRef.current }
          : { sheet: "reactions", cell: REACTIONS.indexOf("blink") };
      }
      return { sheet: "directions", cell: restRef.current };
    };
    const render = () => show(resolve());
    renderRef.current = render;

    const paint = () => {
      const view = viewRef.current;
      const side = pixels();
      if (canvas.width !== side) {
        canvas.width = side;
        canvas.height = side;
        view.dirty = true;
      }
      if (!view.dirty) {
        return;
      }

      const face = view.face;
      const img = sheetsRef.current[face.sheet];
      if (!img || !img.naturalWidth) {
        return;
      }
      view.dirty = false;

      // The blink ring shares the directions layout; only expressions are 3x3.
      const cols = face.sheet === "reactions" ? 3 : COLS;
      const tile = img.naturalWidth / cols;
      context.clearRect(0, 0, side, side);
      context.imageSmoothingQuality = "high";
      context.drawImage(img, (face.cell % cols) * tile, Math.floor(face.cell / cols) * tile, tile, tile, 0, 0, side, side);
    };

    const aim = () => {
      const button = buttonRef.current;
      if (!button || !pointer) {
        return;
      }

      const box = button.getBoundingClientRect();
      const dx = pointer.x - (box.left + box.width / 2);
      const dy = pointer.y - (box.top + box.height / 2);

      targetX = clamp(dx / TILT_RANGE, -1, 1);
      targetY = clamp(dy / TILT_RANGE, -1, 1);

      let next: number;
      if (Math.hypot(dx, dy) < DEAD_ZONE) {
        sector = -1;
        next = CENTER;
      } else {
        // Hold the current sector until the pointer is well past its edge.
        const angle = Math.atan2(dy, dx);
        if (sector !== -1 && Math.abs(wrap(angle - sector * SECTOR)) < SECTOR / 2 + HYSTERESIS) {
          return;
        }
        sector = (Math.round(angle / SECTOR) + DIRECTIONS) % DIRECTIONS;
        next = sector;
      }

      // Straight to the canvas: a turn never goes through a React render. The
      // blink ring is aimed too, so the head keeps following while eyes are shut.
      restRef.current = next;
      render();
    };

    const onPointerMove = (event: PointerEvent) => {
      const now = performance.now();
      const previous = pointer;
      const since = (now - movedAt) / 1000;
      pointer = { x: event.clientX, y: event.clientY };
      movedAt = now;

      if (dozing && reactionRef.current === "sleepy") {
        fireRef.current?.(null, 0);
      }

      // Startle on CLOSING SPEED rather than plain proximity, so drifting slowly
      // across the mascot never sets it off and only a rush at it does.
      const button = buttonRef.current;
      if (button && previous && since > 0 && !reactionRef.current && now - startledAt > STARTLE_COOLDOWN) {
        const box = button.getBoundingClientRect();
        const mx = box.left + box.width / 2;
        const my = box.top + box.height / 2;
        const was = Math.hypot(previous.x - mx, previous.y - my);
        const is = Math.hypot(pointer.x - mx, pointer.y - my);
        if (is < STARTLE_RADIUS && (was - is) / Math.max(since, 1 / 240) > STARTLE_SPEED) {
          startledAt = now;
          fireRef.current?.("surprised", REACTION_HOLD);
        }
      }

      aim();
    };

    const tick = (now: number) => {
      frame = requestAnimationFrame(tick);
      const dt = Math.min((now - last) / 1000, MAX_STEP);
      last = now;

      if (!visible) {
        return;
      }

      paint();

      // Doze off when the pointer has been still a long while. Held with no
      // timer, so it lasts until something actually wakes the character.
      if (dozing && reactionRef.current !== "sleepy") {
        dozing = false;
      }
      // A boop is attention, so hold the doze clock while one is on screen.
      // Without this the character falls straight back asleep the instant a
      // reaction clears, because the pointer still has not moved.
      if (reactionRef.current && reactionRef.current !== "sleepy") {
        movedAt = now;
      }
      if (idle && !reduced && !dozing && !reactionRef.current && now - movedAt > DOZE_AFTER) {
        dozing = true;
        fireRef.current?.("sleepy", 0);
      }

      if (reduced) {
        return;
      }

      vx += (targetX - nx) * STIFFNESS * dt;
      vy += (targetY - ny) * STIFFNESS * dt;
      const decay = Math.exp(-DAMPING * dt);
      vx *= decay;
      vy *= decay;
      nx += vx * dt;
      ny += vy * dt;

      const breath = idle ? Math.sin(((now - started) / BREATH_PERIOD) * Math.PI * 2) * BREATH_AMOUNT : 0;

      const node = tiltRef.current;
      if (!node) {
        return;
      }

      const settled = Math.abs(vx) + Math.abs(vy) + Math.abs(targetX - nx) + Math.abs(targetY - ny);
      if (settled < SETTLED && breath === 0) {
        return;
      }

      node.style.transform =
        `perspective(${PERSPECTIVE}px) ` +
        `translate3d(${(nx * SHIFT_X).toFixed(2)}px, ${(ny * SHIFT_Y + breath * -6).toFixed(2)}px, 0) ` +
        `rotateY(${(nx * YAW).toFixed(2)}deg) ` +
        `rotateX(${(-ny * PITCH).toFixed(2)}deg) ` +
        `rotateZ(${(nx * ROLL).toFixed(2)}deg) ` +
        `scaleY(${(1 + breath).toFixed(4)})`;
    };

    const tracks = window.matchMedia("(hover: hover) and (pointer: fine)").matches;

    // Stop the loop when the mascot is scrolled away or the tab is hidden.
    const observer = new IntersectionObserver(
      ([entry]) => {
        visible = entry.isIntersecting && !document.hidden;
      },
      { threshold: 0 },
    );
    observer.observe(canvas);
    const onVisibility = () => {
      visible = !document.hidden;
      last = performance.now();
    };

    frame = requestAnimationFrame(tick);
    if (tracks) {
      window.addEventListener("pointermove", onPointerMove, { passive: true });
      window.addEventListener("scroll", aim, { passive: true });
    }
    document.addEventListener("visibilitychange", onVisibility);

    return () => {
      cancelAnimationFrame(frame);
      observer.disconnect();
      window.removeEventListener("pointermove", onPointerMove);
      window.removeEventListener("scroll", aim);
      document.removeEventListener("visibilitychange", onVisibility);
      renderRef.current = null;
    };
  }, [idle, reduced, size, blink]);

  reactionRef.current = reaction;
  blinkingRef.current = blinking;

  useEffect(() => {
    renderRef.current?.();
  }, [reaction, blinking]);

  // Idle blinking, paused while a boop reaction is on screen.
  //
  // The timer reschedules itself rather than keying off `blinking`. With
  // `blinking` in the dependency list the effect tears down the moment the eyes
  // shut, and the cleanup cancels the very timer that reopens them, leaving the
  // mascot blinking for a whole interval at a time.
  useEffect(() => {
    if (!idle || reduced || reaction) {
      return;
    }
    let live = true;
    let shut = 0;
    let open = 0;
    const schedule = () => {
      shut = window.setTimeout(
        () => {
          if (!live) {
            return;
          }
          setBlinking(true);
          open = window.setTimeout(() => {
            if (!live) {
              return;
            }
            setBlinking(false);
            schedule();
          }, BLINK_MS);
        },
        BLINK_MIN + Math.random() * (BLINK_MAX - BLINK_MIN),
      );
    };
    schedule();
    return () => {
      live = false;
      window.clearTimeout(shut);
      window.clearTimeout(open);
    };
  }, [idle, reduced, reaction]);

  useEffect(() => {
    return () => {
      timersRef.current.forEach(window.clearTimeout);
    };
  }, []);

  // Lets the pointer loop in the canvas effect raise a reaction of its own.
  fireRef.current = (next: Reaction | null, hold: number) => {
    timersRef.current.forEach(window.clearTimeout);
    timersRef.current = [];
    if (next) {
      setBlinking(false);
    }
    setReaction(next);
    if (next && hold > 0) {
      timersRef.current.push(window.setTimeout(() => setReaction(null), hold));
    }
  };

  const boop = () => {
    timersRef.current.forEach(window.clearTimeout);
    timersRef.current = [];
    setBlinking(false);

    const later = (ms: number, next: Reaction | null) => {
      timersRef.current.push(window.setTimeout(() => setReaction(next), ms));
    };

    const now = Date.now();
    const boops = boopsRef.current;
    boops.count = now - boops.at < DIZZY_WINDOW ? boops.count + 1 : 1;
    boops.at = now;

    if (boops.count >= DIZZY_AFTER) {
      boops.count = 0;
      setReaction("dizzy");
      later(DIZZY_END, null);
    } else {
      setReaction("blink");
      later(BOOP_PAYOFF, PAYOFFS[boops.turn % PAYOFFS.length]);
      boops.turn += 1;
      later(BOOP_END, null);
    }

    if (reduced) {
      return;
    }

    // Per-keyframe easing with the effect itself linear: an easing on the effect
    // would reinterpret every offset and front-load the whole bounce.
    squashRef.current?.animate(SQUASH, { duration: SQUASH_MS, easing: "linear" });
  };

  const fill: CSSProperties = { display: "block", width: "100%", height: "100%" };

  // Inline styles so the file drops into any project without a CSS framework.
  return (
    <button
      ref={buttonRef}
      type="button"
      onClick={boop}
      aria-label={`Boop the ${label}`}
      className={className}
      style={{
        position: "relative",
        display: "block",
        flexShrink: 0,
        width: size,
        height: size,
        padding: 0,
        border: 0,
        background: "transparent",
        appearance: "none",
        cursor: "pointer",
        userSelect: "none",
      }}
    >
      <span ref={squashRef} style={{ ...fill, position: "relative", transformOrigin: "50% 78%" }}>
        <span
          ref={tiltRef}
          style={{
            position: "absolute",
            inset: 0,
            transformOrigin: "50% 70%",
            willChange: "transform",
          }}
        >
          <canvas ref={canvasRef} style={fill} />
        </span>
      </span>
    </button>
  );
}