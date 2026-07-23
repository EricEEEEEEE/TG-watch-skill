# GitHub visual benchmark

Use this corpus as a maintained best-of reference, not as a claim that every GitHub
repository has been exhaustively proven inferior. Before a major release, repeat repository
and code search, update the corpus, and run the dominance tests in `acceptance-gates.md`.

Repository rows record observed visual patterns, not guaranteed current runtime support.
Only official Telegram Bot API documentation establishes protocol capabilities; verify every
third-party SDK, wrapper, server, and client with the runtime feature gate in
`telegram-10.2.md`.

## Contents

- Benchmark dimensions and reference corpus
- Cross-project findings and required advantages
- Corpus update procedure

## Benchmark dimensions

Score systems on:

1. semantic recognition from arbitrary script/output
2. medium selection across text, image, map, album, and motion
3. correctness of graphical encoding
4. Telegram-native and mobile legibility
5. CJK, contrast, missingness, and uncertainty
6. deterministic generation and fallback
7. cross-domain reuse without business coupling

## Reference corpus

### Telegram primitives

| Project | Borrow | Do not copy |
| --- | --- | --- |
| [python-telegram-bot](https://github.com/python-telegram-bot/python-telegram-bot) | official-style examples for media, keyboards, Web Apps | transport/API examples are not a visual decision system |
| [aiogram](https://github.com/aiogram/aiogram) | examples/types for photo, animation, video, and media groups in inspected revisions | repository presence does not prove installed-runtime support or justify a medium |
| [node-telegram-bot-api](https://github.com/yagop/node-telegram-bot-api) | broad Telegram carrier coverage | no semantic-to-visual compiler |
| [go-telegram/bot](https://github.com/go-telegram/bot) | direct media upload patterns | no content grammar or mobile QA |

### Monitoring and status

| Project | Borrow | Do not copy |
| --- | --- | --- |
| [Grafana](https://github.com/grafana/grafana) | alert-panel screenshots preserve nearby quantitative evidence | desktop panels often shrink poorly in Telegram |
| [Gatus](https://github.com/TwiN/gatus) | compact condition results and triggered/resolved contrast | plain template is not enough for trend/topology/geo |
| [Healthchecks](https://github.com/healthchecks/healthchecks) | schedule, downtime, last observation, and evidence hierarchy | verbose operational text as the universal format |
| [Uptime Kuma](https://github.com/louislam/uptime-kuma) | provider templates and concise state summaries | status prose without visual relationship selection |
| [Prometheus Alertmanager Bot](https://github.com/metalmatze/alertmanager-bot) | templated alert payloads and real-payload testing | template transport logic as visual architecture |
| [Zabbix Telegram](https://github.com/BlackVS/zabbix-telegram) | graph/image attachment with monitoring context | fixed monitoring vocabulary and screenshot dependence |

### Finance and quantitative visuals

| Project | Borrow | Do not copy |
| --- | --- | --- |
| [Freqtrade](https://github.com/freqtrade/freqtrade) | compact status/profit tables and financial hierarchy | trading actions or domain-specific decisions |
| [Hummingbot Condor](https://github.com/hummingbot/condor) | portfolio, PnL, trend, and composition dashboard patterns | desktop dashboard density |
| [Crypto-Signal](https://github.com/CryptoSignal/Crypto-Signal) | indicator overlays and multi-timeframe evidence | unexplained indicator density |
| [crypto-opnbot](https://github.com/hawooni/crypto-opnbot) | on-demand chart images with price context | third-party chart screenshot as universal renderer |
| [Jesse](https://github.com/jesse-ai/jesse) | quantitative chart conventions and reproducible analysis | trading framework coupling |

### News and content summaries

| Project | Borrow | Do not copy |
| --- | --- | --- |
| [TrendRadar](https://github.com/sansan0/TrendRadar) | grouped trends, ordering, keyword emphasis, Telegram delivery | ranking alone as semantic understanding |
| [RSS-to-Telegram-Bot](https://github.com/Rongronggg9/RSS-to-Telegram-Bot) | preserve native source media and concise metadata | one feed template for all content relationships |
| [Zam](https://github.com/AminAlam/Zam) | screenshot composition, RTL/CJK-aware rendering, progress cues | browser screenshot when native text is superior |

### Maps and spatial evidence

| Project | Borrow | Do not copy |
| --- | --- | --- |
| [plane-notify](https://github.com/Jxck-S/plane-notify) | path, direction, altitude/location context | aviation-specific field layout |
| [earthquake-talker-light](https://github.com/neuwcodebox/earthquake-talker-light) | event point, affected area, and geographic urgency | fixed earthquake severity semantics |
| [py-staticmaps](https://github.com/flopp/py-staticmaps) | deterministic static points, lines, polygons, and bounds | low-level drawing without visual hierarchy |
| [Bellingcat Toolkit](https://github.com/bellingcat/toolkit) | route, distance, polygon, and map-evidence tool patterns | external investigation UI as a Telegram card |

### Motion

| Project | Borrow | Do not copy |
| --- | --- | --- |
| [Remotion](https://github.com/remotion-dev/remotion) | deterministic data-driven video composition | motion without a semantic admission test |
| [Stickerify](https://github.com/Stickerifier/Stickerify) | Telegram-oriented media conversion | conversion as explanatory visualization |

## Cross-project finding

The corpus contains strong point solutions:

- Telegram libraries expose carriers.
- monitoring tools preserve state and evidence
- finance tools provide charts
- news tools provide ordering and media
- map tools provide geometry
- video tools provide deterministic composition

The benchmark gap is the integration layer: inspect arbitrary script semantics, identify the
dominant relationship, choose the lightest sufficient medium, compile a visual grammar, and
validate it on Telegram mobile without changing business behavior.

## Required advantages of this skill

The skill must demonstrate all of the following together:

- domain-neutral semantic roles and VisualIntent
- deterministic text/image/video selection with recorded reasoning
- official Rich Message path behind runtime feature gates plus safe degradation
- direct source-traceable `VisualSpec` text compilation and explicit
  `VisualSpec` → source-bound `RenderSpec` image/video compilation
- first-class anchor, threshold, uncertainty, timeline, map, and motion grammars
- CJK/mobile/accessibility gates
- data-to-pixel traceability
- static fallbacks for motion and rich features
- no ownership of routing, retry, alert policy, or business judgment

## Updating the corpus

For each release:

1. Search GitHub repository names, topics, README text, and code for Telegram plus the visual
   intents in `semantic-roles.md`.
2. Record candidates before judging them.
3. Deep-read source, examples, and screenshots for high-signal projects.
4. Add a project only when a reusable visual strength is evidenced.
5. Add a golden case whenever a competitor exposes a new capability.
6. Compare artifacts side by side at 390 px using the same source data.
7. Remove stale claims; keep direct repository or official-document links.

Do not claim universal superiority from stars, feature counts, or a one-time search. Claim
release superiority only against the named, dated corpus and passing dominance matrix.
