from __future__ import annotations

import logging
import re
from pathlib import Path
from typing import Any

import yaml
from pydantic import BaseModel

from services.adapter.config_adapter import ConfigAdapter

# services/gateway/configs_store.py → backend/configs/
BACKEND_DIR = Path(__file__).resolve().parent.parent.parent
CONFIGS_DIR = BACKEND_DIR / "configs"

logger = logging.getLogger(__name__)

_SLUG_RE = re.compile(r"[^a-zA-Z0-9_-]")


class ConfigStoreError(Exception):
    """Raised for user-facing errors (invalid YAML, id conflict, etc.)."""

    def __init__(self, message: str, status_code: int = 400) -> None:
        super().__init__(message)
        self.status_code = status_code


class ConfigSummary(BaseModel):
    id: str
    version: str | None = None
    description: str | None = None
    source: str | None = None
    record_filters: list[dict[str, Any]] = []


class ConfigPayload(BaseModel):
    id: str
    yaml: str


def _slugify(value: str) -> str:
    slug = _SLUG_RE.sub("-", value).strip("-")
    return slug or "config"


def _path_for(config_id: str) -> Path:
    safe = _slugify(config_id)
    if safe != config_id:
        raise ConfigStoreError(
            f"Config id '{config_id}' contains characters that are not allowed; "
            f"use only letters, digits, '-' and '_'."
        )
    return CONFIGS_DIR / f"{safe}.yaml"


def _parse_and_validate(yaml_text: str) -> dict[str, Any]:
    try:
        parsed = yaml.safe_load(yaml_text)
    except yaml.YAMLError as e:
        raise ConfigStoreError(f"Invalid YAML: {e}") from e
    if not isinstance(parsed, dict):
        raise ConfigStoreError("YAML must be a mapping at the top level.")
    try:
        ConfigAdapter.from_dict(parsed)
    except (KeyError, ValueError) as e:
        raise ConfigStoreError(f"Config is missing required sections: {e}") from e
    return parsed


def _summary_from_parsed(config_id: str, parsed: dict[str, Any]) -> ConfigSummary:
    adapter_block = parsed.get("adapter") or {}
    match_block = parsed.get("match") or {}
    raw_filters = match_block.get("record") or []
    record_filters = [item for item in raw_filters if isinstance(item, dict)]
    return ConfigSummary(
        id=config_id,
        version=adapter_block.get("version"),
        description=adapter_block.get("description"),
        source=match_block.get("source"),
        record_filters=record_filters,
    )


def _ensure_configs_dir() -> None:
    CONFIGS_DIR.mkdir(parents=True, exist_ok=True)


def list_configs() -> list[ConfigSummary]:
    _ensure_configs_dir()
    summaries: list[ConfigSummary] = []
    for path in sorted(CONFIGS_DIR.glob("*.yaml")):
        config_id = path.stem
        try:
            with path.open("r", encoding="utf-8") as f:
                parsed = yaml.safe_load(f)
        except yaml.YAMLError:
            logger.warning("Skipping config %s: invalid YAML", path.name)
            continue
        if not isinstance(parsed, dict):
            logger.warning("Skipping config %s: top-level is not a mapping", path.name)
            continue
        summaries.append(_summary_from_parsed(config_id, parsed))
    return summaries


def get_config(config_id: str) -> ConfigPayload:
    path = _path_for(config_id)
    if not path.is_file():
        raise ConfigStoreError(f"Config '{config_id}' not found.", status_code=404)
    return ConfigPayload(id=config_id, yaml=path.read_text(encoding="utf-8"))


def load_parsed_configs() -> list[tuple[str, dict[str, Any]]]:
    """Load every valid config as (id, parsed-dict). Skips unparseable files."""
    _ensure_configs_dir()
    results: list[tuple[str, dict[str, Any]]] = []
    for path in sorted(CONFIGS_DIR.glob("*.yaml")):
        try:
            with path.open("r", encoding="utf-8") as f:
                parsed = yaml.safe_load(f)
        except yaml.YAMLError:
            logger.warning("Skipping config %s: invalid YAML", path.name)
            continue
        if not isinstance(parsed, dict):
            continue
        results.append((path.stem, parsed))
    return results


def save_new_config(yaml_text: str) -> ConfigPayload:
    parsed = _parse_and_validate(yaml_text)
    adapter_block = parsed.get("adapter") or {}
    base_id = str(adapter_block.get("id") or "").strip()
    if not base_id:
        raise ConfigStoreError("Config is missing adapter.id.")

    base_slug = _slugify(base_id)
    _ensure_configs_dir()

    candidate = base_slug
    suffix = 2
    while (CONFIGS_DIR / f"{candidate}.yaml").exists():
        candidate = f"{base_slug}-{suffix}"
        suffix += 1

    if candidate != base_id:
        parsed.setdefault("adapter", {})["id"] = candidate
        yaml_text = yaml.safe_dump(parsed, sort_keys=False)

    (CONFIGS_DIR / f"{candidate}.yaml").write_text(yaml_text, encoding="utf-8")
    return ConfigPayload(id=candidate, yaml=yaml_text)


def update_config(config_id: str, yaml_text: str) -> ConfigPayload:
    path = _path_for(config_id)
    if not path.is_file():
        raise ConfigStoreError(f"Config '{config_id}' not found.", status_code=404)

    parsed = _parse_and_validate(yaml_text)
    parsed_id = str((parsed.get("adapter") or {}).get("id") or "").strip()
    if parsed_id != config_id:
        raise ConfigStoreError(
            f"adapter.id in the YAML ('{parsed_id}') does not match the URL id "
            f"('{config_id}'). Rename is not supported.",
            status_code=409,
        )

    path.write_text(yaml_text, encoding="utf-8")
    return ConfigPayload(id=config_id, yaml=yaml_text)
