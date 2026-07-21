#!/usr/bin/env python3
"""Deduplicate failed LLM-first fill attempts across agents and sessions."""

from __future__ import annotations

import argparse
import hashlib
import json
from datetime import date
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_REGISTRY = (
    ROOT / "src/data/grid-generation-handcrafted/llm-first-attempt-registry.json"
)
DEFAULT_BRIEF = (
    ROOT / "src/data/grid-generation-handcrafted/llm-first-unavailable-answers.json"
)
BLOCKING_STATUSES = {"unfillable", "editorial-rejected", "topology-invalid"}


def digest_file(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def normalized_values(values: list[str]) -> list[str]:
    return sorted({value.strip().upper() for value in values if value.strip()})


def canonical_state_digest(state: dict | list | None) -> str | None:
    """Return a stable digest of the exact partial layout, when one is supplied."""
    if state is None:
        return None
    encoded = json.dumps(
        state,
        ensure_ascii=True,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def select_state_path(state: object, dotted_path: str) -> object:
    """Select a nested item (for example ``conceptions.2``) from a JSON report."""
    current = state
    for part in dotted_path.split("."):
        if isinstance(current, list):
            current = current[int(part)]
        elif isinstance(current, dict):
            current = current[part]
        else:
            raise ValueError(f"Chemin d'état invalide à {part!r}")
    return current


def attempt_signature(
    shape_id: str,
    anchors: list[str],
    answers: list[str],
    policy_digest: str,
    partial_state: dict | list | None = None,
) -> str:
    payload = {
        "shapeId": shape_id.strip(),
        "anchors": normalized_values(anchors),
        "answers": normalized_values(answers),
        "policyDigest": policy_digest,
    }
    state_digest = canonical_state_digest(partial_state)
    if state_digest is not None:
        payload["stateDigest"] = state_digest
    encoded = json.dumps(payload, ensure_ascii=True, sort_keys=True).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def load_registry(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def matching_attempts(registry: dict, signature: str) -> list[dict]:
    return [item for item in registry.get("attempts", []) if item.get("signature") == signature]


def should_skip(attempts: list[dict]) -> bool:
    if any(item.get("status") in BLOCKING_STATUSES for item in attempts):
        return True
    return sum(item.get("status") == "timeout" for item in attempts) >= 2


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("action", choices=("check", "record"))
    parser.add_argument("--registry", type=Path, default=DEFAULT_REGISTRY)
    parser.add_argument("--brief", type=Path, default=DEFAULT_BRIEF)
    parser.add_argument("--shape-id", required=True)
    parser.add_argument("--anchor", action="append", default=[])
    parser.add_argument("--answer", action="append", default=[])
    parser.add_argument(
        "--state-file",
        type=Path,
        help=(
            "JSON contenant l'état exact de la grille partielle (cases, placements, "
            "motifs ouverts). Cet état distingue deux placements des mêmes mots."
        ),
    )
    parser.add_argument(
        "--state-path",
        default="",
        help="Chemin JSON pointé dans --state-file, par exemple conceptions.2.",
    )
    parser.add_argument(
        "--status",
        choices=("unfillable", "editorial-rejected", "timeout", "topology-invalid"),
    )
    parser.add_argument("--reason", default="")
    parser.add_argument("--agent", default="")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    registry = load_registry(args.registry)
    policy_digest = digest_file(args.brief)
    partial_state = None
    if args.state_file:
        partial_state = json.loads(args.state_file.read_text(encoding="utf-8"))
        if args.state_path:
            partial_state = select_state_path(partial_state, args.state_path)
    state_digest = canonical_state_digest(partial_state)
    signature = attempt_signature(
        args.shape_id,
        args.anchor,
        args.answer,
        policy_digest,
        partial_state,
    )
    matches = matching_attempts(registry, signature)
    if args.action == "check":
        result = {"signature": signature, "skip": should_skip(matches), "attempts": matches}
        print(json.dumps(result, ensure_ascii=False, indent=2))
        return 3 if result["skip"] else 0
    if not args.status or not args.reason.strip():
        raise ValueError("record exige --status et --reason")
    if any(
        item.get("status") == args.status and item.get("reason") == args.reason
        for item in matches
    ):
        print(json.dumps({"recorded": False, "signature": signature, "reason": "duplicate"}))
        return 0
    registry.setdefault("attempts", []).append({
        "signature": signature,
        "shapeId": args.shape_id,
        "anchorAnswers": normalized_values(args.anchor),
        "partialAnswers": normalized_values(args.answer),
        "stateDigest": state_digest,
        "partialState": partial_state,
        "policyDigest": policy_digest,
        "status": args.status,
        "reason": args.reason.strip(),
        "agent": args.agent.strip(),
        "triedOn": date.today().isoformat(),
    })
    args.registry.write_text(
        json.dumps(registry, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    print(json.dumps({"recorded": True, "signature": signature}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
