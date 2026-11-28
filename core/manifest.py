"""Validated provider and strategy metadata loaded from mappings/providers.yml."""

from __future__ import annotations

import functools
import re
from pathlib import Path
from typing import Any
from urllib.parse import urlsplit

import yaml
from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator


class StrategyDefinition(BaseModel):
    model_config = ConfigDict(extra="forbid")

    driver: str = Field(min_length=1)
    params: dict[str, Any] = Field(default_factory=dict)


class ProviderDefinition(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: str
    name: str = Field(min_length=1)
    base_url: str
    allowed_hosts: list[str]
    default_language: str
    recommended_limit: int
    requires_browser: bool
    datacenter_waf_sensitive: bool
    strategies: list[StrategyDefinition]

    @field_validator("id")
    @classmethod
    def validate_id(cls, value: str) -> str:
        if not re.fullmatch(r"[a-z][a-z0-9_]*", value):
            raise ValueError("provider id must be a lowercase snake-case identifier")
        return value

    @field_validator("base_url")
    @classmethod
    def validate_https_base_url(cls, value: str) -> str:
        parsed = urlsplit(value)
        if parsed.scheme != "https" or not parsed.hostname:
            raise ValueError("base_url must be an absolute HTTPS URL")
        return value

    @field_validator("allowed_hosts")
    @classmethod
    def validate_allowed_hosts(cls, values: list[str]) -> list[str]:
        if not values:
            raise ValueError("allowed_hosts must not be empty")
        normalized: list[str] = []
        for value in values:
            host = value.casefold().strip().rstrip(".")
            labels = host.split(".")
            if (
                not host
                or len(host) > 253
                or any(
                    not re.fullmatch(r"[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?", label)
                    for label in labels
                )
            ):
                raise ValueError(
                    "allowed_hosts entries must be valid hostnames without schemes or ports"
                )
            normalized.append(host)
        if len(set(normalized)) != len(normalized):
            raise ValueError("allowed_hosts entries must be unique")
        return normalized

    @field_validator("default_language")
    @classmethod
    def validate_default_language(cls, value: str) -> str:
        language = value.strip().casefold()
        if not re.fullmatch(r"[a-z]{2}", language):
            raise ValueError("default_language must be a two-letter ISO 639-1 code")
        return language

    @field_validator("recommended_limit")
    @classmethod
    def validate_recommended_limit(cls, value: int) -> int:
        if value < 1:
            raise ValueError("recommended_limit must be positive")
        return value

    @model_validator(mode="after")
    def validate_base_host(self) -> ProviderDefinition:
        base_host = urlsplit(self.base_url).hostname
        if base_host is None or base_host.casefold() not in self.allowed_hosts:
            raise ValueError("base_url hostname must be included in allowed_hosts")
        if not self.strategies:
            raise ValueError("providers must define at least one strategy")
        return self


@functools.lru_cache(maxsize=1)
def load_provider_manifest() -> dict[str, ProviderDefinition]:
    path = Path(__file__).resolve().parent.parent / "mappings" / "providers.yml"
    if not path.is_file():
        raise FileNotFoundError(f"Provider manifest not found: {path}")
    raw = yaml.safe_load(path.read_text(encoding="utf-8"))
    if not isinstance(raw, dict) or not isinstance(raw.get("providers"), list):
        raise ValueError("providers.yml must contain a 'providers' list")

    definitions: dict[str, ProviderDefinition] = {}
    for entry in raw["providers"]:
        definition = ProviderDefinition.model_validate(entry)
        if definition.id in definitions:
            raise ValueError(f"Duplicate provider id: {definition.id}")
        definitions[definition.id] = definition
    return definitions
