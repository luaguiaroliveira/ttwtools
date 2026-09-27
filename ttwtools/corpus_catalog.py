"""
corpus_catalog.py — Pacotes de corpus, catálogo e instalação (novomodelo.md §6, §9.5, §16.3–16.5).

Pacote de corpus: um `.zip` com
    ficha.json            ficha do corpus (idioma, variedade, período, gêneros, tamanho,
                          licença conferida, fonte, camadas com tagger e versão, hashes)
    corpus.ttwa           (opcional) projeto já indexado e etiquetado
    referencia-<unid>.tsv (opcional) listas de frequência (keyness.write_reference_list)

Catálogo (`catalogo.json`): {"format": "ttwtools-catalog/1", "updated": ..., "packages": [
    {"id", "version", "kind": "package"|"recipe", "url", "size", "sha256", "ficha": {...}}]}
URL relativa é resolvida a partir da URL do catálogo. `recipe` = corpus sem
redistribuição (licença restrita): só a receita de preparo, sem arquivo.

Regra de licença: um pacote só entra no catálogo com `ficha.license.verified_on`
preenchido e `redistributable: true` (validate_catalog recusa o resto).

Instalação na pasta de dados do usuário (platformdirs): <dados>/corpora/<id>/<versão>/.
"""

from __future__ import annotations

import datetime as dt
import hashlib
import json
import shutil
import urllib.parse
import urllib.request
import zipfile
from pathlib import Path
from typing import Any, Callable, Mapping

CATALOG_FORMAT = "ttwtools-catalog/1"
FICHA_FORMAT = "ttwtools-ficha/1"
_FICHA_REQUIRED = {
    "id": str, "name": str, "version": str, "lang": str, "license": dict, "source": dict,
}
_LICENSE_REQUIRED = {"name": str, "redistributable": bool}


# ---------------------------------------------------------------------------
# Pastas e configuração
# ---------------------------------------------------------------------------

def data_dir() -> Path:
    """Pasta de dados do usuário (corpora e modelos baixados). TTWTOOLS_DATA_DIR muda o lugar."""
    import os
    if os.environ.get("TTWTOOLS_DATA_DIR"):
        base = Path(os.environ["TTWTOOLS_DATA_DIR"])
    else:
        import platformdirs
        base = Path(platformdirs.user_data_dir("TTWtools", appauthor=False))
    base.mkdir(parents=True, exist_ok=True)
    return base


def settings() -> dict:
    path = data_dir() / "settings.json"
    return json.loads(path.read_text(encoding="utf-8")) if path.is_file() else {}


def set_setting(key: str, value: Any) -> None:
    s = settings()
    s[key] = value
    (data_dir() / "settings.json").write_text(json.dumps(s, ensure_ascii=False, indent=1), encoding="utf-8")


def catalog_url() -> str | None:
    """URL (ou caminho) do catálogo: settings.json → TTWTOOLS_CATALOG_URL. Sem padrão até a
    decisão de hospedagem (D6)."""
    import os
    return settings().get("catalog_url") or os.environ.get("TTWTOOLS_CATALOG_URL")


# ---------------------------------------------------------------------------
# Validação
# ---------------------------------------------------------------------------

def validate_ficha(ficha: Mapping[str, Any], for_catalog: bool = True) -> list[str]:
    errors = []
    for key, typ in _FICHA_REQUIRED.items():
        if not isinstance(ficha.get(key), typ):
            errors.append(f"ficha.{key} ausente ou do tipo errado ({typ.__name__})")
    lic = ficha.get("license") or {}
    for key, typ in _LICENSE_REQUIRED.items():
        if not isinstance(lic.get(key), typ):
            errors.append(f"ficha.license.{key} ausente ou do tipo errado")
    if for_catalog:
        if not lic.get("verified_on"):
            errors.append("licença não conferida (ficha.license.verified_on vazio)")
        if lic.get("redistributable") is not True:
            errors.append("licença não permite redistribuir: publique só a receita (kind 'recipe')")
    size = ficha.get("size") or {}
    if for_catalog and (not isinstance(size.get("documents"), int) or not isinstance(size.get("words"), int)):
        errors.append("ficha.size precisa de documents e words (inteiros)")
    for i, layer in enumerate(ficha.get("layers") or []):
        if not {"tool", "tool_version"} <= set(layer):
            errors.append(f"ficha.layers[{i}] precisa de tool e tool_version")
    return errors


