"""
formats — Entrada e saída em formatos de corpus (novomodelo.md §9.2).

    conllu       leitura (vira documento + camada) e escrita a partir de uma camada (UD)
    vrt          escrita (CWB, Sketch Engine, CQPweb)
    nltk_tagged  leitura de texto anotado palavra/TAG (Brown, LOB)
    tables       tabela de tokens em CSV, JSONL ou Parquet (se houver pyarrow)
"""

from .common import document_layers, sentences_of
from .conllu import export_conllu, import_conllu, parse_conllu, write_conllu
from .nltk_tagged import import_nltk_tagged, parse_nltk_tagged
from .tables import export_tokens
from .vrt import export_vrt

__all__ = [
    "document_layers", "sentences_of",
    "parse_conllu", "import_conllu", "write_conllu", "export_conllu",
    "parse_nltk_tagged", "import_nltk_tagged",
    "export_vrt", "export_tokens",
]
