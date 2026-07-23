---
name: tg-watch-visual-system
description: Design, implement, and validate the best Telegram-facing visual output for any script or agent workflow. Use when Codex or another coding agent creates or revises user-visible Telegram output and must inspect the script's meaning, choose between native text/Rich Message, static image or map, media album, animation, and video, then implement mobile-first rendering for comparisons, trends, thresholds, value anchors, discounts or premiums, rankings, composition, timelines, locations, routes, distances, networks, uncertainty, or digests. This skill is purely visual and must not own alert triggers, scheduling, routing, deduplication, retries, acknowledgements, trading decisions, or source-data logic.
---

# TG Watch Visual System

Treat the skill as a **visual compiler**, not a card template and not an alert
framework.

Compile:

```text
script + sample output + user question
→ semantic roles
→ visual intent
→ text / image / video
→ visual grammar
→ renderer
→ Telegram-compatible artifact
→ mobile visual QA
```

## Core contract

Keep all work inside the presentation layer.

Do:

- inspect the real script, output schema, sample payload, and current rendering;
- identify the one question the user must answer first;
- preserve supplied numbers, units, thresholds, anchors, time, source, and
  uncertainty;
- select the least expensive medium that expresses the relationships correctly;
- implement the selected visual in the script or a reusable renderer;
- generate a real preview from representative data;
- validate the preview at Telegram mobile sizes;
- provide a lossless fallback for unsupported Telegram features.

Do not:

- create or change trigger conditions, schedules, routing, topics, cooldowns,
  deduplication, retries, acknowledgements, or delivery policy;
- invent severity, anchor values, thresholds, recommendations, confidence, or
  business conclusions;
- change data acquisition, financial calculations, trading behavior, or
  execution permissions;
- turn a short answer into an image or video merely for decoration;
- claim completion without opening or otherwise inspecting the rendered output.

If the user requests a plan only, stop after producing a `VisualSpec`. Otherwise,
implement, render, and verify.

## Required workflow

### 1. Inspect the real output

Read the relevant script and any formatter, template, renderer, sample payload,
and existing screenshots. Run a safe local sample when possible.

Record:

- audience and Telegram reading context;
- primary question;
- available facts and their provenance;
- relationships among facts;
- expected reading time: `5s`, `15s`, or `exploratory`;
- platform and dependency constraints.

Never design from filenames alone.

### 2. Extract semantic roles

Map source fields to domain-independent roles such as:

`scalar`, `delta`, `anchor`, `threshold`, `interval`, `series`, `category`,
`geo_point`, `geo_path`, `geo_region`, `network`, `sequence`, `uncertainty`,
`time`, `unit`, and `source`.

Then identify one or more visual intents:

`state`, `state_change`, `comparison`, `ranking`, `trend`, `composition`,
`threshold_distance`, `value_anchor`, `discount_premium`, `spread`, `timeline`,
`geo_location`, `distance_route`, `network`, `before_after`, `uncertainty`, or
`digest`.

Read `references/semantic-roles.md` whenever roles or intents are ambiguous.

### 3. Select the medium

Choose among three visual media:

1. **Text**
   - Use basic formatted text for one conclusion and at most five supporting
     facts.
   - Use Telegram Rich Message for structured reports, tables, details, quotes,
     formulas, or native media blocks when the runtime supports it.
2. **Image**
   - Use a card, chart, static map, timeline, topology, or 2–10 item album when
     the user must perceive comparison, scale, shape, spatial relation, or
     simultaneous evidence.
3. **Video**
   - Use animation/video only when movement, order, propagation, or transition
     carries meaning that a static view cannot express as clearly.

Require video to beat the best static alternative by at least 15 points in the
medium score. Otherwise use the static alternative.

Read `references/decision-engine.md` before making a non-obvious medium choice.
Record rejected media and reasons in the `VisualSpec`.

### 4. Compile a VisualSpec

Create the semantic and medium-decision contract before rendering:

```json
{
  "schema_version": "1.0",
  "primary_question": "How close is utilization to its threshold?",
  "headline": "Capacity",
  "answer": "73% used",
  "semantic_roles": ["scalar", "threshold", "delta", "time", "unit", "source"],
  "intents": ["threshold_distance"],
  "evidence": [
    {
      "label": "Current",
      "value": "73",
      "unit": "%",
      "role": "scalar",
      "source_path": "$.utilization"
    }
  ],
  "scores": {"text": 55, "image": 95, "video": 20},
  "selected_modality": "image",
  "fallback_chain": ["image", "text"],
  "selection_reason": "A shared scale exposes the remaining buffer.",
  "grammar": "threshold-bullet",
  "feature_gate": {
    "rich_messages": false,
    "images": true,
    "videos": true
  },
  "warnings": []
}
```

