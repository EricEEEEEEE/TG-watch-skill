#!/usr/bin/env python3
"""Run the TG Watch corpus through inference, compilation, rendering, and QA.

The compiler in this module deliberately consumes only the representative
payload and the VisualSpec returned by ``inspect_payload``. Expected labels in
the corpus are read only after rendering, when the evaluator scores the result.
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from collections import Counter
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import Any, Dict, List, Mapping, Optional, Sequence, Tuple


ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / "scripts"
if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))

import make_contact_sheet  # noqa: E402
import render_visual as V  # noqa: E402
import validate_visual  # noqa: E402
from inspect_visual_semantics import inspect_payload  # noqa: E402
from render_rich_message import render_message  # noqa: E402
from visual_spec import FeatureGate, VisualSpec  # noqa: E402


MANIFEST_SCHEMA = "tg-watch.render-eval.v1"
GRAMMAR_TO_KIND = {
    "value-band": "anchor",
    "threshold-bullet": "threshold",
    "aligned-bars": "comparison",
    "ranked-bars": "ranking",
    "annotated-line": "trend",
    "stacked-composition": "composition",
    "node-link": "network",
    "range-band": "uncertainty",
    "route-map": "route",
    "event-timeline": "timeline",
    "sequence-replay": "sequence",
}


class CompileError(ValueError):
    """Raised when a VisualSpec cannot be compiled without inventing facts."""


def _json_dump(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )


def _safe_name(value: str) -> str:
    normalized = re.sub(r"[^a-zA-Z0-9._-]+", "-", value).strip("-")
    return normalized or "case"


def _evidence_values(spec: VisualSpec) -> Dict[str, str]:
    return {datum.source_path: datum.value for datum in spec.evidence}


def _source_value(spec: VisualSpec, source_path: str) -> Any:
    values = _evidence_values(spec)
    if source_path not in values:
        raise CompileError("VisualSpec evidence is missing %s" % source_path)
    raw: Any = values[source_path]
    if isinstance(raw, str):
        stripped = raw.strip()
        if stripped.startswith(("[", "{")):
            try:
                return json.loads(stripped)
            except json.JSONDecodeError:
                pass
        if stripped in {"true", "false", "null"}:
            return json.loads(stripped)
        try:
            if re.fullmatch(r"[-+]?(?:\d+(?:\.\d*)?|\.\d+)(?:[eE][-+]?\d+)?", stripped):
                return json.loads(stripped)
        except json.JSONDecodeError:
            pass
    return raw


def _has_evidence(spec: VisualSpec, source_path: str) -> bool:
    return source_path in _evidence_values(spec)


def _copy_source_for_text(
    spec: VisualSpec, value: str, preferred_paths: Sequence[str]
) -> Optional[str]:
    """Find the original payload field that supplied display narrative."""

    evidence = _evidence_values(spec)
    for source_path in preferred_paths:
        if source_path in evidence and str(evidence[source_path]) == value:
            return source_path
    for source_path, candidate in evidence.items():
        if str(candidate) == value:
            return source_path
    return None


class _RenderCompiler:
    """Small deterministic VisualSpec -> RenderSpec compiler for the corpus."""

    def __init__(self, spec: VisualSpec):
        self.spec = spec
        self.data: Dict[str, Any] = {}
        self.meta: Dict[str, Any] = {}
        self.bindings: Dict[str, Dict[str, Any]] = {}

    def direct(self, target: str, source_path: str) -> Any:
        value = _source_value(self.spec, source_path)
        self.bindings[target] = {"source_path": source_path}
        return value

    def derived(
        self, target: str, operation: str, source_paths: Sequence[str]
    ) -> Any:
        inputs = [_evidence_values(self.spec)[path] for path in source_paths]
        result = V.execute_binding_operation(operation, inputs)
        self.bindings[target] = {
            "inputs": list(source_paths),
            "operation": operation,
            "verified_result": result,
        }
        return result

    def common(self) -> None:
        if _has_evidence(self.spec, "$.unit"):
            self.data["unit"] = self.direct("data.unit", "$.unit")
        if _has_evidence(self.spec, "$.source"):
            self.meta["source"] = self.direct("meta.source", "$.source")
        if _has_evidence(self.spec, "$.timestamp"):
            self.meta["timestamp"] = self.direct("meta.timestamp", "$.timestamp")
        if _has_evidence(self.spec, "$.confidence_interval"):
            self.meta["uncertainty"] = self.direct(
                "meta.uncertainty", "$.confidence_interval"
            )

    def decimals_for(self, *source_paths: str) -> None:
        """Preserve supplied precision while hiding binary-float artifacts."""

        maximum = 0

        def visit(value: Any) -> None:
            nonlocal maximum
            if isinstance(value, bool):
                return
            if isinstance(value, (int, float)):
                try:
                    exponent = Decimal(str(value)).as_tuple().exponent
                except (InvalidOperation, ValueError):
                    return
                maximum = max(maximum, max(0, -int(exponent)))
            elif isinstance(value, list):
                for child in value:
                    visit(child)
            elif isinstance(value, Mapping):
                for child in value.values():
                    visit(child)

        for source_path in source_paths:
            visit(_source_value(self.spec, source_path))
        self.data["decimals"] = min(8, maximum)

    def compile(self) -> Dict[str, Any]:
        grammar = self.spec.grammar
        kind = GRAMMAR_TO_KIND.get(grammar)
        if kind is None:
            raise CompileError(
                "grammar %r is not an image/video grammar" % grammar
            )
        self.common()
        handler = getattr(self, "_compile_" + kind)
        handler()
        title_source = _copy_source_for_text(
            self.spec,
            self.spec.headline,
            ("$.headline", "$.title", "$.name", "$.pair", "$.label"),
        )
        if title_source is None:
            raise CompileError(
                "image/video headline must copy a traceable payload field"
            )
        title = str(self.derived("title", "copy", (title_source,)))
        subtitle = ""
        if self.spec.answer:
            answer_source = _copy_source_for_text(
                self.spec,
                self.spec.answer,
                ("$.summary", "$.conclusion", "$.answer", "$.message", "$.status"),
            )
            if answer_source is None:
                raise CompileError(
                    "image/video answer must copy a traceable payload field"
                )
            subtitle = str(self.derived("subtitle", "copy", (answer_source,)))
        elif _has_evidence(self.spec, "$.confidence"):
            subtitle = str(_source_value(self.spec, "$.confidence"))
            self.bindings["subtitle"] = {
                "inputs": ["$.confidence"],
                "operation": "copy",
                "verified_result": subtitle,
            }
        render_spec = {
            "version": "1.0",
            "kind": kind,
            "title": title,
            "subtitle": subtitle,
            "theme": "light",
            "data": self.data,
            "meta": self.meta,
            "source_bindings": self.bindings,
        }
        return {
            "visual_spec": self.spec.to_dict(),
            "render_spec": render_spec,
        }

    def _compile_threshold(self) -> None:
        self.data["value"] = self.direct("data.value", "$.value")
        self.data["threshold"] = self.direct("data.threshold", "$.threshold")
        self.decimals_for("$.value", "$.threshold")

    def _compile_anchor(self) -> None:
        intent = self.spec.intents[0].value
        if intent == "discount_premium":
            current_path, anchor_path = "$.current_price", "$.fair_anchor_price"
            self.data["current_label"] = "PRICE"
            self.data["anchor_label"] = "FAIR"
        elif intent == "spread":
            current_path, anchor_path = "$.bid", "$.ask"
            self.data["current_label"] = "BID"
            self.data["anchor_label"] = "ASK"
        else:
            current_path, anchor_path = "$.value", "$.anchor"
            self.data["current_label"] = "CURRENT"
            self.data["anchor_label"] = "ANCHOR"
        self.data["current"] = self.direct("data.current", current_path)
        self.data["anchor"] = self.direct("data.anchor", anchor_path)
        self.decimals_for(current_path, anchor_path)

    def _compile_comparison(self) -> None:
        if self.spec.intents[0].value == "before_after":
            sources = ("$.categories", "$.previous_values", "$.current_values")
            self.data["items"] = self.derived(
                "data.items", "before_after_items", sources
            )
            self.decimals_for("$.previous_values", "$.current_values")
        else:
            self.data["items"] = self.derived(
                "data.items", "zip_items", ("$.categories", "$.values")
            )
            self.decimals_for("$.values")

    def _compile_ranking(self) -> None:
        self.data["items"] = self.derived(
            "data.items", "zip_items", ("$.categories", "$.values")
        )
        self.decimals_for("$.values")

    def _compile_trend(self) -> None:
        self.data["points"] = self.direct("data.points", "$.series")
        if _has_evidence(self.spec, "$.threshold"):
            self.data["threshold"] = self.direct(
                "data.threshold", "$.threshold"
            )
        self.decimals_for("$.series")

    def _compile_composition(self) -> None:
        self.data["items"] = self.derived(
            "data.items", "zip_items", ("$.categories", "$.values")
        )
        self.decimals_for("$.values")

    def _compile_network(self) -> None:
        self.data["nodes"] = self.derived(
            "data.nodes", "node_objects", ("$.nodes",)
        )
        self.data["edges"] = self.derived(
            "data.edges", "edge_objects", ("$.edges",)
        )

    def _compile_uncertainty(self) -> None:
        self.data["estimate"] = self.direct("data.estimate", "$.estimate")
        self.data["intervals"] = self.derived(
            "data.intervals", "interval_band", ("$.confidence_interval",)
        )
        self.decimals_for("$.estimate", "$.confidence_interval")

    def _compile_route(self) -> None:
        self.data["points"] = self.derived(
            "data.points", "endpoint_points", ("$.origin", "$.destination")
        )
        if _has_evidence(self.spec, "$.distance") and _has_evidence(
            self.spec, "$.unit"
        ):
            self.data["distance_label"] = self.derived(
                "data.distance_label",
                "format_value_unit",
                ("$.distance", "$.unit"),
            )

    def _compile_timeline(self) -> None:
        self.data["events"] = self.derived(
            "data.events", "timeline_events", ("$.events",)
        )
        event_count = len(_source_value(self.spec, "$.events"))
        if event_count > 9:
            self.data["max_items"] = event_count

    def _compile_sequence(self) -> None:
        # The motion renderer accepts numeric arrays directly and assigns only
        # presentational step labels, so no transformation is needed.
        self.data["frames"] = self.direct("data.frames", "$.series")
        if _has_evidence(self.spec, "$.threshold"):
            self.data["threshold"] = self.direct(
                "data.threshold", "$.threshold"
            )
        self.decimals_for("$.series")


def compile_render_bundle(spec: VisualSpec) -> Dict[str, Any]:
    """Compile a source-bound render bundle without consulting expectations."""

    if spec.selected_modality.value not in {"image", "video"}:
        raise CompileError("text VisualSpec does not compile to raster media")
    return _RenderCompiler(spec).compile()


def _text_fallback_ok(spec: VisualSpec, rendered: Mapping[str, Any]) -> bool:
    payload = rendered.get("payload")
    if rendered.get("selected_format") == "html":
        return (
            isinstance(payload, str)
            and bool(payload.strip())
            and rendered.get("parse_mode") == "HTML"
            and len(payload) <= spec.feature_gate.max_html_chars
        )
    fallback = rendered.get("fallback")
    return (
        isinstance(payload, Mapping)
        and isinstance(fallback, Mapping)
        and fallback.get("format") == "html"
        and isinstance(fallback.get("payload"), str)
        and bool(str(fallback.get("payload")).strip())
    )


def _relative(path: Path, base: Path) -> str:
    return path.relative_to(base).as_posix()


def _mobile_artifact_gate(
    artifact: Path,
    role: str,
    case_dir: Path,
    out_dir: Path,
) -> Dict[str, Any]:
    report = validate_visual.validate_mobile_previews(
        artifact,
        case_dir / "mobile" / role,
    )
    report["source"] = _relative(artifact, out_dir)
    for width_result in report.get("results", {}).values():
        width_result["path"] = _relative(Path(width_result["path"]), out_dir)
    validation_path = case_dir / f"{role}-mobile-validation.json"
    report["validation_path"] = _relative(validation_path, out_dir)
    _json_dump(validation_path, report)
    return report


def _inference_checks(
    case: Mapping[str, Any], spec: VisualSpec
) -> Tuple[Dict[str, bool], Dict[str, Any], Dict[str, Any]]:
    actual = {
        "medium": spec.selected_modality.value,
        "primary_intent": spec.intents[0].value,
        "grammar": spec.grammar,
        "roles": sorted(role.value for role in spec.semantic_roles),
    }
    expected = {
        "medium": str(case["expected_medium"]),
        "primary_intent": str(case["intent"]),
        "grammar": str(case["expected_grammar"]),
        "roles": sorted(str(role) for role in case["roles"]),
    }
    checks = {
        key: actual[key] == expected[key]
        for key in ("medium", "primary_intent", "grammar")
    }
    checks["roles"] = set(expected["roles"]) <= set(actual["roles"])
    return checks, expected, actual


def evaluate_render_case(
    case: Mapping[str, Any],
    out_dir: Path,
    *,
    video_fallback: bool = True,
) -> Dict[str, Any]:
    """Run one complete case; expectations never enter inference/compilation."""

    case_id = str(case["id"])
    case_dir = out_dir / "cases" / _safe_name(case_id)
    case_dir.mkdir(parents=True, exist_ok=True)
    result: Dict[str, Any] = {
        "id": case_id,
        "intent_family": str(case["intent"]),
        "variant": str(case["variant"]),
        "passed": False,
        "errors": [],
        "paths": {},
    }
    try:
        spec = inspect_payload(
            case["sample"],
            primary_question=str(case["primary_question"]),
        )
        checks, expected, actual = _inference_checks(case, spec)
        result["inference"] = {
            "passed": all(checks.values()),
            "checks": checks,
            "expected": expected,
            "actual": actual,
        }
        spec_path = case_dir / "visual-spec.json"
        _json_dump(spec_path, spec.to_dict())
        result["paths"]["visual_spec"] = _relative(spec_path, out_dir)

        text_output = render_message(spec)
        text_path = case_dir / "text-fallback.json"
        _json_dump(text_path, text_output)
        text_ok = _text_fallback_ok(spec, text_output)
        result["text_fallback"] = {
            "passed": text_ok,
            "selected_format": text_output.get("selected_format"),
        }
        result["paths"]["text_fallback"] = _relative(text_path, out_dir)

        media_ok = True
        mobile_ok = True
        mobile_artifacts: Dict[str, Dict[str, Any]] = {}
        if spec.selected_modality.value in {"image", "video"}:
            bundle = compile_render_bundle(spec)
            bundle_path = case_dir / "render-bundle.json"
            _json_dump(bundle_path, bundle)
            suffix = ".gif" if spec.selected_modality.value == "video" else ".png"
            artifact = case_dir / ("primary" + suffix)
            V.render(bundle, artifact)
            validation = validate_visual.validate_visual(artifact, bundle)
            validation_path = case_dir / "validation.json"
            _json_dump(validation_path, validation)
            media_ok = bool(validation["ok"])
            if not media_ok:
                result["errors"].extend(
                    "primary validation: %s" % error
                    for error in validation.get("errors", [])
                )
            result["media"] = {
                "passed": media_ok,
                "kind": bundle["render_spec"]["kind"],
                "format": validation.get("format"),
                "frames": validation.get("frames"),
                "traceability": validation.get("checks", {}).get(
                    "traceability", False
                ),
                "source_bindings": validation.get("metadata", {}).get(
                    "source_binding_status"
                ),
            }
            result["paths"].update(
                {
                    "render_bundle": _relative(bundle_path, out_dir),
                    "artifact": _relative(artifact, out_dir),
                    "validation": _relative(validation_path, out_dir),
                }
            )
            primary_mobile = _mobile_artifact_gate(
                artifact,
                "primary",
                case_dir,
                out_dir,
            )
            mobile_artifacts["primary"] = primary_mobile
            mobile_ok = mobile_ok and bool(primary_mobile["ok"])
            if not primary_mobile["ok"]:
                result["errors"].extend(
                    "primary mobile gate: %s" % error
                    for error in primary_mobile.get("errors", [])
                )

            if spec.selected_modality.value == "video":
                for role, metadata_key in (
                    ("poster", "poster_artifact"),
                    ("final", "final_artifact"),
                ):
                    filename = validation.get("metadata", {}).get(
                        metadata_key, ""
                    )
                    static_artifact = artifact.parent / str(filename)
                    static_mobile = _mobile_artifact_gate(
                        static_artifact,
                        role,
                        case_dir,
                        out_dir,
                    )
                    mobile_artifacts[role] = static_mobile
                    mobile_ok = mobile_ok and bool(static_mobile["ok"])
                    if not static_mobile["ok"]:
                        result["errors"].extend(
                            "%s mobile gate: %s" % (role, error)
                            for error in static_mobile.get("errors", [])
                        )

            if spec.selected_modality.value == "video" and video_fallback:
                fallback_gate = FeatureGate(
                    rich_messages=spec.feature_gate.rich_messages,
                    images=spec.feature_gate.images,
                    videos=False,
                    max_rich_text_chars=spec.feature_gate.max_rich_text_chars,
                    max_html_chars=spec.feature_gate.max_html_chars,
                )
                fallback_spec = inspect_payload(
                    case["sample"],
                    primary_question=str(case["primary_question"]),
                    feature_gate=fallback_gate,
                )
                fallback_bundle = compile_render_bundle(fallback_spec)
                fallback_bundle_path = case_dir / "image-fallback-bundle.json"
                _json_dump(fallback_bundle_path, fallback_bundle)
                fallback_artifact = case_dir / "image-fallback.png"
                V.render(fallback_bundle, fallback_artifact)
                fallback_validation = validate_visual.validate_visual(
                    fallback_artifact, fallback_bundle
                )
                fallback_validation_path = (
                    case_dir / "image-fallback-validation.json"
                )
                _json_dump(fallback_validation_path, fallback_validation)
                fallback_ok = (
                    fallback_spec.selected_modality.value == "image"
                    and fallback_spec.grammar == "annotated-line"
                    and bool(fallback_validation["ok"])
                )
                if not fallback_ok:
                    result["errors"].extend(
                        "image fallback validation: %s" % error
                        for error in fallback_validation.get("errors", [])
                    )
                media_ok = media_ok and fallback_ok
                result["image_fallback"] = {
                    "passed": fallback_ok,
                    "grammar": fallback_spec.grammar,
                    "traceability": fallback_validation.get("checks", {}).get(
                        "traceability", False
                    ),
                }
                result["paths"].update(
                    {
                        "image_fallback_bundle": _relative(
                            fallback_bundle_path, out_dir
                        ),
                        "image_fallback_artifact": _relative(
                            fallback_artifact, out_dir
                        ),
                        "image_fallback_validation": _relative(
                            fallback_validation_path, out_dir
                        ),
                    }
                )
                fallback_mobile = _mobile_artifact_gate(
                    fallback_artifact,
                    "image-fallback",
                    case_dir,
                    out_dir,
                )
                mobile_artifacts["image_fallback"] = fallback_mobile
                mobile_ok = mobile_ok and bool(fallback_mobile["ok"])
                if not fallback_mobile["ok"]:
                    result["errors"].extend(
                        "image fallback mobile gate: %s" % error
                        for error in fallback_mobile.get("errors", [])
                    )
        else:
            result["media"] = {"passed": True, "kind": "text"}

        result["mobile_gate"] = {
            "passed": mobile_ok,
            "required_widths": list(validate_visual.MOBILE_WIDTHS),
            "artifact_count": len(mobile_artifacts),
            "preview_count": sum(
                int(report.get("preview_count", 0))
                for report in mobile_artifacts.values()
            ),
            "artifacts": mobile_artifacts,
            "not_applicable": not mobile_artifacts,
        }
        media_ok = media_ok and mobile_ok
        result["passed"] = (
            bool(result["inference"]["passed"]) and text_ok and media_ok
        )
    except (OSError, ValueError, KeyError, TypeError, V.RenderSpecError) as exc:
        result["errors"].append("%s: %s" % (type(exc).__name__, exc))
    return result


def evaluate_render_corpus(
    payload: Mapping[str, Any],
    out_dir: Path,
    *,
    contact_sheet: bool = False,
    video_fallback: bool = True,
) -> Dict[str, Any]:
    cases = payload.get("cases")
    if not isinstance(cases, list):
        raise ValueError("corpus must contain a cases array")
    out_dir.mkdir(parents=True, exist_ok=True)
    results = [
        evaluate_render_case(
            case,
            out_dir,
            video_fallback=video_fallback,
        )
        for case in cases
    ]
    passed = sum(1 for result in results if result["passed"])
    media_counts = Counter(
        result.get("inference", {}).get("actual", {}).get("medium", "error")
        for result in results
    )
    intent_counts = Counter(result["intent_family"] for result in results)
    artifacts = [
        out_dir / result["paths"]["artifact"]
        for result in results
        if "artifact" in result.get("paths", {})
    ]
    mobile_artifacts = [
        artifact
        for result in results
        for artifact in result.get("mobile_gate", {})
        .get("artifacts", {})
        .values()
    ]
    mobile_passed = sum(
        1 for artifact in mobile_artifacts if artifact.get("ok")
    )
    manifest: Dict[str, Any] = {
        "schema": MANIFEST_SCHEMA,
        "corpus": {
            "version": payload.get("version"),
            "description": payload.get("description", ""),
        },
        "case_count": len(results),
        "passed": passed,
        "failed": len(results) - passed,
        "pass_rate": passed / len(results) if results else 0.0,
        "artifact_count": len(artifacts),
        "media_counts": dict(sorted(media_counts.items())),
        "intent_counts": dict(sorted(intent_counts.items())),
        "mobile_gate": {
            "required_widths": list(validate_visual.MOBILE_WIDTHS),
            "artifact_count": len(mobile_artifacts),
            "preview_count": sum(
                int(artifact.get("preview_count", 0))
                for artifact in mobile_artifacts
            ),
            "passed_artifacts": mobile_passed,
            "failed_artifacts": len(mobile_artifacts) - mobile_passed,
            "passed": mobile_passed == len(mobile_artifacts),
        },
        "results": results,
    }
    if contact_sheet and artifacts:
        sheet = out_dir / "contact-sheet.png"
        make_contact_sheet.make_contact_sheet(artifacts, sheet, columns=5)
        manifest["contact_sheet"] = _relative(sheet, out_dir)
    _json_dump(out_dir / "manifest.json", manifest)
    return manifest


def load_corpus(path: Path) -> Mapping[str, Any]:
    raw = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(raw, Mapping):
        raise ValueError("corpus JSON must be an object")
    return raw


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Run deterministic TG Watch render evaluations."
    )
    parser.add_argument(
        "--cases",
        type=Path,
        default=Path(__file__).with_name("cases.json"),
        help="evaluation corpus JSON",
    )
    parser.add_argument(
        "--out-dir",
        type=Path,
        required=True,
        help="directory for bundles, artifacts, validations, and manifest",
    )
    parser.add_argument(
        "--contact-sheet",
        action="store_true",
        help="generate a first-frame contact sheet for visual review",
    )
    parser.add_argument(
        "--no-video-fallback",
        action="store_true",
        help="skip the separately inferred static fallback for video cases",
    )
    parser.add_argument(
        "--json",
        action="store_true",
        help="write the summary to stdout as JSON",
    )
    return parser


def main(argv: Optional[Sequence[str]] = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        summary = evaluate_render_corpus(
            load_corpus(args.cases),
            args.out_dir,
            contact_sheet=args.contact_sheet,
            video_fallback=not args.no_video_fallback,
        )
    except (OSError, ValueError, TypeError, json.JSONDecodeError) as exc:
        raise SystemExit("render evaluation error: %s" % exc) from exc
    if args.json:
        json.dump(summary, sys.stdout, ensure_ascii=False, indent=2, sort_keys=True)
        sys.stdout.write("\n")
    else:
        print(
            "TG Watch render eval: {passed}/{case_count} passed; "
            "{artifact_count} primary media artifacts; manifest={manifest}".format(
                manifest=args.out_dir / "manifest.json", **summary
            )
        )
        for result in summary["results"]:
            if not result["passed"]:
                print("FAIL %s %s" % (result["id"], result["errors"]))
    return 0 if summary["failed"] == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
