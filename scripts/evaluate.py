#!/usr/bin/env python3
"""Compatibility wrapper for the WatchBench evaluator CLI."""

from watchbench.cli.evaluate import main


if __name__ == "__main__":
    raise SystemExit(main())
