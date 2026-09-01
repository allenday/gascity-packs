#!/usr/bin/env python3
"""Small CLI fixture for exercising the deployed docs-impact reviewer."""

from __future__ import annotations

import argparse


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--label", default="supervisor-smoke")
    parser.add_argument("--quiet", action="store_true")
    parser.parse_args()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
