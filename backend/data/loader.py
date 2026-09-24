"""
Loads the reference JSON data files from the project-level /data directory.

Most files loaded here are DEMO/PLACEHOLDER data (see each file's "_meta"
block). The JSL benchmark and climate-target files contain reported reference
values. This module is intentionally just a thin, cached loader - no
scientific computation happens here.
"""
from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path

# backend/data/loader.py -> backend/ -> project root -> data/
PROJECT_ROOT = Path(__file__).resolve().parents[2]
DATA_DIR = PROJECT_ROOT / "data"

_FILES = {
    "emission_factors": "emission_factors.json",
    "steel_grades": "steel_grades.json",
    "scrap_quality": "scrap_quality.json",
    "energy_sources": "energy_sources.json",
    "baseline": "baseline.json",
    "alloy_specifications": "alloy_specifications.json",
    "jsl_benchmarks": "JSL_BENCHMARKS.json",
    "jsl_climate_targets": "JSL_CLIMATE_TARGETS.json",
}


class DataFileNotFoundError(FileNotFoundError):
    pass


@lru_cache(maxsize=None)
def _load_json(filename: str) -> dict:
    path = DATA_DIR / filename
    if not path.exists():
        raise DataFileNotFoundError(
            f"Expected reference data file at {path}, but it was not found."
        )
    with path.open("r", encoding="utf-8") as f:
        return json.load(f)


def get_emission_factors() -> dict:
    return _load_json(_FILES["emission_factors"])


def get_steel_grades() -> dict:
    return _load_json(_FILES["steel_grades"])


def get_scrap_quality() -> dict:
    return _load_json(_FILES["scrap_quality"])


def get_energy_sources() -> dict:
    return _load_json(_FILES["energy_sources"])


def get_baseline() -> dict:
    return _load_json(_FILES["baseline"])


def get_alloy_specifications() -> dict:
    return _load_json(_FILES["alloy_specifications"])


def get_jsl_benchmarks() -> dict:
    return _load_json(_FILES["jsl_benchmarks"])


def get_jsl_climate_targets() -> dict:
    return _load_json(_FILES["jsl_climate_targets"])


def get_all_reference_data() -> dict:
    """Convenience bundle used by the /reference-data endpoint that feeds
    all frontend dropdowns in a single request."""
    return {
        "emission_factors": get_emission_factors(),
        "steel_grades": get_steel_grades(),
        "scrap_quality": get_scrap_quality(),
        "energy_sources": get_energy_sources(),
        "baseline": get_baseline(),
        "alloy_specifications": get_alloy_specifications(),
        "jsl_benchmarks": get_jsl_benchmarks(),
        "jsl_climate_targets": get_jsl_climate_targets(),
    }
