#!/usr/bin/env python3
"""Run the 85-case corpus through the real semantic inspector."""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any, Dict, Mapping, Optional, Sequence


ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / "scripts"
if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))

from inspect_visual_semantics import inspect_payload  # noqa: E402


def evaluate_case(case: Mapping[str, Any]) -> Dict[str, Any]:
    """Forward one real sample without leaking expected labels to the inspector."""

    spec = inspect_payload(
        case["sample"],
        primary_question=str(case["primary_question"]),
    )
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
        name: actual[name] == expected[name]
        for name in ("medium", "primary_intent", "grammar")
    }
    checks["roles"] = set(expected["roles"]) <= set(actual["roles"])
    return {
        "id": str(case["id"]),
        "passed": all(checks.values()),
        "checks": checks,
        "expected": expected,
        "actual": actual,
        "scores": spec.scores.to_dict(),
    }


def evaluate_corpus(payload: Mapping[str, Any]) -> Dict[str, Any]:
    cases = payload.get("cases")
    if not isinstance(cases, list):
        raise ValueError("corpus must contain a cases array")
    results = [evaluate_case(case) for case in cases]
    passed = sum(1 for result in results if result["passed"])
    return {
        "case_count": len(results),
        "passed": passed,
        "failed": len(results) - passed,
        "pass_rate": passed / len(results) if results else 0.0,
        "results": results,
    }


def load_corpus(path: Path) -> Mapping[str, Any]:
    raw = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(raw, Mapping):
        raise ValueError("corpus JSON must be an object")
    return raw


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Run TG Watch forward evaluations.")
    parser.add_argument(
        "--cases",
        type=Path,
        default=Path(__file__).with_name("cases.json"),
        help="evaluation corpus JSON",
    )
    parser.add_argument("--json", action="store_true", help="emit full JSON result")
    parser.add_argument(
        "--verbose", action="store_true", help="print every case result"
    )
    return parser


def main(argv: Optional[Sequence[str]] = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        summary = evaluate_corpus(load_corpus(args.cases))
    except (OSError, ValueError, KeyError, TypeError, json.JSONDecodeError) as exc:
        raise SystemExit("evaluation error: %s" % exc) from exc
    if args.json:
        json.dump(summary, sys.stdout, ensure_ascii=False, indent=2, sort_keys=True)
        sys.stdout.write("\n")
    else:
        if args.verbose:
            for result in summary["results"]:
                state = "PASS" if result["passed"] else "FAIL"
                print("%s %s" % (state, result["id"]))
                if not result["passed"]:
                    print(
                        "  expected=%s actual=%s"
                        % (result["expected"], result["actual"])
                    )
        print(
            "TG Watch forward eval: {passed}/{case_count} passed".format(**summary)
        )
    return 0 if summary["failed"] == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
