"""
layers.py — Camadas de anotação: do JSONL canônico às tabelas `layers`/`tokens`.

Uma camada é o resultado de uma ferramenta (tagger) sobre um documento. É
identificada por `(texto, ferramenta, versão, modelo, config_hash)`: se já
existe uma camada com essa chave para o mesmo texto, não é preciso etiquetar
de novo (novomodelo.md §9.4 e §11.4).

Só as opções que mudam o resultado entram no `config_hash`; opções de
desempenho (dispositivo, processos, lote) ficam de fora.
"""

from __future__ import annotations

import hashlib
import json
from typing import Any

# Chaves do metadado JSONL que identificam o arquivo, não a configuração
_BASE_META_KEYS = {"type", "tagger", "tagger_version", "filename"}
# Opções de desempenho: guardadas na config, mas fora do config_hash
PERFORMANCE_KEYS = {"device", "use_gpu", "n_processes", "batch_size", "combined_pass"}
# Chaves que indicam o modelo usado
_MODEL_KEYS = ("model", "spacy_model", "stanza_model")

# Colunas de `tokens` preenchidas a partir de cada token JSONL
TOKEN_FIELDS = ("start_char", "end_char", "word", "lemma", "upos", "xpos", "feats", "tags")


def text_hash(text: str) -> str:
    """SHA-256 do texto (UTF-8), usado para saber se um documento mudou."""
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def config_hash(config: dict[str, Any]) -> str:
    """Hash estável das opções que mudam o resultado (sem as de desempenho)."""
    relevant = {k: v for k, v in config.items() if k not in PERFORMANCE_KEYS}
    canonical = json.dumps(relevant, sort_keys=True, ensure_ascii=False, separators=(",", ":"))
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()[:16]


def parse_tagged_jsonl(content: str) -> tuple[dict, list[dict]] | None:
    """Lê o conteúdo de um arquivo etiquetado JSONL. Devolve None para o TSV antigo."""
    first, _, rest = content.partition("\n")
    first = first.strip()
    if not first.startswith("{"):
        return None
    try:
        meta = json.loads(first)
    except json.JSONDecodeError:
        return None
    if meta.get("type") != "metadata":
        return None
    tokens = [json.loads(line) for line in rest.splitlines() if line.strip()]
    return meta, tokens


def layer_info(meta: dict) -> dict[str, Any]:
    """Ferramenta, versão, modelo, configuração efetiva e config_hash de um metadado JSONL."""
    config = {k: v for k, v in meta.items() if k not in _BASE_META_KEYS}
    model = next((str(meta[k]) for k in _MODEL_KEYS if meta.get(k)), "")
    return {
        "tool": meta.get("tagger", ""),
        "tool_version": str(meta.get("tagger_version", "")),
        "model": model,
        "config": config,
        "config_hash": config_hash(config),
    }


def token_row(tok: dict) -> tuple:
    """Token JSONL → valores das colunas de `tokens` (sem layer_id/idx/doc_id) + `extra`.

    - `xpos` vazio vira NULL; o spaCy grava a etiqueta Penn como `ptb`.
    - `tags` e `feats` estruturados são guardados em JSON.
    - Campos desconhecidos vão para `extra` (JSON), para não perder nada.
    """
    extra = {k: v for k, v in tok.items() if k not in TOKEN_FIELDS}
    xpos = tok.get("xpos") or None
    if xpos is None and tok.get("ptb"):
        xpos = extra.pop("ptb")
    feats = tok.get("feats")
    if feats is not None and not isinstance(feats, str):
        feats = json.dumps(feats, ensure_ascii=False)
    tags = tok.get("tags")
    return (
        tok.get("start_char"),
        tok.get("end_char"),
        tok.get("word"),
        tok.get("lemma") or None,
        tok.get("upos") or None,
        xpos,
        feats,
        json.dumps(tags, ensure_ascii=False) if tags is not None else None,
        json.dumps(extra, ensure_ascii=False) if extra else None,
    )
