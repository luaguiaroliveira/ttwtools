"""storage.py — Espaço em disco: conferir antes de gravar, para nunca deixar arquivo pela metade.

    ensure_free_space(destino, bytes_necessários, "save")     # levanta InsufficientDiskSpace
    ensure_free_space(destino, estimate_open(arquivo), "open")

Também reúne as pastas do aplicativo: de trabalho (temporárias, com dono) e o cache (índices e
derivados, com limite e limpeza). Só a biblioteca padrão. `what` é o nome da operação ("save", "save_as", "export", "open",
"import"); a tela traduz pelo código e pelos valores de `InsufficientDiskSpace.params`.
"""

from __future__ import annotations

import os
import shutil
import struct
import tempfile
import time
from pathlib import Path

MARGIN_FIXED = 64 * 1024 * 1024      # folga fixa somada a toda estimativa
MARGIN_RATIO = 0.10                  # e 10% do estimado
_OPEN_FACTOR = 3                     # sem tamanho no cabeçalho (xz): descompactado ≈ 3× o arquivo

_WHAT_PT = {"save": "salvar", "save_as": "salvar como", "export": "exportar", "open": "abrir o arquivo",
            "import": "importar", "index": "criar o índice de busca"}


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


# ---------------------------------------------------------------------------
# Pastas de trabalho (temporárias, com dono)
# ---------------------------------------------------------------------------

WORKDIR_PREFIXES = {"work": "ttw_work_", "export": "ttw_export_", "pack": "ttw_pack_"}
OWNER_FILE = "owner.pid"
last_purge = {"count": 0, "bytes": 0}      # o que a última limpeza de órfãs apagou (o app avisa ao iniciar)


def make_workdir(prefix: str = "ttw_work_") -> Path:
    """Pasta temporária com `owner.pid` (o processo dono). Se o processo morrer sem limpar,
    `purge_orphans()` reconhece a pasta como abandonada, sem esperar horas."""
    d = Path(tempfile.mkdtemp(prefix=prefix))
    (d / OWNER_FILE).write_text(str(os.getpid()))
    return d


def workdir(kind: str = "work") -> Path:
    """Nova pasta de trabalho de um tipo: "work" (cópia de trabalho), "export" ou "pack" (empacotamento)."""
    return make_workdir(WORKDIR_PREFIXES[kind])


def _pid_alive(pid: int) -> bool:
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    except PermissionError:
        return True
    except OSError:
        return False
    return True


def dir_size(path: "str | Path") -> int:
    """Tamanho total dos arquivos de uma pasta (ou do arquivo)."""
    p = Path(path)
    if p.is_file():
        return p.stat().st_size
    total = 0
    for root, _dirs, files in os.walk(p):
        for f in files:
            try:
                total += os.lstat(os.path.join(root, f)).st_size
            except OSError:
                pass
    return total


def _owner(d: Path) -> int | None:
    try:
        return int((d / OWNER_FILE).read_text().strip() or 0) or None
    except (OSError, ValueError):
        return None


def list_workdirs(prefixes: "tuple[str, ...] | None" = None) -> list[dict]:
    """Pastas de trabalho na pasta temporária: caminho, tipo, bytes, pid do dono, se o dono vive
    (None sem marca), idade em horas e `mine` (deste processo)."""
    prefixes = prefixes or tuple(WORKDIR_PREFIXES.values())
    kinds = {v: k for k, v in WORKDIR_PREFIXES.items()}
    out = []
    for d in sorted(Path(tempfile.gettempdir()).glob("ttw_*")):
        pre = next((p for p in prefixes if d.name.startswith(p)), None)
        if pre is None or not d.is_dir():
            continue
        pid = _owner(d)
        out.append({"path": str(d), "kind": kinds.get(pre, pre), "bytes": dir_size(d), "pid": pid,
                    "alive": _pid_alive(pid) if pid else None,
                    "age_hours": round((time.time() - d.stat().st_mtime) / 3600, 2),
                    "mine": pid == os.getpid()})
    return out


def purge_orphans(prefixes: "tuple[str, ...] | None" = None, max_age_hours: float = 24) -> int:
    """Apaga pastas de trabalho abandonadas: as de processo que já morreu (marca `owner.pid`) e, sem
    marca (versões antigas), as com mais de `max_age_hours`. As de processos vivos ficam. Devolve
    quantas apagou; `last_purge` guarda também os bytes."""
    n = freed = 0
    for w in list_workdirs(prefixes):
        dead = (w["alive"] is False) if w["pid"] else w["age_hours"] > max_age_hours
        if dead:
            shutil.rmtree(w["path"], ignore_errors=True)
            n += 1
            freed += w["bytes"]
    last_purge.update(count=n, bytes=freed)
    return n