Use `scripts/inspect_visual_semantics.py` to generate or validate a draft
specification when the input can be represented as JSON. Keep Rich Messages
disabled until the deployed Bot API path, library, and target clients are
verified.

For text, compile `VisualSpec` directly through
`scripts/render_rich_message.py`. For image or video, explicitly compile it
into a concrete `RenderSpec`; bind every displayed field back to an
`evidence.source_path`:

```json
{
  "visual_spec": {
    "selected_modality": "image",
    "grammar": "threshold-bullet",
    "evidence": [
      {"value": "Capacity", "source_path": "$.label"},
      {"value": "73", "source_path": "$.utilization"},
      {"value": "85", "source_path": "$.threshold"},
      {"value": "%", "source_path": "$.unit"},
      {"value": "metrics API", "source_path": "$.source"},
      {"value": "2026-07-23 09:30 SGT", "source_path": "$.timestamp"}
    ]
  },
  "render_spec": {
    "version": "1.0",
    "kind": "threshold",
    "title": "Capacity",
    "data": {"value": 73, "threshold": 85, "unit": "%"},
    "meta": {"source": "metrics API", "timestamp": "2026-07-23 09:30 SGT"},
    "source_bindings": {
      "title": {
        "inputs": ["$.label"],
        "operation": "copy",
        "verified_result": "Capacity"
      },
      "data.value": {"source_path": "$.utilization"},
      "data.threshold": {"source_path": "$.threshold"},
      "data.unit": {"source_path": "$.unit"},
      "meta.source": {"source_path": "$.source"},
      "meta.timestamp": {"source_path": "$.timestamp"}
    }
  }
}
```

The shortened `visual_spec` above illustrates the binding only; pass the full
validated object in a real bundle. Do not let a pixel renderer guess which
source field belongs to a mark. Treat a standalone `RenderSpec` as an
exploratory preview; release validation requires the source-bound bundle.

### 5. Apply the visual grammar

Use one dominant visual question and at most two supporting evidence modules.

Apply this shared hierarchy to every medium:

1. **Answer** — verdict and one hero metric.
2. **Evidence** — comparison, trend, range, route, timeline, or other
   relationship.
3. **Trust** — object, time, unit, source, uncertainty, and missing/estimated
   status.

Read only the medium-specific reference needed:

- text or Rich Message: `references/text-visuals.md`
- cards and statistical charts: `references/image-visuals.md`
- locations, routes, radius, or regions: `references/map-visuals.md`
- animation or video: `references/motion-visuals.md`
- anchor, discount, or premium: `references/anchor-price-card.md`
- low-level Pillow composition: `references/rendering.md`

### 6. Render with the smallest suitable engine

Prefer deterministic local renderers:

- native structured output from `VisualSpec`: `scripts/render_rich_message.py`
- source-bound image/video bundle dispatch: `scripts/render_visual.py`
- cards and charts: `scripts/layout.py` and `scripts/render_chart.py`
- maps: `scripts/render_map.py`
- animations: `scripts/render_motion.py`
- explicit-fixture legacy anchor recipe: `scripts/render_anchor_price_card.py`

Use `assets/examples/visual-system-gallery.png` as a renderer index, not as a
template to copy blindly. The route and motion poster/final examples in the
same folder are release-reviewed mobile references.

Do not require a hosted chart service for sourced or sensitive data. Keep every
renderer usable without Telegram credentials.

For Telegram 10.2 Rich Messages and framework feature gates, read
`references/telegram-10.2.md`. Always provide an older-client/framework fallback.

### 7. Generate and inspect previews

Render at least one representative artifact. For reusable or high-risk layouts,
also render:

- a long CJK title;
- missing optional data;
- an extreme value or long label;
- light and dark themes when both are supported.

Use `scripts/make_contact_sheet.py` for multi-variant inspection. Open the output
at full size, then materialize and inspect the 320, 375, 390, and 430 px mobile
previews. Do not approve from dimensions or file existence alone.

### 8. Run visual QA

Run `scripts/validate_visual.py` on every image or animation and apply
`references/accessibility.md`.

Reject the output if any of these are true:

- the primary answer is not identifiable within five seconds;
- text is clipped, overlaps, becomes tofu, or is unreadable at any required
  mobile width;
- color or emoji is the only state encoding;
- axes, units, anchors, thresholds, time, or sources are missing when relevant;
- the caption repeats the image rather than complements it;
- a map does not answer location, distance, direction, route, or affected area;
- a video depends on sound, begins blank, or lacks a readable conclusion frame;
- displayed values cannot be traced to the input.

Read `references/acceptance-gates.md` before declaring a reusable renderer or
skill revision complete.

## Output requirements

For an implementation task, return:

- the selected medium and one-sentence rationale;
- the implemented file paths;
- the rendered preview paths;
- fallback behavior;
- validation commands and results;
- any visual limitation that remains.

Do not describe alert-system behavior that this skill did not own.
