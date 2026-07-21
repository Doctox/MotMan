#!/usr/bin/env python3
"""Rebuild the historical manifest for the owner-rejected round-2 batch."""
from __future__ import annotations

import curate_compact_7x8_young_current_round2 as curation


def main() -> None:
    curation.main()
    print(f"Lot refusé conservé comme preuve dans {curation.OUTPUT}")


if __name__ == "__main__":
    main()
