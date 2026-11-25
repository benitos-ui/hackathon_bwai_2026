"""Téléchargement sécurisé et vérifié (SHA-256) des poids du modèle NER (§7.11).

Usage :
    ``BWAI_MODELE_URL="https://..." python scripts/telecharger_modele.py``
    ou :
    ``python scripts/telecharger_modele.py https://...``

Sécurité & reproductibilité (CDC §7.11, E18) :
- Aucune URL secrète ni jeton n'est stocké dans le dépôt.
- L'empreinte SHA-256 attendue est lue depuis ``ai/modeles/ner-v1.sha256`` (fichier
  versionné non secret) avant toute extraction.
- En cas d'empreinte différente, l'archive corrompue ou altérée est immédiatement
  supprimée et l'installation est interrompue.
- Protection contre le Zip-Slip (vérification que chaque fichier extrait reste
  strictement à l'intérieur du dossier cible).
"""

import argparse
import hashlib
import os
from pathlib import Path
import sys
from typing import Optional, Union
import urllib.request
import zipfile

CHEMIN_SHA256_DEFAUT: Path = Path("ai/modeles/ner-v1.sha256")
DOSSIER_SORTIE_DEFAUT: Path = Path("ai/modeles")
ARCHIVE_DEFAUT: Path = Path("ai/modeles/ner-v1.zip")


def calculer_sha256(path: Union[str, Path]) -> str:
    """Calcule l'empreinte SHA-256 hexadécimale d'un fichier par blocs de 1 Mio."""
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for bloc in iter(lambda: f.read(1 << 20), b""):
            h.update(bloc)
    return h.hexdigest()


def lire_sha256_attendu(chemin_sha256: Union[str, Path] = CHEMIN_SHA256_DEFAUT) -> str:
    """Lit et normalise l'empreinte SHA-256 attendue (64 caractères hexadécimaux)."""
    p = Path(chemin_sha256)
    if not p.is_file():
        raise FileNotFoundError(
            f"Fichier d'empreinte introuvable : {p}. "
            "Impossible de vérifier l'intégrité du modèle."
        )
    contenu = p.read_text(encoding="utf-8").strip().split()[0].lower()
    if len(contenu) != 64 or any(c not in "0123456789abcdef" for c in contenu):
        raise ValueError(f"Empreinte SHA-256 invalide dans {p} : '{contenu}'")
    return contenu


def _extraire_zip_securise(archive: Path, dossier_cible: Path) -> None:
    """Extrait une archive ZIP en bloquant toute traversée de répertoire (Zip-Slip)."""
    racine = dossier_cible.resolve()
    racine.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(archive, "r") as zf:
        for membre in zf.infolist():
            dest = (racine / membre.filename).resolve()
            if racine != dest and racine not in dest.parents:
                raise ValueError(
                    f"Chemin interdit détecté dans l'archive (Zip-Slip) : {membre.filename}"
                )
        zf.extractall(racine)


def telecharger_et_installer(
    url: str,
    sha256_attendu: str,
    archive: Union[str, Path] = ARCHIVE_DEFAUT,
    dossier_sortie: Union[str, Path] = DOSSIER_SORTIE_DEFAUT,
    garder_archive: bool = False,
) -> Path:
    """Télécharge l'archive, vérifie son SHA-256, puis l'extrait en sécurité.

    En cas de divergence d'empreinte ou d'archive invalide, supprime immédiatement
    l'archive téléchargée avant de lever ``ValueError``.
    """
    if not url or not url.strip():
        raise ValueError(
            "URL du modèle manquante : définir BWAI_MODELE_URL ou passer l'URL en argument."
        )

    attendu = sha256_attendu.strip().lower()
    chemin_archive = Path(archive)
    chemin_archive.parent.mkdir(parents=True, exist_ok=True)

    urllib.request.urlretrieve(url, str(chemin_archive))

    try:
        obtenu = calculer_sha256(chemin_archive)
        if obtenu != attendu:
            chemin_archive.unlink(missing_ok=True)
            raise ValueError(
                f"Empreinte SHA-256 différente (attendu={attendu}, obtenu={obtenu}) : "
                "archive corrompue ou modifiée, supprimée et installation interrompue."
            )
        _extraire_zip_securise(chemin_archive, Path(dossier_sortie))
    except Exception:
        chemin_archive.unlink(missing_ok=True)
        raise

    if not garder_archive:
        chemin_archive.unlink(missing_ok=True)

    return Path(dossier_sortie)


def main(argv: Optional[list[str]] = None) -> int:
    parser = argparse.ArgumentParser(
        description="Télécharge et vérifie (SHA-256) les poids du modèle NER."
    )
    parser.add_argument(
        "url",
        nargs="?",
        default=os.environ.get("BWAI_MODELE_URL"),
        help="URL publique de l'archive du modèle (ou variable BWAI_MODELE_URL).",
    )
    parser.add_argument(
        "--sha256-file",
        default=str(CHEMIN_SHA256_DEFAUT),
        help="Chemin vers le fichier contenant l'empreinte SHA-256 attendue.",
    )
    parser.add_argument(
        "--sha256",
        default=None,
        help="Empreinte SHA-256 attendue (remplace --sha256-file si fournie).",
    )
    parser.add_argument(
        "--sortie",
        default=str(DOSSIER_SORTIE_DEFAUT),
        help="Dossier cible d'extraction (défaut : ai/modeles).",
    )
    parser.add_argument(
        "--garder-archive",
        action="store_true",
        help="Conserver le fichier .zip après extraction.",
    )
    args = parser.parse_args(argv)

    if not args.url:
        print(
            "Erreur : fournir l'URL publique du modèle via BWAI_MODELE_URL ou en argument "
            "(aucun secret dans le dépôt).",
            file=sys.stderr,
        )
        return 1

    try:
        attendu = args.sha256 if args.sha256 else lire_sha256_attendu(args.sha256_file)
        dossier = telecharger_et_installer(
            url=args.url,
            sha256_attendu=attendu,
            dossier_sortie=args.sortie,
            garder_archive=args.garder_archive,
        )
    except Exception as exc:
        print(f"Erreur d'installation du modèle : {exc}", file=sys.stderr)
        return 1

    print(f"Modèle installé et vérifié dans : {dossier}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
