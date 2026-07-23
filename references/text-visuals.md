# Text visual system

Use native Telegram text when typography and structure are sufficient. Text is not a
fallback-quality medium; for short conclusions and structured reports it is often the most
legible, accessible, searchable, and robust choice.

## Contents

- Regular versus Rich Message selection
- VisualSpec/RenderSpec contract
- Information order and recipes
- Typography and density
- Captions and content integrity

## Choose regular versus rich text

Use regular HTML/Markdown text for:

- one conclusion plus up to five facts
- confirmations, status summaries, and short deltas
- environments that have not verified Rich Message support
- the final fallback for every other medium

Use official Telegram Rich Message structures only when the runtime gate in
`telegram-10.2.md` passes. Then use them for:

- reports with sections or evidence tiers
- tables whose columns remain readable on a phone
- formulas, references, footnotes, or preformatted snippets
- details that should be collapsed by default
- native map, collage, slideshow, image, video, or audio blocks

See `telegram-10.2.md` for feature gates and official limits.

## Spec contract

Let `VisualSpec` select the text modality and either
`verdict-key-values`, `rich-digest`, `html-digest`, or `native-location`. Pass `VisualSpec`
directly to the text compiler/adapter, which emits a Rich Message representation and an HTML
fallback. The text path does not create or consume `RenderSpec`.

Preserve every fact's `VisualSpec.evidence.source_path` in structured rows/metadata. Build
headings and answer copy from declared semantics and evidence. The text adapter must not
search for similar keys, extract unbound numbers from prose, or invent missing copy.
`VisualSpec` keeps the complete evidence contract; first-viewport density is a rendering
choice, not permission to discard provenance. When one Telegram text budget cannot contain
the complete fallback, use the ordered continuations returned by
`render_html_fallback_parts()` / `render_message()` and preserve every fact.

## Information order

Write in this order:

1. **Headline:** subject plus supplied conclusion/state.
2. **Primary line:** one value, delta, or relationship.
3. **Evidence:** two to five facts, a compact table, or a short timeline.
4. **Context:** timestamp, unit, method, uncertainty, and source.

Do not begin with provenance, system labels, or long setup text. Do not repeat the headline
as the first evidence line.

## Regular text recipes

### State

```text
<b>{subject}: {state}</b>
{primary value} · {short context}
{timestamp} · {source}
```

### Change

```text
<b>{subject}: {current}</b>
{previous} → {current}  ({signed delta})
Window: {comparison window}
Source: {source} · {observation time}
```

### Compact comparison

```text
<b>{question answered in one line}</b>
1. {subject A}  {value}
2. {subject B}  {value}
3. {subject C}  {value}
Same unit/window · {timestamp} · {source}
```

### Event timeline

```text
<b>{subject}: {latest state}</b>
09:02  {event one}
09:14  {event two}
09:27  {event three}
Observed {timestamp} · {source}
```

Use aligned monospaced text only when proportional rendering would make numeric comparison
harder and line wrapping has been tested on mobile.

## Rich Message recipes

### Report

```text
H1  Answer
P   One-sentence interpretation already supported by input
H2  Evidence
TABLE or LIST
DETAILS  Method and long evidence
FOOTER   Timestamp · unit · source
```

### Overview plus detail

```text
H1  Primary answer
PULL QUOTE  Hero value or supplied state
DIVIDER
H2  What changed
TABLE / TIMELINE
DETAILS  Sources, method, raw observations
```

Keep tables narrow:

- prefer two or three columns
- place the comparable value in the rightmost column
- keep units in headers when all rows share them
- move long notes into a details block
- replace a wide table with repeated label–value rows

## Typography and emphasis

- Use one heading level as the visual entry point.
- Bold the answer, not entire paragraphs.
- Use monospace for identifiers and aligned measurements, not prose.
- Use marked text sparingly for one supplied exception or changed item.
- Use block quotes for evidence or a quoted source, not decoration.
- Use details blocks to defer method, raw evidence, and secondary context.
- Keep emoji semantic and limited; never encode state with emoji alone.

## Density budget

For the first viewport on a typical phone:

- one headline
- one primary line
- no more than five evidence rows
- one compact provenance line

If more content is essential, use a collapsed details block or split overview and detail.
Avoid walls of bold text and nested bullets deeper than two levels.
Never let a long headline consume the answer/evidence budget. Splits must use balanced HTML,
must not cut escaped entities, and must report `part_count`; silent omission is a failure.

## Captions for image and motion

A caption should provide what the media cannot:

- the answer in accessible text
- observation time and source
- one caveat, uncertainty, or missing-data note

Do not list every plotted value again. Do not make the visual depend on a caption for its
title, units, legend, or time window.

## Content integrity

- Preserve the script's terminology and sign convention.
- Show explicit `+` and `−` signs for signed deltas.
- Keep currency/unit position consistent.
- Use locale-aware separators without changing precision.
- Distinguish zero, missing, unknown, and not applicable.
- Never add action language, urgency, or causal explanation absent from input.
