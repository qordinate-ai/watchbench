#!/usr/bin/env python3
"""Compatibility wrapper for the Hugging Face export CLI."""

from watchbench.cli.export_hf_dataset import main


if __name__ == "__main__":
    raise SystemExit(main())
