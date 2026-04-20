"""CLI entry point for the Progressive Harmonization ETL framework.

Usage:
    python -m src.cli <input_file> --source <source_name> [--device <device>] [--output <file>]

Example:
    python -m src.cli "sample_data/mHealth/example data/fitbit-example (1).json" --source fitbit
"""

from __future__ import annotations

import argparse
import json
import logging
import sys
from pathlib import Path

from .adapters import AdapterRegistry, ConfigAdapter, FitbitAdapter
from .connectors import JsonConnector, SourceMetadata
from .heuristics import HeuristicChain, TimestampNormalizer, UnitInferrer
from .pipeline import Pipeline

CONFIGS_DIR = Path(__file__).resolve().parent.parent / "configs"


def build_default_registry() -> AdapterRegistry:
    """Build a registry with all built-in adapters.

    Loads YAML config-driven adapters from configs/ first (Tier 1),
    then registers hardcoded adapters as fallback.
    """
    registry = AdapterRegistry()

    # Tier 1: Config-driven adapters (preferred)
    if CONFIGS_DIR.is_dir():
        for config_path in sorted(CONFIGS_DIR.glob("*.yaml")):
            try:
                registry.register(ConfigAdapter(config_path))
            except Exception as e:
                logging.getLogger(__name__).warning(
                    "Failed to load config %s: %s", config_path.name, e
                )

    # Fallback: hardcoded adapters (for types not yet covered by configs)
    registry.register(FitbitAdapter())
    return registry


def build_default_heuristics() -> HeuristicChain:
    """Build the default heuristic chain."""
    return HeuristicChain([
        TimestampNormalizer(),
        UnitInferrer(),
    ])


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(
        description="Progressive Harmonization ETL - Ingest data into canonical model"
    )
    parser.add_argument("input", help="Path to the input data file")
    parser.add_argument(
        "--source",
        required=True,
        help="Source name (e.g., 'fitbit', 'withings')",
    )
    parser.add_argument("--device", default=None, help="Device model (e.g., 'Fitbit Charge 6')")
    parser.add_argument("--output", "-o", default=None, help="Output file (default: stdout)")
    parser.add_argument(
        "--pretty", action="store_true", default=True, help="Pretty-print JSON output"
    )
    parser.add_argument("--verbose", "-v", action="store_true", help="Enable verbose logging")

    args = parser.parse_args(argv)

    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.INFO,
        format="%(levelname)s %(name)s: %(message)s",
    )

    metadata = SourceMetadata(
        source_name=args.source,
        format="json",
        device=args.device,
        modality="wearable",
    )

    connector = JsonConnector(metadata)
    registry = build_default_registry()
    heuristics = build_default_heuristics()
    pipeline = Pipeline(connector, registry, heuristics)

    events = pipeline.run(args.input)

    output = [e.to_dict() for e in events]
    json_str = json.dumps(output, indent=2 if args.pretty else None, default=str)

    if args.output:
        Path(args.output).write_text(json_str, encoding="utf-8")
        print(f"Wrote {len(events)} canonical events to {args.output}", file=sys.stderr)
    else:
        print(json_str)


if __name__ == "__main__":
    main()
