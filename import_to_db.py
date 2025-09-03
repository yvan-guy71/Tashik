import os
import time
import json
import shutil
import datetime
from app import app, db, MANGAS_DIR
from models import Manga, Chapter, Rating, Favorite, Comment, ReadingHistory, User

def safe_read(path, default=""):
    try:
        with open(path, encoding="utf-8") as f:
            return f.read().strip()
    except Exception:
        return default

def safe_read_json(path, default=None):
    try:
        with open(path, encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return default if default is not None else []

def import_mangas_from_fs():
    STATIC_COVERS_DIR = os.path.join(app.root_path, "static", "covers")
    os.makedirs(STATIC_COVERS_DIR, exist_ok=True)

    with app.app_context():
        for manga_name in os.listdir(MANGAS_DIR):
            manga_dir = os.path.join(MANGAS_DIR, manga_name)
            if not os.path.isdir(manga_dir):
                continue

            # Lecture des infos du manga
            author = safe_read(os.path.join(manga_dir, "author.txt"))
            if not author and manga and manga.author:
                author = manga.author  # Garde l'ancien auteur si le fichier est vide
            year = safe_read(os.path.join(manga_dir, "year.txt"))
            category = safe_read(os.path.join(manga_dir, "category.txt"))
            if not category and manga and manga.category:
                category = manga.category  # Garde l'ancienne catégorie si le fichier est vide
            syllabus = safe_read(os.path.join(manga_dir, "syllabus.txt"))
            if not syllabus and manga and manga.syllabus:
                syllabus = manga.syllabus  # Garde l'ancien synopsis si le fichier est vide
            cover_filename = safe_read(os.path.join(manga_dir, "cover.txt"))
            date_added = safe_read(os.path.join(manga_dir, "date_added.txt"))
            try:
                date_added = int(date_added)
            except Exception:
                date_added = int(time.time())

            # Manga
            manga = Manga.query.filter_by(name=manga_name).first()
            if not manga:
                manga = Manga(
                    name=manga_name,
                    author=author,
                    year=year,
                    category=category,
                    syllabus=syllabus,
                    cover_filename=cover_filename,
                    date_added=date_added
                )
                db.session.add(manga)
                db.session.commit()
            else:
                manga.author = author
                manga.year = year
                manga.category = category
                manga.syllabus = syllabus
                manga.cover_filename = cover_filename
                manga.date_added = date_added
                db.session.commit()

            cover_src = os.path.join(manga_dir, cover_filename)
            if os.path.exists(cover_src) and cover_filename:
                # On copie la cover dans static/covers/ avec un nom unique (ex: One Piece.jpg)
                ext = os.path.splitext(cover_filename)[1]
                new_cover_filename = f"{manga_name}{ext}"
                cover_dest = os.path.join(STATIC_COVERS_DIR, new_cover_filename)
                shutil.copy(cover_src, cover_dest)
                manga.cover_filename = new_cover_filename
                db.session.commit()
            else:
                manga.cover_filename = None
                db.session.commit()

            # Import des chapitres
            for chapter_name in os.listdir(manga_dir):
                chapter_path = os.path.join(manga_dir, chapter_name)
                if os.path.isdir(chapter_path):
                    date_added_path = os.path.join(chapter_path, "date_added.txt")
                    date_added_chap = safe_read(date_added_path)
                    try:
                        date_added_chap = int(date_added_chap)
                    except Exception:
                        date_added_chap = int(time.time())
                    chapter = Chapter.query.filter_by(name=chapter_name, manga_id=manga.id).first()
                    if not chapter:
                        chapter = Chapter(
                            name=chapter_name,
                            manga_id=manga.id,
                            date_added=date_added_chap
                        )
                        db.session.add(chapter)
            db.session.commit()

            # Import des ratings (notes)
            ratings_path = os.path.join(manga_dir, "ratings.json")
            ratings = safe_read_json(ratings_path, [])
            for r in ratings:
                try:
                    value = float(str(r.get("value", 0)).replace(",", ".").split("/")[0])
                except Exception:
                    value = 0
                user_id = r.get("user_id")
                rating_obj = Rating.query.filter_by(manga_id=manga.id, user_id=user_id, value=value).first()
                if not rating_obj:
                    rating_obj = Rating(manga_id=manga.id, value=value, user_id=user_id)
                    db.session.add(rating_obj)
            db.session.commit()

            # Import des favoris
            favs_path = os.path.join(manga_dir, "favorites.json")
            favs = safe_read_json(favs_path, [])
            for f in favs:
                user_id = f.get("user_id")
                fav_obj = Favorite.query.filter_by(manga_id=manga.id, user_id=user_id).first()
                if not fav_obj:
                    fav_obj = Favorite(manga_id=manga.id, user_id=user_id)
                    db.session.add(fav_obj)
            db.session.commit()

            # Import des commentaires
            comments_path = os.path.join(manga_dir, "comments.json")
            comments = safe_read_json(comments_path, [])
            for c in comments:
                user_id = c.get("user_id")
                content = c.get("content", "")
                created_at = c.get("created_at", int(time.time()))
                comment_obj = Comment.query.filter_by(manga_id=manga.id, user_id=user_id, content=content).first()
                if not comment_obj:
                    comment_obj = Comment(manga_id=manga.id, user_id=user_id, content=content, created_at=created_at)
                    db.session.add(comment_obj)
            db.session.commit()

            # Import historique de lecture
            history_path = os.path.join(manga_dir, "history.json")
            history = safe_read_json(history_path, [])
            for h in history:
                user_id = h.get("user_id")
                chapter_name = h.get("chapter_name")
                hist_obj = ReadingHistory.query.filter_by(user_id=user_id, manga_id=manga.id, chapter_name=chapter_name).first()
                if not hist_obj:
                    hist_obj = ReadingHistory(user_id=user_id, manga_id=manga.id, chapter_name=chapter_name)
                    db.session.add(hist_obj)
            db.session.commit()

# Sauvegarde automatique de la base avant import
def backup_db():
    db_path = os.path.join(app.root_path, "site.db")
    if os.path.exists(db_path):
        now = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
        backup_path = os.path.join(app.root_path, f"site_backup_{now}.db")
        import shutil
        shutil.copy(db_path, backup_path)
        print(f"Sauvegarde de la base effectuée : {backup_path}")

if __name__ == "__main__":
    backup_db()
    import_mangas_from_fs()
    print("Import terminé !")