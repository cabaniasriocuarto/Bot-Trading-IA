from __future__ import annotations

from typing import Any

from pydantic import BaseModel, ConfigDict, Field


class PackMetadata(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str
    version: str
    market: str
    timeframes: list[str]


class PackUniverse(BaseModel):
    model_config = ConfigDict(extra="allow")

    min_volume_24h_usd: float = Field(default=0.0, ge=0)
    max_spread_bps: float = Field(default=30.0, ge=0)


class PackMicrostructure(BaseModel):
    model_config = ConfigDict(extra="allow")

    enable_vpin: bool = True
    enable_obi: bool = True
    enable_cvd: bool = True


class PackSpec(BaseModel):
    model_config = ConfigDict(extra="allow")

    metadata: PackMetadata
    universe: PackUniverse = Field(default_factory=PackUniverse)
    microstructure: PackMicrostructure = Field(default_factory=PackMicrostructure)
    params: dict[str, Any] = Field(default_factory=dict)
