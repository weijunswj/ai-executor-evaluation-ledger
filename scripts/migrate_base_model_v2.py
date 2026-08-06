#!/usr/bin/env python3
"""Compatibility entrypoint for deterministic closed-manifest regeneration."""

from __future__ import annotations

from scripts.validate_manifests import main


if __name__ == "__main__":
    raise SystemExit(main(["--write"]))
