"""storage.py — Espaço em disco: conferir antes de gravar, para nunca deixar arquivo pela metade.

    ensure_free_space(destino, bytes_necessários, "save")     # levanta InsufficientDiskSpace
    ensure_free_space(destino, estimate_open(arquivo), "open")

Só a biblioteca padrão. `what` é o nome da operação ("save", "save_as", "export", "open",
"import"); a tela traduz pelo código e pelos valores de `InsufficientDiskSpace.params`.
"""

from __future__ import annotations

import shutil
import struct
from pathlib import Path

MARGIN_FIXED = 64 * 1024 * 1024      # folga fixa somada a toda estimativa
MARGIN_RATIO = 0.10                  # e 10% do estimado
_OPEN_FACTOR = 3                     # sem tamanho no cabeçalho (xz): descompactado ≈ 3× o arquivo

_WHAT_PT = {"save": "salvar", "save_as": "salvar como", "export": "exportar", "open": "abrir o arquivo",
            "import": "importar"}


class InsufficientDiskSpace(OSError):
    """Não há espaço livre para a operação. Nada foi criado."""

    code = "insufficient_disk_space"

    def __init__(self, what: str, needed: int, free: int, path: "str | Path"):
        self.what, self.needed, self.free, self.path = what, int(needed), int(free), str(path)
        super().__init__(
            f"Espaço em disco insuficiente para {_WHAT_PT.get(what, what)}: precisa de cerca de "
            f"{self.needed / 1e6:.0f} MB e há {self.free / 1e6:.0f} MB livres em {self.path}.")

    @property
    def params(self) -> dict:
        """Valores para a mensagem traduzida na tela."""
        return {"what": self.what, "needed_mb": round(self.needed / 1e6), "free_mb": round(self.free / 1e6),
                "path": self.path}


def free_bytes(path: "str | Path") -> int:
    """Espaço livre no disco onde `path` está (ou estaria: sobe até uma pasta que exista)."""
    p = Path(path).expanduser()
    while not p.exists() and p != p.parent:
        p = p.parent
    return shutil.disk_usage(p).free


def with_margin(nbytes: int) -> int:
    """Estimativa + folga (fixa + 10%)."""
    return int(nbytes * (1 + MARGIN_RATIO)) + MARGIN_FIXED


def ensure_free_space(path: "str | Path", needed_bytes: int, what: str = "") -> None:
    """Levanta `InsufficientDiskSpace` se o disco de `path` não comporta `needed_bytes` (já com folga).
    Não cria nada: `path` pode ainda não existir."""
    free = free_bytes(path)
    if free < needed_bytes:
        raise InsufficientDiskSpace(what, needed_bytes, free, path)


def gzip_uncompressed_size(path: "str | Path") -> int | None:
    """Tamanho descompactado lido do fim do arquivo gzip (ISIZE, módulo 2³²); None se não for gzip."""
    p = Path(path).expanduser()
    with p.open("rb") as fh:
        if fh.read(2) != b"\x1f\x8b":
            return None
        fh.seek(-4, 2)
        return struct.unpack("<I", fh.read(4))[0]


def estimate_open(path: "str | Path") -> int:
    """Espaço para descompactar um projeto: o tamanho do cabeçalho gzip quando plausível (o campo
    tem 32 bits; menor que o arquivo compactado indica que deu a volta), senão 3× o arquivo."""
    p = Path(path).expanduser()
    size = p.stat().st_size
    isize = gzip_uncompressed_size(p)
    if isize is not None and isize >= size:
        return with_margin(isize)
    return with_margin(size * _OPEN_FACTOR)
