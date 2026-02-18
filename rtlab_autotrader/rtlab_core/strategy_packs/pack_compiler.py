from __future__ import annotations

import json
from pathlib import Path

from rtlab_core.strategy_packs.pack_loader import PackDocument


def compile_pack(pack: PackDocument, output_dir: str | Path) -> Path:
    out_dir = Path(output_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    out_path = out_dir / f"{pack.spec.metadata.name}_{pack.spec.metadata.version}.json"
    payload = {
        "metadata": pack.spec.metadata.model_dump(),
        "universe": pack.spec.universe.model_dump(),
        "microstructure": pack.spec.microstructure.model_dump(),
        "params": pack.spec.params,
        "rules": pack.rules,
    }
    out_path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    return out_path
