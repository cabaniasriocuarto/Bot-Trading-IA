from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from .checkpoint import CheckpointStore
from .graphql import GraphQLClient
from .runtime import SnapshotContext
from .schema import SchemaCatalog


@dataclass(slots=True)
class ExportSession:
    context: SnapshotContext
    client: GraphQLClient
    catalog: SchemaCatalog
    checkpoint: CheckpointStore
    attachment_candidates: list[dict[str, Any]] = field(default_factory=list)
    viewer: dict[str, Any] | None = None
    organization: dict[str, Any] | None = None

    def add_attachment_candidate(self, candidate: dict[str, Any]) -> None:
        self.attachment_candidates.append(candidate)

