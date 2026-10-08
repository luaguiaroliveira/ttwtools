"""Contorno para o BiberPlus 0.4.0 no Windows.

``biberplus.tagger.tagger_utils.build_variable_dictionaries`` extrai o nome de cada lista de
``constants/*.txt`` com ``split('/')``; no Windows ``glob`` devolve barras invertidas, a chave vira o
caminho inteiro e o tagger falha com ``KeyError: 'quantifiers'``. Troca a função (e as cópias importadas
por ``from ... import``) por uma que usa ``os.path``; nos outros sistemas não faz nada.
"""

from __future__ import annotations

import os
import sys
from glob import glob

_applied = False


def apply() -> None:
    global _applied
    if _applied or sys.platform != "win32":
        return
    _applied = True
    try:
        from biberplus.tagger import tagger_utils
    except ImportError:
        return

    def build_variable_dictionaries():
        folder = os.path.join(os.path.dirname(tagger_utils.__file__), "constants")
        return {os.path.splitext(os.path.basename(f))[0]: tagger_utils.read_in_variables(f)
                for f in glob(os.path.join(folder, "*.txt"))}

    import importlib
    tagger_utils.build_variable_dictionaries = build_variable_dictionaries
    for name in ("tagger", "function_words_tagger", "tag_frequencies"):
        try:
            mod = importlib.import_module(f"biberplus.tagger.{name}")
        except ImportError:
            continue
        if hasattr(mod, "build_variable_dictionaries"):
            mod.build_variable_dictionaries = build_variable_dictionaries
