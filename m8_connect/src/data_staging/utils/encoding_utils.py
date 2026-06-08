"""Detección de codificación para archivos de texto/CSV."""

from __future__ import annotations

from pathlib import Path
from typing import Union

import chardet

_ENCODING_ALIASES = {
    "utf8": "utf-8",
    "iso-8859-1": "latin-1",
    "iso8859-1": "latin-1",
    "windows-1252": "cp1252",
    "ascii": "utf-8",
}


def normalize_encoding_name(encoding: str | None) -> str:
    if not encoding:
        return "utf-8"
    key = str(encoding).strip().lower().replace("_", "-")
    return _ENCODING_ALIASES.get(key, key)


def detect_file_encoding(
    file_path: Union[str, Path],
    sample_size: int = 262_144,
) -> str:
    """
    Detecta la codificación de un archivo de texto.

    Prioridad: BOM UTF-8 → UTF-8 válido (estricto) → chardet con confianza → cp1252 → latin-1.
    Evita usar latin-1 en archivos UTF-8 solo porque Polars no lanza error al leerlos.
    """
    path = Path(file_path)
    if not path.is_file():
        return "utf-8"

    with path.open("rb") as f:
        raw = f.read(sample_size)

    if not raw:
        return "utf-8"

    if raw.startswith(b"\xef\xbb\xbf"):
        # BOM: leer como UTF-8 (Polars/python aceptan utf8 y omiten el BOM).
        return "utf-8"

    try:
        raw.decode("utf-8")
        return "utf-8"
    except UnicodeDecodeError:
        pass

    detected = chardet.detect(raw)
    enc = normalize_encoding_name(detected.get("encoding"))
    confidence = float(detected.get("confidence") or 0.0)

    if enc in ("utf-8", "utf-8-sig"):
        return "utf-8"

    if confidence >= 0.7:
        try:
            raw.decode(enc)
            # Excel en Windows (español) suele ser cp1252, no ISO-8859-1.
            if enc == "latin-1":
                try:
                    raw.decode("cp1252")
                    return "cp1252"
                except UnicodeDecodeError:
                    pass
            return enc
        except (UnicodeDecodeError, LookupError):
            pass

    for fallback in ("cp1252", "latin-1"):
        try:
            raw.decode(fallback)
            return fallback
        except UnicodeDecodeError:
            continue

    return "utf-8"


_POLARS_ENCODING = {
    "utf-8": "utf8",
    "utf-8-sig": "utf8",
    "cp1252": "windows-1252",
    "latin-1": "latin1",
}


def encoding_for_polars(encoding: str) -> str:
    """Nombre de encoding aceptado por Polars."""
    enc = normalize_encoding_name(encoding)
    return _POLARS_ENCODING.get(enc, enc.replace("-", ""))


def encoding_for_python(encoding: str) -> str:
    """Nombre de encoding para open() / csv de la stdlib."""
    enc = normalize_encoding_name(encoding)
    if enc == "utf-8-sig":
        return "utf-8-sig"
    return enc


_MOJIBAKE_MARKERS = ("Ã¡", "Ã©", "Ã­", "Ã³", "Ãº", "Ã±", "Ã¼", "Ã")


def looks_like_mojibake(value: str) -> bool:
    return bool(value) and any(marker in value for marker in _MOJIBAKE_MARKERS)


def repair_mojibake_text(value: str) -> str:
    """
    Corrige texto UTF-8 leído erróneamente como latin-1/cp1252 (ej. CuliacÃ¡n → Culiacán).
    """
    if not isinstance(value, str) or not looks_like_mojibake(value):
        return value
    try:
        return value.encode("latin-1").decode("utf-8")
    except (UnicodeDecodeError, UnicodeEncodeError):
        return value
