#!/usr/bin/env python
from __future__ import annotations

import argparse
import hashlib
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable


def _sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as fh:
        for chunk in iter(lambda: fh.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def _safe_name(text: str) -> str:
    text = re.sub(r"[^A-Za-z0-9._-]+", "_", text.strip())
    return text.strip("._") or "biblio"


def _iter_source_files(input_dirs: Iterable[Path]) -> list[Path]:
    out: list[Path] = []
    seen: set[str] = set()
    for root in input_dirs:
        if not root.exists():
            continue
        for path in sorted(root.rglob("*")):
            if not path.is_file():
                continue
            if path.suffix.lower() not in {".pdf", ".txt"}:
                continue
            key = str(path.resolve())
            if key in seen:
                continue
            seen.add(key)
            out.append(path.resolve())
    return out


def _extract_pdf_text(pdf_path: Path) -> tuple[str | None, str]:
    try:
        from pypdf import PdfReader  # type: ignore
    except Exception:
        return None, "no_pdf_parser"
    try:
        reader = PdfReader(str(pdf_path))
        parts: list[str] = []
        for page in reader.pages:
            parts.append(page.extract_text() or "")
        return "\n\n".join(parts).strip(), "ok"
    except Exception as exc:
        return None, f"extract_error:{exc}"


@dataclass
class BiblioRow:
    source_path: Path
    file_type: str
    source_sha256: str
    txt_path: Path | None
    txt_sha256: str | None
    txt_status: str


def _process_file(path: Path, txt_out_dir: Path) -> BiblioRow:
    source_sha = _sha256(path)
    suffix = path.suffix.lower()
    if suffix == ".txt":
        txt_name = f"{_safe_name(path.stem)}.txt"
        target = txt_out_dir / txt_name
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(path.read_text(encoding="utf-8", errors="replace"), encoding="utf-8")
        txt_sha = _sha256(target)
        return BiblioRow(
            source_path=path,
            file_type="txt",
            source_sha256=source_sha,
            txt_path=target,
            txt_sha256=txt_sha,
            txt_status="copied",
        )

    text, status = _extract_pdf_text(path)
    if text is None:
        return BiblioRow(
            source_path=path,
            file_type="pdf",
            source_sha256=source_sha,
            txt_path=None,
            txt_sha256=None,
            txt_status=status,
        )
    txt_name = f"{_safe_name(path.stem)}.txt"
    target = txt_out_dir / txt_name
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(text, encoding="utf-8")
    txt_sha = _sha256(target)
    return BiblioRow(
        source_path=path,
        file_type="pdf",
        source_sha256=source_sha,
        txt_path=target,
        txt_sha256=txt_sha,
        txt_status="extracted",
    )


def _render_index(rows: list[BiblioRow], *, generated_at: str, txt_out_dir: Path, input_dirs: list[Path]) -> str:
    lines: list[str] = []
    lines.append("# BIBLIO INDEX (SHA256)")
    lines.append("")
    lines.append(f"Generado: `{generated_at}`")
    lines.append("")
    lines.append("## Alcance")
    lines.append("- Fuentes locales detectadas en directorios configurados.")
    lines.append(f"- Texto extraído/copiado en `{txt_out_dir.as_posix()}` (ignorado por git).")
    lines.append("- Si un PDF no puede parsearse, queda `txt_status=no_pdf_parser` o `extract_error:*`.")
    lines.append("")
    lines.append("## Directorios escaneados")
    for root in input_dirs:
        lines.append(f"- `{root}`")
    lines.append("")
    lines.append("## Índice")
    lines.append("")
    lines.append("| # | Tipo | Archivo | Source SHA256 | TXT SHA256 | TXT status |")
    lines.append("|---|---|---|---|---|---|")
    for idx, row in enumerate(rows, start=1):
        file_name = row.source_path.name.replace("|", "\\|")
        source_ref = str(row.source_path).replace("|", "\\|")
        txt_sha = row.txt_sha256 or "-"
        lines.append(
            f"| {idx} | {row.file_type} | `{file_name}`<br/>`{source_ref}` | `{row.source_sha256}` | `{txt_sha}` | `{row.txt_status}` |"
        )
    lines.append("")
    return "\n".join(lines) + "\n"


def main() -> int:
    parser = argparse.ArgumentParser(description="Extrae/cataloga bibliografía local y genera índice SHA256.")
    parser.add_argument(
        "--input-dir",
        action="append",
        dest="input_dirs",
        default=[],
        help="Directorio a escanear (se puede repetir).",
    )
    parser.add_argument(
        "--index-out",
        default="docs/reference/BIBLIO_INDEX.md",
        help="Ruta de salida para el índice markdown.",
    )
    parser.add_argument(
        "--txt-out-dir",
        default="docs/reference/biblio_txt",
        help="Directorio de salida para .txt extraídos/copiados.",
    )
    args = parser.parse_args()

    roots = [Path(p).resolve() for p in args.input_dirs] if args.input_dirs else []
    if not roots:
        roots = [Path("docs/reference/biblio_raw").resolve()]
    txt_out_dir = Path(args.txt_out_dir).resolve()
    index_out = Path(args.index_out).resolve()

    source_files = _iter_source_files(roots)
    rows = [_process_file(path, txt_out_dir) for path in source_files]
    from datetime import datetime, timezone

    generated_at = datetime.now(timezone.utc).isoformat()
    markdown = _render_index(rows, generated_at=generated_at, txt_out_dir=txt_out_dir, input_dirs=roots)
    index_out.parent.mkdir(parents=True, exist_ok=True)
    index_out.write_text(markdown, encoding="utf-8")
    print(f"[biblio] index: {index_out}")
    print(f"[biblio] files indexed: {len(rows)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
