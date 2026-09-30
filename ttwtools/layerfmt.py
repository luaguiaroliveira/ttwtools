"""layerfmt.py — Formato colunar das camadas empacotadas (`layer_blobs`), versão `TCL1`.

`TCL` = *TTWtools Columnar Layer*: nome próprio deste projeto (não é um formato ou pacote externo, nem tem
relação com a linguagem Tcl). `TCL1` é também o código de 4 bytes que abre cada blob; mantido por
compatibilidade com os arquivos já gravados.

Cada camada vira uma tabela de colunas, em vez de uma lista JSON de linhas:

    blob = layerfmt.encode(rows)      # rows: linhas de `tokens` (start, end, word, lemma, upos, xpos, feats, tags, extra)
    rows = layerfmt.decode(blob)      # lista de listas, igual à do JSON antigo

Por que é menor: as formas, lemas e etiquetas se repetem, então cada coluna de texto guarda um
dicionário local (valores distintos, uma vez) e um índice de 2 ou 4 bytes por token; as posições
viram diferenças pequenas; e o conjunto todo passa por zlib. Numa camada de 3,76 M de tokens:
219,9 MB (JSON) → cerca de 15 MB (ver o plano de armazenamento, passo A5).

Formato do blob: `b"TCL1"` + zlib( n:u32, 2 colunas de int32 (início e tamanho) e 7 colunas de
texto (n_dic:u32, dicionário em JSON, largura do índice:u8, índices) ). Little-endian, só
biblioteca padrão. `decode` aceita também o blob antigo (zlib de JSON), para ler arquivos
antigos para sempre. Um blob só de versão anterior do TTWtools não abre este formato.
"""

from __future__ import annotations

import json
import struct
import sys
import zlib
from array import array
from typing import Sequence

MAGIC = b"TCL1"
N_COLUMNS = 9                       # start_char, end_char, word, lemma, upos, xpos, feats, tags, extra
_NONE = -(2 ** 31)                  # None nas colunas de inteiros
_LEVEL = 6


def is_columnar(blob: bytes) -> bool:
    """O blob está no formato colunar (e não no JSON antigo)?"""
    return bytes(blob[:4]) == MAGIC


def _le(a: array) -> bytes:
    if sys.byteorder == "big":
        a = array(a.typecode, a)
        a.byteswap()
    return a.tobytes()


def _from_le(typecode: str, raw: bytes) -> array:
    a = array(typecode)
    a.frombytes(raw)
    if sys.byteorder == "big":
        a.byteswap()
    return a


def _int_col(values: Sequence) -> array:
    out = array("i")
    for v in values:
        if v is None:
            out.append(_NONE)
        elif type(v) is int and _NONE < v < 2 ** 31:
            out.append(v)
        else:
            raise ValueError(f"valor não inteiro numa coluna de posição: {v!r}")
    return out


def encode(rows: Sequence[Sequence]) -> bytes:
    """Linhas de tokens → blob colunar. ValueError se as linhas não têm o formato esperado (quem grava
    pode cair no JSON antigo)."""
    n = len(rows)
    for r in rows:
        if len(r) != N_COLUMNS:
            raise ValueError(f"linha de token com {len(r)} colunas (esperado {N_COLUMNS})")
    starts = [r[0] for r in rows]
    ends = [r[1] for r in rows]
    # início como diferença do início anterior; fim como tamanho do token: números pequenos comprimem bem
    prev, d_start = 0, []
    for v in starts:
        d_start.append(None if v is None else v - prev)
        prev = prev if v is None else v
    length = [None if e is None or s is None else e - s for s, e in zip(starts, ends)]
    parts = [struct.pack("<I", n), _le(_int_col(d_start)), _le(_int_col(length))]
    for c in range(2, N_COLUMNS):
        ids: dict = {}
        idx = array("I")
        for r in rows:
            v = r[c]
            if v is None:
                idx.append(0)
                continue
            if type(v) is not str:
                raise ValueError(f"valor não textual numa coluna de texto: {v!r}")
            i = ids.get(v)
            if i is None:
                i = ids[v] = len(ids) + 1        # 0 é o None
            idx.append(i)
        dic = json.dumps(list(ids), ensure_ascii=False, separators=(",", ":")).encode("utf-8")
        width = 2 if len(ids) < 65536 else 4
        body = _le(array("H", idx)) if width == 2 else _le(idx)
        parts += [struct.pack("<IB", len(dic), width), dic, body]
    return MAGIC + zlib.compress(b"".join(parts), _LEVEL)


def decode(blob: bytes) -> list[list]:
    """Blob → linhas de tokens (listas de 9 valores). Aceita o formato colunar e o JSON antigo."""
    blob = bytes(blob)
    if not is_columnar(blob):
        return json.loads(zlib.decompress(blob).decode("utf-8"))
    buf = memoryview(zlib.decompress(blob[4:]))
    (n,) = struct.unpack_from("<I", buf, 0)
    pos = 4
    ints = []
    for _ in range(2):
        ints.append(_from_le("i", bytes(buf[pos:pos + 4 * n])))
        pos += 4 * n
    d_start, length = ints
    starts: list = []
    prev = 0
    for d in d_start:
        if d == _NONE:
            starts.append(None)
        else:
            prev += d
            starts.append(prev)
    ends = [None if (ln == _NONE or s is None) else s + ln for s, ln in zip(starts, length)]
    cols: list = [starts, ends]
    for _ in range(2, N_COLUMNS):
        n_dic, width = struct.unpack_from("<IB", buf, pos)
        pos += 5
        values = [None] + json.loads(bytes(buf[pos:pos + n_dic]).decode("utf-8"))
        pos += n_dic
        idx = _from_le("H" if width == 2 else "I", bytes(buf[pos:pos + width * n]))
        pos += width * n
        cols.append([values[i] for i in idx])
    return [list(r) for r in zip(*cols)] if n else []