def validate_catalog(catalog: Mapping[str, Any]) -> list[str]:
    errors = []
    if catalog.get("format") != CATALOG_FORMAT:
        errors.append(f"format deve ser {CATALOG_FORMAT}")
    seen = set()
    for i, entry in enumerate(catalog.get("packages") or []):
        where = f"packages[{i}] ({entry.get('id')})"
        key = (entry.get("id"), entry.get("version"))
        if key in seen:
            errors.append(f"{where}: id e versão repetidos")
        seen.add(key)
        kind = entry.get("kind", "package")
        if kind not in ("package", "recipe"):
            errors.append(f"{where}: kind deve ser package ou recipe")
        if kind == "package":
            for k in ("url", "size", "sha256"):
                if not entry.get(k):
                    errors.append(f"{where}: falta {k}")
        ficha = entry.get("ficha") or {}
        errors += [f"{where}: {e}" for e in validate_ficha(ficha, for_catalog=(kind == "package"))]
        if ficha.get("id") != entry.get("id") or ficha.get("version") != entry.get("version"):
            errors.append(f"{where}: id/versão da entrada e da ficha diferem")
    return errors


# ---------------------------------------------------------------------------
# Criar pacotes
# ---------------------------------------------------------------------------

def _sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def make_package(project_path: str | Path, out_dir: str | Path, ficha: Mapping[str, Any],
                 corpus_name: str | None = None, include_corpus: bool = True,
                 reference_units: tuple[str, ...] = ("form", "lemma", "pos"), layer: str | None = None) -> dict:
    """Cria `<id>-<versão>.zip` com a ficha, o projeto e/ou as listas de referência.
    Completa a ficha com tamanho, camadas e hashes. Devolve a entrada do catálogo."""
    import tempfile
    from . import keyness
    from .corpus import list_corpora
    from .project import TTWAProject

    ficha = dict(ficha)
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory() as tmp, TTWAProject.open(project_path, migrate=True) as proj:
        tmp = Path(tmp)
        corpora = {c["name"]: c for c in list_corpora(proj)}
        name = corpus_name or next(iter(corpora))
        info = corpora[name]
        words = keyness.corpus_freqs(proj, name, "form", layer=layer).words
        ficha.setdefault("size", {"documents": info["documents"], "words": words})
        ficha.setdefault("layers", [{"tool": l["tool"], "tool_version": l["tool_version"], "model": l["model"]}
                                    for l in info["layers"]])
        ficha["format"] = FICHA_FORMAT
        ficha["corpus_name"] = name
        files: dict[str, str] = {}
        if include_corpus:
            shutil.copy(project_path, tmp / "corpus.ttwa")
            files["corpus.ttwa"] = _sha256(tmp / "corpus.ttwa")
        for unit in reference_units:
            lic = ficha.get("license", {})
            card = {"name": ficha.get("name"), "version": ficha.get("version"), "lang": ficha.get("lang"),
                    "variety": ficha.get("variety"), "license": lic.get("reference_list", lic.get("name"))}
            try:
                path = keyness.make_reference_list(proj, name, tmp / f"referencia-{unit}.tsv", unit=unit,
                                                   layer=layer, card=card)
            except ValueError:
                continue
            files[path.name] = _sha256(path)
        ficha["files"] = files
        (tmp / "ficha.json").write_text(json.dumps(ficha, ensure_ascii=False, indent=1), encoding="utf-8")
        pkg = out_dir / f"{ficha['id']}-{ficha['version']}.zip"
        with zipfile.ZipFile(pkg, "w", zipfile.ZIP_DEFLATED) as z:
            for f in sorted(tmp.iterdir()):
                z.write(f, f.name)
    return {"id": ficha["id"], "version": ficha["version"], "kind": "package", "url": pkg.name,
            "size": pkg.stat().st_size, "sha256": _sha256(pkg), "ficha": ficha}


def write_catalog(entries: list[Mapping], path: str | Path) -> dict:
    catalog = {"format": CATALOG_FORMAT, "updated": dt.date.today().isoformat(), "packages": list(entries)}
    errors = validate_catalog(catalog)
    if errors:
        raise ValueError("catálogo inválido: " + "; ".join(errors))
    Path(path).write_text(json.dumps(catalog, ensure_ascii=False, indent=1), encoding="utf-8")
    return catalog


# ---------------------------------------------------------------------------
# Ler catálogo, instalar, remover, atualizar
# ---------------------------------------------------------------------------

