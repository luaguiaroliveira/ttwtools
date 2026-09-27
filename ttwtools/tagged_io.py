"""I/O utilities for the canonical JSONL tagged format used by all ttwtools taggers.

Format specification
--------------------
A tagged JSONL file contains one JSON object per line:

  Line 1  : metadata object — must include ``type="metadata"``, ``tagger``,
             ``tagger_version``, and ``filename``. Backend-specific keys
             (``stanza_model``, ``device``, ``spacy_model``, etc.) are optional.
             Unknown keys are silently ignored by readers.

  Lines 2+ : one token object per line with **at minimum**:

             ``start_char``  int  — inclusive start offset in the original .txt file
             ``end_char``    int  — exclusive end offset  (original[start:end] == word)
             ``word``        str  — surface form as it appears in the original file
             ``xpos``        str  — Penn Treebank POS tag, or "" if not available
             ``tags``        list — tagger-specific feature tags (may be empty list)

             Any extra fields (e.g. ``confidence``, ``t_start``) are preserved
             transparently.

Export formats (generated on demand)
-------------------------------------
  json  — single JSON object {"metadata": {…}, "tokens": […]}
  tsv   — tab-separated, tags flattened to space-separated string, metadata as comments
  csv   — comma-separated, same layout as tsv
"""

from __future__ import annotations

import csv
import json
from pathlib import Path
from typing import Any


def write_tagged_jsonl(
    metadata: dict[str, Any],
    tokens: list[dict[str, Any]],
    path: str | Path,
) -> None:
    """Write a canonical ttwtools tagged JSONL file.

    Parameters
    ----------
    metadata : dict — must contain at minimum ``tagger``, ``tagger_version``,
               ``filename``.  ``type="metadata"`` is added automatically.
    tokens   : list of token dicts (see module docstring for required fields).
    path     : destination file path; parent directories are created if needed.
    """
    path = Path(path).expanduser()
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as f:
        f.write(json.dumps({"type": "metadata", **metadata}, ensure_ascii=False))
        f.write("\n")
        for tok in tokens:
            f.write(json.dumps(tok, ensure_ascii=False))
            f.write("\n")


def read_tagged_jsonl(path: str | Path) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    """Read a canonical tagged JSONL file.

    Returns
    -------
    (metadata_dict, list_of_token_dicts)

    Raises
    ------
    ValueError  if the file appears to be in the legacy TSV format.
    """
    path = Path(path).expanduser()
    with path.open("r", encoding="utf-8") as f:
        first_line = f.readline().rstrip("\n")

        # Detect legacy TSV format (starts with "# filename:" comment or column header)
        if first_line.startswith("# filename:") or first_line.startswith("type\t"):
            raise ValueError(
                f"'{path.name}' appears to be in the legacy TSV format "
                "(type|content|tags). Re-process the original corpus to generate "
                "the current JSONL format."
            )

        metadata = json.loads(first_line)
        tokens = [json.loads(line) for line in f if line.strip()]

    return metadata, tokens


def export_tagged(
    jsonl_path: str | Path,
    fmt: str,
    out_path: str | Path | None = None,
) -> Path:
    """Export a JSONL tagged file to another format.

    Parameters
    ----------
    jsonl_path : path to the source ``.jsonl`` file.
    fmt        : one of ``"json"``, ``"tsv"``, ``"csv"``.
    out_path   : output path; if ``None``, derived from ``jsonl_path`` with the
                 new extension.

    Returns
    -------
    The output path (as a ``Path``).
    """
    if fmt not in {"json", "tsv", "csv"}:
        raise ValueError(f"fmt must be one of 'json', 'tsv', 'csv'; got {fmt!r}")

    jsonl_path = Path(jsonl_path)
    metadata, tokens = read_tagged_jsonl(jsonl_path)

    if out_path is None:
        out_path = jsonl_path.with_suffix(f".{fmt}")
    out_path = Path(out_path).expanduser()

    if fmt == "json":
        with out_path.open("w", encoding="utf-8") as f:
            json.dump(
                {"metadata": metadata, "tokens": tokens},
                f,
                ensure_ascii=False,
                indent=2,
            )

    elif fmt in {"tsv", "csv"}:
        sep = "\t" if fmt == "tsv" else ","

        # Collect any extra fields beyond the canonical four
        core = {"start_char", "end_char", "word", "xpos", "tags"}
        extra_fields: list[str] = []
        for tok in tokens:
            for k in tok:
                if k not in core and k not in extra_fields:
                    extra_fields.append(k)

        fieldnames = ["start_char", "end_char", "word", "xpos", "tags"] + extra_fields

        with out_path.open("w", encoding="utf-8", newline="") as f:
            # Write metadata as comment lines before the header
            for k, v in metadata.items():
                if k != "type":
                    f.write(f"# {k}: {v}\n")

            writer = csv.DictWriter(
                f,
                fieldnames=fieldnames,
                delimiter=sep,
                extrasaction="ignore",
                lineterminator="\n",
            )
            writer.writeheader()
            for tok in tokens:
                row = dict(tok)
                if isinstance(row.get("tags"), list):
                    row["tags"] = " ".join(row["tags"])
                writer.writerow(row)

    return out_path
