# Motion and video visual system

Use motion only when time or transition is data. The goal is explanatory compression, not
attention capture.

## Contents

- Admission test and motion grammars
- VisualSpec/RenderSpec contract
- Story, frame, typography, and technical rules
- Companion artifacts, integrity, and rejection conditions

## Motion admission test

Render motion only when all answers are yes:

1. Does order, movement, accumulation, or transition change the interpretation?
2. Are there at least three meaningful states?
3. Would a static overview or small multiples hide a material pattern?
4. Can the sequence be understood without audio?
5. Can a useful poster and final frame be generated?

Score motion using `decision-engine.md`. Require a score at least 15 points above the best
static option.

## Spec contract

Let `VisualSpec` justify the video modality and select the canonical `sequence-replay`
grammar. Explicitly compile it into `RenderSpec.kind = sequence` with source-bound frames,
timestamps, labels, values, coordinates, and final answer. Bind each frame member or series
path; do not bind only a generic sequence label.

The motion renderer may interpolate presentation geometry only when the declared grammar and
data model permit it. It must not invent intermediate measurements or infer frame values.

## Supported motion patterns

| VisualIntent | Sequence-replay pattern |
| --- | --- |
| `distance_route` | draw path over time; preserve start, direction, and end |
| `threshold_distance` | hold context, animate value to boundary, mark crossing, hold result |
| `timeline` | reveal events in actual order with stable time scale |
| `composition` | grow total/parts while preserving the final comparative frame |
| `geo_location` + supplied sequence | update supplied regions on a fixed map extent |
| `before_after` | locked camera and scale, then direct comparison |
| `ranking` | animate position only when rank transitions are the evidence |

Do not animate static KPI tiles, decorative backgrounds, logos, or severity rails.

## Story structure

Target 6–12 seconds:

1. **Context, 0–1.5 s:** title, subject, scale, starting state.
2. **Change, 1.5–8 s:** one continuous data-driven transition.
3. **Takeaway, final 1.5–2 s:** final state, supplied conclusion, time/source.

Show meaningful content within 0.5 seconds. Avoid logo intros. Freeze long enough at the end
for a screenshot to remain useful.

## Frame and transition rules

- Keep axes, map extents, and object positions stable unless camera movement conveys scale.
- Use linear time for temporal evidence unless a time jump is labeled.
- Keep data values attached to their objects.
- Use restrained easing for presentation, never to distort timing or magnitude.
- Use cuts for categorical changes and interpolation for continuous changes.
- Mark skipped periods and missing frames.
- Keep one dominant moving relationship per scene.
- Do not flash faster than three times per second.

## Typography

- Apply the same mobile type minimums as `image-visuals.md`.
- Keep text on screen long enough to read silently.
- Use concise labels; move method and long evidence to the caption or final frame.
- Burn in only essential captions; provide the primary answer as Telegram text as well.

## Technical baseline

Prefer a broadly compatible MP4:

```text
codec: H.264
pixel format: yuv420p
frame rate: 24 or 30 fps
dimensions: even-numbered pixels
fast start: enabled
audio: optional; never required for comprehension
```

Use `1200×675` landscape or `1080×1080` square unless the source geometry requires another
format. Keep critical content in a 6% safe area.

Use GIF/animation only for short, low-color, loop-safe sequences. Prefer MP4 for charts,
maps, gradients, and text because compression and legibility are generally better.

## Required companion artifacts

Generate:

- poster frame containing title and starting context
- final frame containing the answer
- static fallback summarizing the entire sequence
- native-text accessible summary

The fallback must be selected intentionally, not an arbitrary video thumbnail.

## Integrity rules

- Interpolate only where the data model permits; otherwise use discrete steps.
- Do not invent intermediate measurements.
- Do not accelerate or slow time without labeling the mapping.
- Keep axes/domains fixed across comparable frames.
- Preserve uncertainty through the sequence.
- Never add urgency, causality, or recommendation through sound, speed, or color.

## Rejection conditions

Reject motion when:

- the final frame contains the whole answer
- the sequence consists only of text fades
- playback is needed to discover a basic number
- there is no static fallback
- the output becomes unreadable after Telegram compression
- motion exists solely for branding or novelty
