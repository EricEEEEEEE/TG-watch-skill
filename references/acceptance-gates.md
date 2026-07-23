# Acceptance gates

A visual is complete only after semantic, rendering, mobile, accessibility, fallback, and
benchmark checks pass. A renderer completing without error is not acceptance.

## Contents

- Evaluation corpus and gates 0–8
- Motion gate and release evidence
- Reviewer checklist

## Evaluation corpus

Maintain at least 85 golden cases:

- all 17 canonical VisualIntents:
  `state`, `state_change`, `comparison`, `ranking`, `trend`, `composition`,
  `threshold_distance`, `value_anchor`, `discount_premium`, `spread`, `timeline`,
  `geo_location`, `distance_route`, `network`, `before_after`, `uncertainty`, `digest`
- five variants per intent:
  normal, missing, extreme, long CJK/mixed text, and dense/compound

Include both familiar and unseen scripts. Keep evaluation inputs separate from expected
answers so forward tests cannot reconstruct the result from leaked context.

## Gate 0 — Pure visual scope

Pass only when:

- changes are limited to visual inspection, planning, rendering, preview, and QA
- business data and labels remain source-controlled
- no schedule, trigger, routing, topic, recipient, retry, deduplication, action, or trading
  behavior changes

Any scope violation blocks release even if the artifact looks better.

## Gate 1 — Semantic correctness

- state one primary visual question
- map every displayed element to a semantic role
- select one primary and at most two secondary VisualIntents
- preserve units, timestamps, source, missingness, and supplied uncertainty
- record all deterministic display derivations
- require a non-empty original-payload `source_path` for every `VisualSpec` evidence item

Target: 100% field-to-source traceability.

## Gate 1A — Spec compilation

- for text, pass `VisualSpec` directly to the text compiler/adapter
- verify rich and HTML text retain evidence `source_path`
- for image/video, compile `VisualSpec` to `RenderSpec` as an explicit AI/agent step
- validate the image/video bundle shape `{visual_spec, render_spec}`
- require `RenderSpec.source_bindings` for every displayed image/video field
- require image/video `title` and `subtitle` to use the registered `copy`
  operation against original evidence; matching an unbound `VisualSpec` string
  is not traceability
- require image/video derived bindings to declare complete `inputs`, a registered executable
  `operation`, and its exact `verified_result`
- recompute every derived value inside validation; reject free-form formulas and self-reported
  results
- reject fallback key search, prose-to-number inference, guessed values, and silent defaults
- verify the selected grammar maps to the registered `RenderSpec.kind`
- embed/record both spec digests in the artifact or validation report

A standalone unbound image/video `RenderSpec` may be used only as a marked local/legacy
fixture. It cannot pass a production or high-risk release gate.

## Gate 2 — Medium selection

Run blind review against human-authored expected plans:

- text/image/video decision agreement ≥95%
- Codex versus Claude Code decision agreement ≥90%
- zero unnecessary videos
- every video beats its best static candidate by ≥15 decision points
- every selected medium has a defined fallback

## Gate 3 — Data and graphical integrity

- shown values reproduce from input
- comparable values share unit and window
- axes, baselines, anchors, thresholds, and intervals are truthful
- zero, missing, unknown, and not-applicable remain distinct
- no hidden gaps, cropped outliers, invented interpolation, or unsupported conclusion

Target: zero numeric or semantic mismatch across golden cases.

## Gate 4 — Mobile rendering

Materialize and inspect real previews at 320, 375, 390, and 430 px. A calculation against
only the 390 px width does not pass this gate. For every release PNG, GIF, motion poster/final,
and static image fallback:

- no clipping, overlap, tofu, or accidental truncation
- answer identifiable within three seconds
- headline, hero value, axes, legend, and provenance readable
- critical content survives Telegram preview/crop/compression
- long CJK/mixed-language cases remain coherent
- saved preview dimensions and format match the requested width
- actual preview pixels retain visible content and a safe canvas margin
- actual card geometry remains consistent after resampling
- source typography/truncation metadata passes the width-specific display floor; metadata text
  remains at least 9.5 px at every required width
- GIF previews preserve frame count, frame durations, and distinct first/final frames

Run `validate_visual.py --mobile-preview-dir <dir>` or
`validate_mobile_previews(...)`. Record every width's result and artifact path in the release
manifest.

Target: ≥95% independent-reader answer accuracy at 390 px and 100% mechanical layout pass at
all four widths.

## Gate 5 — Accessibility

- normal text contrast ≥4.5:1
- large text/meaningful graphical boundary contrast ≥3:1
- grayscale and red/green color-vision simulation preserve meaning
- all image/video outputs include native-text meaning summaries
- motion is silent-readable, non-flashing, and has static fallback

Any essential color-only or audio-only encoding blocks release.

## Gate 6 — Carrier correctness

Validate actual target-client output:

- regular HTML/Markdown parses safely
- Rich Message capability is established by official Bot API documentation and runtime gate
- the deployed Bot API, third-party library/raw-call path, and target clients are verified
- Rich Message blocks render in those verified clients
- images keep intended scale after Telegram processing
- video poster, first frame, final frame, and compression remain readable
- collage/slideshow order preserves overview-first hierarchy
- native map/location fallback preserves the geographic answer

Test real representative payloads, not only isolated renderer files.

## Gate 7 — Degradation

Force each unavailable-capability path:

```text
Rich Message → regular text
image → structured text
map → native location/coordinates
motion → static summary → text
collage/slideshow → overview/contact sheet
```

Target: 100% fallback success with answer, unit, time, source, and supplied uncertainty
preserved.

## Gate 8 — GitHub benchmark dominance

Compare against the strongest relevant artifact in `github-benchmark.md` using identical
source data where possible.

Score each 1–5:

| Dimension | Weight |
| --- | ---: |
| primary-answer speed | 25% |
| semantic/encoding fit | 20% |
| mobile legibility | 15% |
| evidence density without overload | 15% |
| data integrity | 15% |
| accessibility and fallback | 10% |

Release only when:

- this skill wins blind preference ≥70%
- median time to locate the primary answer is ≥20% faster
- no reference capability regresses
- cross-domain cases succeed without adding business-specific renderer logic

Describe superiority as relative to the named, dated benchmark corpus, never “all GitHub”
without qualification.

## Motion-specific gate

For every video:

- duration normally 6–12 seconds
- meaningful first content appears within 0.5 seconds
- final answer holds for at least 1.5 seconds
- first and final frames work as standalone images
- static fallback contains the complete answer
- playback speed and interpolation do not distort evidence

## Release evidence

Produce an expected-versus-actual manifest:

```text
Expected: N cases
Actual:   M cases
Passed:   P
Failed:   F
Skipped:  S
```

List every case by name. For failures, record the failed gate and artifact path. Do not
summarize `M < N` as complete.

Required release artifacts:

- `VisualSpec` for every case
- rich/HTML adapter output for text cases
- `{visual_spec, render_spec}` bundle for every image/video case
- source-binding validation and VisualSpec/RenderSpec digests for image/video
- rendered regular/rich text preview where applicable
- source-resolution and 320/375/390/430 px previews for every PNG/GIF release artifact
- video poster/final/static fallback where applicable
- validator output
- contact sheet grouped by VisualIntent
- benchmark score sheet

## Reviewer checklist

- Does the visual answer exactly one primary question?
- Is the medium the lightest one that preserves the relationship?
- Can every pixel-level assertion be traced to input?
- Is the answer obvious on a phone without relying on color or audio?
- Does degradation preserve meaning?
- Did the implementation stay completely outside business and delivery behavior?

If any answer is no, iterate before release.