def _open_url(url: str):
    if "://" not in url or url.startswith("file://"):
        return open(urllib.parse.unquote(url.removeprefix("file://")), "rb")
    return urllib.request.urlopen(url, timeout=60)


def load_catalog(url: str | None = None) -> dict:
    url = url or catalog_url()
    if not url:
        raise ValueError("nenhum catálogo configurado (settings.json 'catalog_url' ou TTWTOOLS_CATALOG_URL)")
    with _open_url(url) as fh:
        catalog = json.loads(fh.read().decode("utf-8"))
    catalog["_url"] = url
    return catalog


def _resolve(base: str, url: str) -> str:
    if "://" in url or Path(url).is_absolute():
        return url
    if "://" in base and not base.startswith("file://"):
        return urllib.parse.urljoin(base, url)
    return str(Path(urllib.parse.unquote(base.removeprefix("file://"))).parent / url)


def installed() -> list[dict]:
    """Pacotes instalados: ficha + caminho de cada um."""
    out = []
    for ficha_path in sorted((data_dir() / "corpora").glob("*/*/ficha.json")):
        ficha = json.loads(ficha_path.read_text(encoding="utf-8"))
        folder = ficha_path.parent
        out.append({"id": ficha["id"], "version": ficha["version"], "path": str(folder), "ficha": ficha,
                    "project": str(folder / "corpus.ttwa") if (folder / "corpus.ttwa").is_file() else None,
                    "reference_lists": sorted(str(p) for p in folder.glob("referencia-*.tsv"))})
    return out


def install(package_id: str, version: str | None = None, catalog: Mapping | None = None,
            progress: Callable[[int, int, str], None] | None = None) -> dict:
    """Baixa, confere o hash e extrai o pacote. Devolve o item de installed()."""
    catalog = catalog or load_catalog()
    entries = [e for e in catalog["packages"] if e["id"] == package_id and (version is None or e["version"] == version)]
    if not entries:
        raise KeyError(f"pacote '{package_id}' não está no catálogo")
    entry = sorted(entries, key=lambda e: [int(x) if x.isdigit() else x for x in e["version"].split(".")])[-1]
    if entry.get("kind", "package") != "package":
        raise ValueError(f"'{package_id}' não é redistribuível: use a receita de preparo")
    dest = data_dir() / "corpora" / entry["id"] / entry["version"]
    tmp = data_dir() / "downloads" / f"{entry['id']}-{entry['version']}.zip.part"
    tmp.parent.mkdir(parents=True, exist_ok=True)
    url = _resolve(catalog.get("_url", ""), entry["url"])
    h = hashlib.sha256()
    done = 0
    with _open_url(url) as src, tmp.open("wb") as dst:
        for chunk in iter(lambda: src.read(1 << 16), b""):
            dst.write(chunk)
            h.update(chunk)
            done += len(chunk)
            if progress:
                progress(done, entry["size"], entry["id"])
    if h.hexdigest() != entry["sha256"]:
        tmp.unlink(missing_ok=True)
        raise ValueError(f"hash não confere para {entry['id']} (download corrompido ou pacote alterado)")
    if dest.exists():
        shutil.rmtree(dest)
    dest.mkdir(parents=True)
    with zipfile.ZipFile(tmp) as z:
        z.extractall(dest)
    tmp.unlink()
    return next(i for i in installed() if i["path"] == str(dest))


def remove(package_id: str, version: str | None = None) -> int:
    """Remove as versões instaladas (todas, ou só `version`). Devolve quantas."""
    n = 0
    base = data_dir() / "corpora" / package_id
    for folder in sorted(base.glob("*")) if base.is_dir() else []:
        if version is None or folder.name == version:
            shutil.rmtree(folder)
            n += 1
    if base.is_dir() and not any(base.iterdir()):
        base.rmdir()
    return n


def updates(catalog: Mapping | None = None) -> list[dict]:
    """Pacotes instalados com versão mais nova no catálogo."""
    catalog = catalog or load_catalog()
    key = lambda v: [int(x) if x.isdigit() else x for x in v.split(".")]  # noqa: E731
    out = []
    for item in installed():
        newer = [e["version"] for e in catalog["packages"] if e["id"] == item["id"] and key(e["version"]) > key(item["version"])]
        if newer:
            out.append({"id": item["id"], "installed": item["version"], "latest": max(newer, key=key)})
    return out
