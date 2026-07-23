# Map and distance visual system

Use a map only when location, direction, extent, adjacency, or route is necessary to answer
the primary question. A geographic name alone does not justify a map.

## Contents

- Map-form selection and required elements
- VisualSpec/RenderSpec contract
- Viewport, labels, and map recipes
- Accuracy, fallbacks, and mobile acceptance

## Choose the map form

| Input relationship | Preferred form |
| --- | --- |
| one point; user needs to open/navigation context | native location or runtime-verified Rich Message map |
| one point plus nearby reference | static locator map |
| point plus supplied radius/uncertainty | radius map |
| origin, destination, and supplied route | route map |
| ordered positions over time | trajectory map; motion only if movement matters |
| several comparable points | labeled point map or clustered small multiples |
| supplied polygon/affected boundary | region map |
| value by administrative region | choropleth plus ordered value list |
| origin-destination volume | flow map, only for a small number of dominant flows |

Prefer a distance ruler or comparison chart when the geographic basemap contributes no
meaning.

## Spec contract

Let `VisualSpec` select the geographic intent and grammar; explicitly compile it to a
source-bound map `RenderSpec`. Bind every coordinate, route point, region vertex, distance,
time, label, and uncertainty value. Derived viewport bounds may be renderer geometry, but a
derived displayed distance or area must declare
`{inputs, operation, verified_result}` and pass renderer-side recomputation.

Never geocode, reroute, snap, interpolate, or replace a coordinate inside the renderer.

## Required visual elements

Include:

- a direct title answering the geographic question
- subject, origin/destination, or affected region labels
- scale bar or explicit distance when distance matters
- legend for symbol size, line style, color, or uncertainty
- observation time and source
- basemap attribution when required by the provider
- clear distinction between supplied route, straight-line relation, and estimated area

Use north-up unless orientation is itself the message. If rotating a route view, include an
orientation indicator.

## Viewport and labeling

- Compute bounds from all required geometry.
- Add 10–15% visual padding around the geometry.
- Preserve the complete route/region unless a deliberate detail inset is included.
- Keep the main subject away from Telegram crop-sensitive edges.
- Direct-label no more than seven important points in one mobile frame.
- Use numbered markers plus a keyed list when labels collide.
- Cluster or aggregate dense points; state the aggregation.
- Use an inset map when global location and local detail are both necessary.

Do not let a basemap compete with the evidence. Desaturate secondary roads, labels, and
terrain; keep the data overlay highest in contrast.

## Map-specific recipes

### Locator

Show one emphasized point, one recognizable reference area, and a short textual location.
Use native Telegram location when a custom basemap adds no explanatory value.

### Radius or uncertainty

Show the point, supplied radius/region, and boundary label. Use fill plus outline so the area
survives grayscale. Do not imply a circular uncertainty region when the input supplies only
a scalar distance without that meaning.

### Route and distance

Show origin and destination with distinct shapes, the supplied route as a directional line,
distance/time labels from input, and optional waypoints. Never label straight-line distance
as route distance.

### Trajectory

Encode time with ordered markers, directional arrows, or a restrained sequential scale.
Show start/end explicitly. Use motion only when the evolution of position is the evidence;
otherwise use a static path.

### Region comparison

Use a perceptually ordered sequential scale for magnitude and a diverging scale only around
a meaningful supplied midpoint. Pair the map with a ranked list so small regions remain
readable.

## Accuracy and integrity

- Plot coordinates exactly as supplied.
- Keep coordinate reference systems consistent.
- Do not fetch or choose a route unless the script already requests/provides that operation.
- Do not substitute a centroid for a precise location without labeling it.
- Do not imply precision beyond the input; use an area or uncertainty marker when supplied.
- Preserve antimeridian and high-latitude geometry correctly.
- Do not expose more location precision than the input/output contract intends.

## Fallbacks

Use:

```text
rendered map → runtime-verified Rich Message map/native location → labeled coordinates in text
route map → ordered waypoints + supplied distance in text
region map → ranked region table
trajectory video → static path + start/end markers
```

Fallback text must preserve the geographic answer, units, timestamp, and source.

## Mobile acceptance

At 390 px:

- origin, destination, and subject are distinguishable
- route/region remains visible without zooming
- distance/scale text is readable
- labels do not overlap the main evidence
- legend does not cover geometry
- map attribution remains legible
- color-disabled rendering preserves categories and boundaries
