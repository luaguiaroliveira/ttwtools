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

`TCL2` (único formato gravado desde 2026-09-30; `TCL1` e o JSON antigo só são lidos): as colunas de texto
viram **ids inteiros** de um léxico compartilhado por corpus (`Lexicon`), que só cresce (ids estáveis:
blobs já gravados continuam válidos quando entram camadas novas). O léxico mora fora do blob (tabela
`lexicon_parts` do projeto, ver `project.LayerStore`); o blob guarda `b"TCL2"` + n:u32 + 9 colunas, cada uma
`largura:u8, tamanho:u32` + zlib, para decodificar só as colunas pedidas (`decode_ids`). Só biblioteca padrão.
"""

from __future__ import annotations

import json
import os
import struct
import sys
import zlib
from array import array
from typing import Sequence

MAGIC = b"TCL1"
MAGIC2 = b"TCL2"
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


def decode(blob: bytes, lex: "Lexicon | None" = None) -> list[list]:
    """Blob → linhas de tokens (listas de 9 valores). Aceita `TCL1`, o JSON antigo e, com o léxico do corpus, `TCL2`."""
    blob = bytes(blob)
    if is_tcl2(blob):
        if lex is None:
            raise ValueError("blob TCL2: informe o léxico do corpus (project.LayerStore.unpack)")
        return decode_tcl2(blob, lex)
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


# ---------------------------------------------------------------------------
# TCL2: ids de um léxico por corpus
# ---------------------------------------------------------------------------

def default_format() -> str:
    """Formato em que se gravam camadas: sempre `tcl2` (decidido: salvar só em TCL2). A leitura aceita os três.
    Os testes trocam esta função para gerar arquivos `TCL1` de antes."""
    return "tcl2"


def is_tcl2(blob: bytes) -> bool:
    return bytes(blob[:4]) == MAGIC2


class Lexicon:
    """Léxico de um corpus: para cada coluna de texto (2..8), a lista dos valores distintos; id 0 = None.
    Só cresce (ids estáveis). `pending` devolve o que ainda não foi gravado."""

    def __init__(self, values: "dict[int, list[str]] | None" = None):
        values = values or {}
        self.values: dict[int, list] = {c: [None] + list(values.get(c, [])) for c in range(2, N_COLUMNS)}
        self.index: dict[int, dict] = {}
        for c, vals in self.values.items():
            d = {v: i for i, v in enumerate(vals) if i}
            d[None] = 0
            self.index[c] = d
        self.saved: dict[int, int] = {c: len(v) - 1 for c, v in self.values.items()}

    def __len__(self) -> int:
        return sum(len(v) - 1 for v in self.values.values())

    def add(self, c: int, new: "Sequence[str]") -> None:
        vals, d = self.values[c], self.index[c]
        for v in new:
            d[v] = len(vals)
            vals.append(v)

    def pending(self) -> "dict[int, list[str]]":
        return {c: self.values[c][self.saved[c] + 1:] for c in self.values if len(self.values[c]) - 1 > self.saved[c]}

    def mark_saved(self) -> None:
        self.saved = {c: len(v) - 1 for c, v in self.values.items()}


_V2 = 0x80000000                    # bit alto de `n` no cabeçalho: layout v2 (posições relativas, `tags` derivável)
_NARROW = {1: ("b", -128), 2: ("h", -32768), 4: ("i", _NONE)}     # largura → (tipo, valor de None)
_TAGS, _XPOS, _WORD = 7, 5, 2


def _signed_col(values: Sequence) -> "tuple[int, bytes]":
    """Inteiros com sinal (ou None) na menor largura que cabe (1, 2 ou 4 bytes); None é o menor valor da largura."""
    top = 0
    for v in values:
        if v is None:
            continue
        if type(v) is not int or not -(2 ** 31) < v < 2 ** 31:
            raise ValueError(f"valor não inteiro numa coluna de posição: {v!r}")
        top = max(top, abs(v))
    w = 1 if top < 127 else 2 if top < 32767 else 4
    tc, none = _NARROW[w]
    return w, _le(array(tc, [none if v is None else v for v in values]))


def _from_signed(w: int, raw: bytes) -> "list[int | None]":
    tc, none = _NARROW[w]
    return [None if v == none else v for v in _from_le(tc, raw)]


def _tags_from_xpos(cols) -> bool:
    """Em todos os tokens, `tags` é exatamente `[xpos]` (spaCy, Stanza)? Então a coluna não precisa ser gravada."""
    xs, ts = cols[_XPOS], cols[_TAGS]
    return bool(xs) and all(type(x) is str and x and t == json.dumps([x]) for x, t in zip(xs, ts))


def encode_tcl2(rows: Sequence[Sequence], lex: Lexicon) -> bytes:
    """Linhas de tokens → blob `TCL2` (layout v2); valores novos entram no léxico. ValueError se as linhas fugirem
    do padrão (o léxico não é alterado nesse caso).

    Posições: `start` como folga em relação ao fim do token anterior (quase sempre 0 ou 1) e `end` como
    `end - start - len(word)` (quase sempre 0), em 1 byte quando cabe: o que sobra é ruído que o zlib elimina.
    `tags`: se em toda a camada vale `[xpos]`, a coluna é omitida (largura 0) e reconstruída pelo léxico."""
    n = len(rows)
    for r in rows:
        if len(r) != N_COLUMNS:
            raise ValueError(f"linha de token com {len(r)} colunas (esperado {N_COLUMNS})")
    if n >= _V2:
        raise ValueError("camada grande demais")
    cols = list(zip(*rows)) if n else [()] * N_COLUMNS
    derive_tags = _tags_from_xpos(cols)
    news = {}
    for c in range(2, N_COLUMNS):
        d = lex.index[c]
        src = cols[c]
        if c == _TAGS and derive_tags:
            src = [json.dumps([x]) for x in dict.fromkeys(cols[_XPOS])]
        new = [v for v in dict.fromkeys(src) if v not in d]
        if any(type(v) is not str for v in new):
            raise ValueError("valor não textual numa coluna de texto")
        news[c] = new
    gaps, extra, prev_end = [], [], 0
    for s_, e_, w_ in zip(cols[0], cols[1], cols[_WORD]):
        if s_ is None:
            if e_ is not None:
                raise ValueError("fim sem início")
            gaps.append(None)
            extra.append(None)
            continue
        if type(s_) is not int or (e_ is not None and type(e_) is not int):
            raise ValueError(f"valor não inteiro numa coluna de posição: {(s_, e_)!r}")
        gaps.append(s_ - prev_end)
        if e_ is None:
            extra.append(None)
            prev_end = s_
        else:
            extra.append(e_ - s_ - (len(w_) if type(w_) is str else 0))
            prev_end = e_
    chunks = [_signed_col(gaps), _signed_col(extra)]      # levantam ValueError se não for inteiro
    for c, new in news.items():
        lex.add(c, new)
    for c in range(2, N_COLUMNS):
        if c == _TAGS and derive_tags:
            chunks.append((0, b""))
            continue
        idx = array("I", map(lex.index[c].__getitem__, cols[c]))
        top = max(idx) if n else 0
        w, tc = (1, "B") if top < 256 else (2, "H") if top < 65536 else (4, "I")
        chunks.append((w, _le(idx if w == 4 else array(tc, idx))))
    parts = [MAGIC2, struct.pack("<I", n | _V2)]
    for w, raw in chunks:
        z = zlib.compress(raw, _LEVEL) if w else b""
        parts += [struct.pack("<BI", w, len(z)), z]
    return b"".join(parts)


def _chunks2(blob: bytes) -> "tuple[int, list[tuple[int, bytes]], bool]":
    """(n, [(largura, zlib)] das 9 colunas, layout v2?)."""
    blob = bytes(blob)
    (n,) = struct.unpack_from("<I", blob, 4)
    v2, n = bool(n & _V2), n & ~_V2
    pos, out = 8, []
    for _ in range(N_COLUMNS):
        w, ln = struct.unpack_from("<BI", blob, pos)
        out.append((w, blob[pos + 5:pos + 5 + ln]))
        pos += 5 + ln
    return n, out, v2


def blob_length(blob: bytes) -> int:
    """Número de tokens de um blob `TCL2`, sem decodificar."""
    return struct.unpack_from("<I", bytes(blob[:8]), 4)[0] & ~_V2


def tcl2_layout(blob: bytes) -> int:
    """1 = `TCL2` da primeira versão (posições em int32); 2 = layout v2 (posições relativas, `tags` derivável)."""
    return 2 if struct.unpack_from("<I", bytes(blob[:8]), 4)[0] & _V2 else 1


def decode_ids(blob: bytes, columns: "Sequence[int]" = tuple(range(2, N_COLUMNS)),
               lex: "Lexicon | None" = None) -> "dict[int, array]":
    """`TCL2`: só os ids das colunas de texto pedidas (2..8), como `array('I')`; 0 = None. Não precisa do léxico,
    exceto para `tags` quando a camada a deriva de `xpos` (layout v2): então `lex` é obrigatório."""
    n, ch, _v2 = _chunks2(blob)
    out = {}
    for c in columns:
        w, z = ch[c]
        if w == 0:
            if lex is None:
                raise ValueError("a coluna tags desta camada é derivada de xpos: informe o léxico do corpus")
            x = decode_ids(blob, (_XPOS,))[_XPOS]
            xv, ti = lex.values[_XPOS], lex.index[_TAGS]
            m = array("I", [0] + [ti.get(json.dumps([v]), 0) for v in xv[1:]])
            out[c] = array("I", map(m.__getitem__, x))
            continue
        out[c] = _from_le({1: "B", 2: "H", 4: "I"}[w], zlib.decompress(z))
    return out


def decode_tcl2(blob: bytes, lex: Lexicon) -> list[list]:
    """Blob `TCL2` → linhas de tokens (listas de 9 valores), como `decode`."""
    n, ch, v2 = _chunks2(blob)
    if n == 0:
        return []
    ids = decode_ids(blob, tuple(range(2, N_COLUMNS)), lex)
    texts = []
    for c in range(2, N_COLUMNS):
        vals = lex.values[c]
        try:
            texts.append([vals[i] for i in ids[c]])
        except IndexError:
            raise ValueError("o léxico do corpus não tem os ids deste blob (léxico ausente ou de outro arquivo)") from None
    starts: list = []
    ends: list = []
    if v2:
        gaps, extra = _from_signed(ch[0][0], zlib.decompress(ch[0][1])), _from_signed(ch[1][0], zlib.decompress(ch[1][1]))
        prev_end = 0
        for g, x, w in zip(gaps, extra, texts[0]):
            if g is None:
                starts.append(None)
                ends.append(None)
                continue
            s_ = prev_end + g
            starts.append(s_)
            if x is None:
                ends.append(None)
                prev_end = s_
            else:
                prev_end = s_ + x + (len(w) if w is not None else 0)
                ends.append(prev_end)
    else:
        ints = [_from_le("i", zlib.decompress(ch[i][1])) for i in range(2)]
        prev = 0
        for d in ints[0]:
            if d == _NONE:
                starts.append(None)
            else:
                prev += d
                starts.append(prev)
        ends = [None if (ln == _NONE or s_ is None) else s_ + ln for s_, ln in zip(starts, ints[1])]
    return [list(r) for r in zip(starts, ends, *texts)]
