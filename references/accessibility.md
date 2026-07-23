# Accessibility and mobile legibility

Treat accessibility as a rendering requirement. A visual that works only at source
resolution, with color, with audio, or in one language fails.

## Contents

- Mobile inspection and typography
- Contrast, reading order, and motion
- Language, accessible summaries, and failure conditions

Compile the accessible native-text summary directly from the same `VisualSpec` evidence as
the media. Preserve its evidence `source_path`; do not create a `RenderSpec` for text.
Image/video values remain bound through `RenderSpec.source_bindings`. Never reconstruct or
guess either path independently.

## Mobile-first inspection

Materialize, capture, and inspect every output at 320, 375, 390, and 430
CSS-pixel-equivalent widths.

At 390 px, verify:

- the primary answer is identifiable within three seconds
- the headline, hero value, axes, legend, and provenance are readable
- no text, marker, or panel clips or overlaps
- touch/crop-safe edges preserve critical content
- long Chinese and English labels wrap intentionally
- Telegram compression does not erase thin lines or small type

Do not approve a visual by looking only at a 1200 px source image.

## Typography

- Use a tested CJK-capable font for any CJK content.
- Provide explicit font fallback order; never depend on an unspecified system font.
- Fail validation on tofu/replacement glyphs.
- Use tabular numerals when columns or deltas must align.
- Keep units adjacent to values and use a nonbreaking relationship when possible.
- Allow at most two headline lines and three body lines per label.
- Prefer full labels; abbreviate only with an available legend or canonical abbreviation.
- Test mixed CJK, Latin, numbers, currency, minus signs, and punctuation.

For a 1200 px-wide raster baseline, start at:

- 48–64 px headline
- 36–44 px body/axis labels
- at least 30 px metadata

Judge final sizes after Telegram downsampling.

## Contrast and color

Meet:

- at least 4.5:1 contrast for normal text
- at least 3:1 for large text and meaningful graphical boundaries

Do not encode meaning with hue alone. Pair color with:

- label or value
- shape
- line style
- position
- icon plus text

Test grayscale and a common red/green color-vision simulation. Use diverging colors only
around a meaningful supplied midpoint.

## Reading order

Keep visual and semantic order aligned:

1. answer
2. evidence
3. provenance

Native-text fallbacks and captions must follow the same order. For Rich Messages, use
headings, lists, tables, and details semantically rather than approximating structure with
spaces or repeated symbols.

## Motion

- Make every video understandable without audio.
- Provide a native-text summary and a static fallback.
- Avoid flashes above three per second.
- Avoid unnecessary parallax, zoom, and looping.
- Keep labels stable long enough to read.
- Preserve a meaningful first frame and final frame.

If a reduced-motion variant is needed, use the static summary rather than merely slowing
decorative animation.

## Language and locale

- Preserve the user's/script's language.
- Use locale-aware number separators and date order.
- Include timezone when time could be ambiguous.
- Keep scientific symbols, signs, and units unambiguous.
- Do not translate identifiers, ticker symbols, place codes, or source names unless an
  established localized name is supplied.
- For right-to-left content, use a runtime-verified Rich Message RTL path or a verified RTL
  renderer.

## Accessible text companion

For every image or video, provide a concise native-text summary containing:

- subject and primary answer
- most important comparison or change
- timestamp and source
- supplied uncertainty or missingness

This is not a pixel-by-pixel alt text. It is the smallest text that preserves the visual's
meaning.

## Failure conditions

Fail the artifact when:

- any required glyph is missing
- the answer relies on red versus green
- essential text is below the mobile legibility floor
- content overlaps, clips, or is silently truncated
- contrast fails
- video requires sound or lacks a static fallback
- a map lacks an alternative textual location/distance
- the native-text summary disagrees with the media
