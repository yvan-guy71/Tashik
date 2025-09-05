import os
from app import app, db
from models import Manga, Chapter

MANGAS_DIR = os.path.join(app.root_path, "mangas")

def safe_read(path, default=""):
    try:
        with open(path, encoding="utf-8") as f:
            return f.read().strip()
    except Exception:
        return default

def parse_date_to_timestamp(s, default=0):
    """Convertit plusieurs formats de da
    te en timestamp (int).
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
    from datetime import datetime
    patterns = [
        '%d-%m-%Y', '%d/%m/%Y', '%Y-%m-%d',
        '%Y-%m-%d %H:%M:%S', '%d-%m-%Y %H:%M:%S', '%d/%m/%Y %H:%M:%S'
    ]
    for p in patterns:
        try:
            dt = datetime.strptime(s, p)
            return int(dt.timestamp())
        except Exception:
            continue
    # 4) Try ISO
    try:
        dt = datetime.fromisoformat(s)
        return int(dt.timestamp())
    except Exception:
        pass
    # 5) Could not parse -> return default
    return default

def synchronize_db_and_fs():
    with app.app_context():
        # Synchronisation des mangas
        mangas_in_db = {m.name: m for m in Manga.query.all()}
        mangas_in_fs = {d: os.path.join(MANGAS_DIR, d) for d in os.listdir(MANGAS_DIR) if os.path.isdir(os.path.join(MANGAS_DIR, d))}

        for manga_name, manga_path in mangas_in_fs.items():
            if manga_name not in mangas_in_db:
                # Ajouter le manga dans la DB
                new_manga = Manga(
                    name=manga_name,
                    author=safe_read(os.path.join(manga_path, "author.txt"), "Inconnu"),
                    category=safe_read(os.path.join(manga_path, "category.txt"), "Autre"),
                    syllabus=safe_read(os.path.join(manga_path, "syllabus.txt"), ""),
                    year=safe_read(os.path.join(manga_path, "year.txt"), ""),
                    date_added=parse_date_to_timestamp(safe_read(os.path.join(manga_path, "date_added.txt"), "0"), default=0),
                    cover_filename=next(
                        (f for f in os.listdir(manga_path) if f.startswith("cover") and f.split(".")[-1] in ["jpg", "jpeg", "png", "webp"]),
                        None
                    )
                )
                db.session.add(new_manga)
                print(f"Ajouté dans la DB : {manga_name}")
            else:
                # Mettre à jour les informations du manga dans la DB
                manga = mangas_in_db[manga_name]
                manga.author = safe_read(os.path.join(manga_path, "author.txt"), manga.author)
                manga.category = safe_read(os.path.join(manga_path, "category.txt"), manga.category)
                manga.syllabus = safe_read(os.path.join(manga_path, "syllabus.txt"), manga.syllabus)
                manga.year = safe_read(os.path.join(manga_path, "year.txt"), manga.year)
                # Utiliser le parser sécurisé pour date_added
                manga.date_added = parse_date_to_timestamp(safe_read(os.path.join(manga_path, "date_added.txt"), str(manga.date_added)), default=manga.date_added)
                manga.cover_filename = next(
                    (f for f in os.listdir(manga_path) if f.startswith("cover") and f.split(".")[-1] in ["jpg", "jpeg", "png", "webp"]),
                    manga.cover_filename
                )
                print(f"Mise à jour dans la DB : {manga_name}")

        # Supprimer les mangas inexistants dans le FS
        for manga_name in mangas_in_db.keys():
            if manga_name not in mangas_in_fs:
                manga_to_delete = mangas_in_db[manga_name]
                db.session.delete(manga_to_delete)
                print(f"Supprimé de la DB : {manga_name}")

        db.session.commit()

        # Synchronisation des chapitres
        for manga_name, manga_path in mangas_in_fs.items():
            chapters_in_db = {c.name: c for c in Chapter.query.filter_by(manga_id=mangas_in_db[manga_name].id).all()}
            chapters_in_fs = {d: os.path.join(manga_path, d) for d in os.listdir(manga_path) if os.path.isdir(os.path.join(manga_path, d))}

            for chapter_name, chapter_path in chapters_in_fs.items():
                if chapter_name not in chapters_in_db:
                    # Ajouter le chapitre dans la DB
                    new_chapter = Chapter(name=chapter_name, manga_id=mangas_in_db[manga_name].id)
                    db.session.add(new_chapter)
                    print(f"Ajouté dans la DB : {chapter_name} (Manga : {manga_name})")

            for chapter_name in chapters_in_db.keys():
                if chapter_name not in chapters_in_fs:
                    # Supprimer le chapitre de la DB
                    chapter_to_delete = chapters_in_db[chapter_name]
                    db.session.delete(chapter_to_delete)
                    print(f"Supprimé de la DB : {chapter_name} (Manga : {manga_name})")

        db.session.commit()
        print("Synchronisation terminée.")

if __name__ == "__main__":
    synchronize_db_and_fs()