def release_own_workdirs() -> int:
    """Apaga as pastas de trabalho deste processo (ao sair)."""
    n = 0
    for w in list_workdirs():
        if w["mine"]:
            shutil.rmtree(w["path"], ignore_errors=True)
            n += 1
    return n


# ---------------------------------------------------------------------------
# Cache (índices e derivados: recriáveis, com limite e limpeza LRU)
# ---------------------------------------------------------------------------

DEFAULT_CACHE_LIMIT_MB = 5120
_LAST_USED = ".last_used"


def cache_dir() -> Path:
    """Pasta do cache (recriável). TTWTOOLS_CACHE_DIR a muda; padrão: pasta de cache do usuário."""
    if os.environ.get("TTWTOOLS_CACHE_DIR"):
        base = Path(os.environ["TTWTOOLS_CACHE_DIR"])
    else:
        import platformdirs
        base = Path(platformdirs.user_cache_dir("TTWtools", appauthor=False))
    base.mkdir(parents=True, exist_ok=True)
    return base


def cache_limit() -> int:
    """Limite do cache em bytes: `cache_limit_mb` do settings.json (padrão 5 GB)."""
    from .corpus_catalog import settings
    return int(float(settings().get("cache_limit_mb") or DEFAULT_CACHE_LIMIT_MB) * 1024 * 1024)


def cache_entry(key: str) -> Path:
    """Pasta do item `key` do cache (criada se preciso); marca o uso agora."""
    d = cache_dir() / key
    d.mkdir(parents=True, exist_ok=True)
    touch_cache(key)
    return d


def touch_cache(key: str) -> None:
    (cache_dir() / key / _LAST_USED).write_text(str(time.time()))


def cache_entries() -> list[dict]:
    """Itens do cache, do menos ao mais recentemente usado: key, bytes, last_used (epoch)."""
    out = []
    for d in cache_dir().iterdir():
        if not d.is_dir():
            continue
        mark = d / _LAST_USED
        used = mark.stat().st_mtime if mark.exists() else d.stat().st_mtime
        out.append({"key": d.name, "bytes": dir_size(d), "last_used": used})
    return sorted(out, key=lambda e: e["last_used"])


def enforce_cache_limit(limit: int | None = None, keep: "tuple[str, ...]" = ()) -> list[str]:
    """Remove os itens menos usados até o cache caber no limite. `keep`: chaves que não saem (em uso
    agora). Devolve as chaves removidas."""
    limit = cache_limit() if limit is None else limit
    entries = cache_entries()
    total = sum(e["bytes"] for e in entries)
    removed = []
    for e in entries:
        if total <= limit:
            break
        if e["key"] in keep:
            continue
        shutil.rmtree(cache_dir() / e["key"], ignore_errors=True)
        total -= e["bytes"]
        removed.append(e["key"])
    return removed


def clear_cache(key: str | None = None) -> int:
    """Apaga o cache (ou um item). Devolve os bytes liberados."""
    freed = 0
    for e in cache_entries():
        if key is None or e["key"] == key:
            shutil.rmtree(cache_dir() / e["key"], ignore_errors=True)
            freed += e["bytes"]
    return freed


def disk_usage(path: "str | Path | None" = None) -> dict:
    """Uso de disco do TTWtools: pastas de trabalho, cache e espaço livre (para a tela e `ttwtools cache list`)."""
    work = list_workdirs()
    cache = cache_entries()
    return {"workdirs": work, "workdirs_bytes": sum(w["bytes"] for w in work),
            "orphans_bytes": sum(w["bytes"] for w in work if (w["alive"] is False) or (w["pid"] is None and not w["mine"])),
            "cache": cache, "cache_bytes": sum(e["bytes"] for e in cache), "cache_limit_bytes": cache_limit(),
            "free_bytes": free_bytes(path or tempfile.gettempdir()), "last_purge": dict(last_purge)}


def cleanup(exit: bool = False) -> dict:
    """Limpeza ao iniciar (órfãs e limite do cache) ou ao sair (`exit=True`: também as pastas deste processo)."""
    own = release_own_workdirs() if exit else 0
    return {"orphans": purge_orphans(), "own": own, "cache_removed": enforce_cache_limit()}
