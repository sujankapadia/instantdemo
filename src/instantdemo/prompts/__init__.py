"""Prompt templates loaded from this package's bundled .md files."""

from __future__ import annotations

from importlib.resources import files


def load(name: str) -> str:
    """Read a prompt template from the package by basename (no extension).

    Example:
        load("phase1") → contents of src/instantdemo/prompts/phase1.md
    """
    return (files("instantdemo.prompts") / f"{name}.md").read_text(encoding="utf-8")
