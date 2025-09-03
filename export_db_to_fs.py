import os
import shutil
from datetime import datetime

from app import app, db
from models import Manga, Chapter

MANGAS_DIR = os.path.join(app.root_path, "mangas")


def safe_write(path, content, overwrite=False):
    """Écrit `content` dans `path` en UTF-8. Ne réécrit pas par défaut.
    Retourne True si fichier créé/écrasé, False sinon.
    """
    try:
        if os.path.exists(path) and not overwrite:
            return False
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "w", encoding="utf-8") as f:
            f.write(content if content is not None else "")
        return True
    except Exception as e:
        print(f"Erreur écriture {path}: {e}")
        return False


def parse_date_to_timestamp(s, default=0):
    """Convertit plusieurs formats de date en timestamp (int).
    Accepté : timestamp int, ISO, 'DD-MM-YYYY', 'DD/MM/YYYY', 'YYYY-MM-DD', et variantes avec time.
    Retourne `default` si la conversion échoue.
    """
    if s is None:
        return default
    s = str(s).strip()
    if s == "":
        return default
    # 1) Try raw integer / numeric timestamp
    try:
        return int(s)
    except Exception:
        pass
    # 2) Try float (e.g. '1620000000.0')
    try:
        return int(float(s))
    except Exception:
        pass
    # 3) Try common human formats
    try:
        from datetime import datetime as _dt
        patterns = [
            '%d-%m-%Y', '%d/%m/%Y', '%Y-%m-%d',
            '%Y-%m-%d %H:%M:%S', '%d-%m-%Y %H:%M:%S', '%d/%m/%Y %H:%M:%S'
        ]
        for p in patterns:
            try:
                dt = _dt.strptime(s, p)
                return int(dt.timestamp())
            except Exception:
                continue
    except Exception:
        pass
    # 4) Try ISO
    try:
        dt = datetime.fromisoformat(s)
        return int(dt.timestamp())
    except Exception:
        pass
    # 5) Could not parse -> return default
    return default


def export_db_entries_to_fs(default_cover_src=None, overwrite=False, create_chapters=True):
    """Crée dossier FS pour mangas présents en DB mais absents en FS.
    - default_cover_src: chemin vers image par défaut à copier si aucune cover trouvée.
    - overwrite: si True, écrase les fichiers textes existants.
    - create_chapters: si True, crée dossiers de chapitres listés en DB.
    """
    created_mangas = []
    updated_mangas = []
    created_chapters = []

    with app.app_context():
        mangas_in_db = {m.name: m for m in Manga.query.all()}
        mangas_in_fs = {d for d in os.listdir(MANGAS_DIR) if os.path.isdir(os.path.join(MANGAS_DIR, d))}

        for name, manga in mangas_in_db.items():
            manga_dir = os.path.join(MANGAS_DIR, name)
            existed = os.path.exists(manga_dir)
            if not existed:
                try:
                    os.makedirs(manga_dir, exist_ok=True)
                    created_mangas.append(name)
                except Exception as e:
                    print(f"Impossible de créer le dossier {manga_dir}: {e}")
                    continue

            # Ecrire les fichiers texte (author, category, syllabus, year)
            wrote_author = safe_write(os.path.join(manga_dir, "author.txt"), manga.author or "", overwrite=overwrite)
            wrote_category = safe_write(os.path.join(manga_dir, "category.txt"), manga.category or "", overwrite=overwrite)
            wrote_syllabus = safe_write(os.path.join(manga_dir, "syllabus.txt"), manga.syllabus or "", overwrite=overwrite)
            wrote_year = safe_write(os.path.join(manga_dir, "year.txt"), str(manga.year or ""), overwrite=overwrite)

            # date_added : privilégie un timestamp entier si possible
            ts = None
            try:
                if getattr(manga, "date_added", None) is not None:
                    # si c'est un int déjà
                    if isinstance(manga.date_added, (int, float)):
                        ts = int(manga.date_added)
                    else:
                        ts = parse_date_to_timestamp(str(manga.date_added), default=0)
            except Exception:
                ts = 0
            if not ts or ts <= 0:
                # si aucun timestamp valide, on écrit la date actuelle en DD-MM-YYYY
                safe_write(os.path.join(manga_dir, "date_added.txt"), datetime.utcnow().strftime("%d-%m-%Y"), overwrite=overwrite)
            else:
                safe_write(os.path.join(manga_dir, "date_added.txt"), str(ts), overwrite=overwrite)

            # Couverture : tenter de localiser et copier
            try:
                cover_src = None
                if getattr(manga, "cover_filename", None):
                    # cherche dans static/covers
                    possible = os.path.join(app.root_path, "static", "covers", manga.cover_filename)
                    if os.path.exists(possible):
                        cover_src = possible
                    elif os.path.exists(manga.cover_filename):
                        cover_src = manga.cover_filename
                if not cover_src and default_cover_src and os.path.exists(default_cover_src):
                    cover_src = default_cover_src

                if cover_src:
                    _, ext = os.path.splitext(cover_src)
                    dest = os.path.join(manga_dir, f"cover{ext.lower()}")
                    if overwrite or not os.path.exists(dest):
                        shutil.copyfile(cover_src, dest)
            except Exception as e:
                print(f"Erreur gestion cover pour {name}: {e}")

            # Créer dossiers de chapitres présents en DB mais absents en FS
            if create_chapters:
                try:
                    chapters_db = Chapter.query.filter_by(manga_id=manga.id).all()
                    for chap in chapters_db:
                        chap_dir = os.path.join(manga_dir, chap.name)
                        if not os.path.exists(chap_dir):
                            try:
                                os.makedirs(chap_dir, exist_ok=True)
                                created_chapters.append(f"{name}/{chap.name}")
                            except Exception as e:
                                print(f"Impossible de créer chapitre {chap_dir}: {e}")
                except Exception:
                    pass

            if existed:
                updated_mangas.append(name)

        # résumé
        print(f"Mangas créés sur FS : {len(created_mangas)}")
        if created_mangas:
            for m in created_mangas:
                print(f"  - {m}")
        print(f"Mangas existants mis à jour (fichiers écrits) : {len(updated_mangas)}")
        print(f"Chapitres créés : {len(created_chapters)}")
        if created_chapters:
            for c in created_chapters[:50]:
                print(f"  - {c}")


if __name__ == "__main__":
    default_cover = os.path.join(app.root_path, "static", "default-cover.jpg")
    export_db_entries_to_fs(default_cover_src=default_cover, overwrite=False, create_chapters=True)
    print("Export DB -> FS terminé.")
