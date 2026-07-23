# Telegram visual capabilities: Bot API 10.2

Treat Telegram as the display surface, not as the responsibility boundary. This skill
chooses and validates visual carriers; it does not own chat routing, topics, recipients,
notification policy, retries, or delivery operations.

## Contents

- Capability matrix and Rich Messages
- Feature gate and medium selection
- Caption, degradation, and exclusions

Official sources:

- [Bot API changelog](https://core.telegram.org/bots/api-changelog)
- [Bot features: advanced formatting](https://core.telegram.org/bots/features#advanced-formatting-options)
- [Bot API: Rich messages](https://core.telegram.org/bots/api#rich-messages)

All feature and limit statements below describe the **official Telegram Bot API 10.2**.
They do not prove that a deployed Bot API server, third-party SDK, wrapper, target client, or
account context supports them. Apply the runtime feature gate before selecting a carrier.

## Capability matrix

| Carrier | Best use | Visual limitation |
| --- | --- | --- |
| regular message | short answer, ≤5 facts | lightweight structure only |
| Rich Message | structured reports, tables, formulae, native media/map | requires Bot API/library/client support |
| photo + caption | stable chart/card/map | text is pixels; must pass mobile QA |
| media group/collage | overview plus related detail frames | order and captions must remain coherent |
| slideshow | sequential detail without forced playback | user controls progression |
| animation/video | data-driven motion | compression and autoplay behavior vary |
| native location/map | point location and navigation | limited custom encoding |
| Mini App/Web App | user-driven exploration | separate interactive product, not this skill's default output |

## Rich Messages

According to the official Bot API, 10.1 introduced `sendRichMessage`; 10.2 added explicit
outgoing blocks and media references. The official Rich Message model can express:

- headings, paragraphs, dividers, lists, and task lists
- nested inline emphasis and marked/code text
- tables with alignment, captions, borders, spans, and striping
- quotes, details, anchors, references, and footnotes
- inline and block LaTeX formulas
- photo, video, animation, audio, and voice-note blocks
- maps, collages, and slideshows

`InputRichMessage` must use exactly one of `html`, `markdown`, or `blocks`. When HTML or
Markdown references uploaded media, supply matching `InputRichMessageMedia` entries.

Official Bot API limits as of 10.2:

- 32,768 UTF-8 text characters
- 500 total blocks, including nested/list/table/detail blocks
- 16 nesting levels
- 50 media attachments
- 20 table columns

These are protocol ceilings, not design targets. Mobile visual density limits are much
lower.

## Feature gate

Before selecting Rich Messages:

1. Set `VisualSpec.feature_gate.rich_messages` false by default.
2. Verify the deployed Bot API endpoint/version exposes `sendRichMessage`.
3. Verify the exact third-party library method or a tested raw API path; package name or
   newest-version claims are insufficient.
4. Render/send a representative test in the target Telegram clients.
5. Confirm the used block types, CJK, tables, details, maps, and media display correctly.
6. Only then set the runtime feature gate true.
7. Pass the `VisualSpec` to the text compiler/adapter and keep its regular HTML fallback.

Never assume a framework supports Bot API 10.2 because Telegram itself does.
Do not cite a third-party library as evidence of Rich Message support unless the exact
installed version and method have been inspected and exercised.

## Medium selection

Prefer regular text when the answer is short.

Prefer Rich Messages when native structure can express the answer without rasterizing text:

- report → headings + paragraphs + details
- comparison → compact table
- method → details/footnote
- formula → mathematical-expression block
- point location → map block
- evidence set → collage/slideshow

Prefer a generated image when a custom quantitative scale, plot, route overlay, topology, or
stable annotated composition is necessary.

Prefer video only when `motion-visuals.md` admits it.

## Caption and media rules

- Make media independently titled, labeled, timestamped, and sourced.
- Put the accessible one-line answer in native text.
- Use captions for context and provenance, not a full transcription of the graphic.
- Reuse the same semantic payload for image labels and caption values.
- Generate a deliberate poster for video.
- Use an overview-first order for collage, slideshow, or media group.

## Degradation matrix

| Preferred output unavailable | Use |
| --- | --- |
| Rich Message | regular HTML/text with flattened headings and rows |
| Rich table | repeated label–value rows |
| Rich map | native location or labeled coordinates |
| collage/slideshow | ordered individual images or one contact sheet |
| custom image | structured text preserving values/units/time/source |
| video | poster/final summary image, then structured text |

The degraded output must preserve the answer and data integrity even when visual richness is
lost.

Rich and HTML text forms must come from the same source-traceable `VisualSpec`. Image/video
carriers must use the validated `{visual_spec, render_spec}` bundle, where `render_spec` is
the source-bound `RenderSpec`; their text fallback is compiled from that same `VisualSpec`.
Do not reconstruct fallback numbers from prose or unbound fields.

## Exclusions

Do not use this reference to decide:

- who receives a message
- which topic or chat is used
- when a message fires
- whether it is silent, ephemeral, protected, retried, or deduplicated
- whether a business action should occur

Those concerns may exist in the host script, but they are not modified by this visual skill.
