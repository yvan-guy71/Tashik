from flask import Flask, render_template, send_from_directory, request, redirect, url_for, flash, abort, session
from flask_login import LoginManager, login_user, logout_user, login_required, current_user
import os
from flask_mail import Mail, Message
import zipfile
import io
from datetime import datetime, timedelta
import re
from dotenv import load_dotenv
import time
from models import db, Manga, Chapter
from models import User, Favorite, ReadingHistory, Comment, Rating, CommentLike, ReadingProgress
from werkzeug.utils import secure_filename
from functools import lru_cache, wraps
from flask_migrate import Migrate
from flask_babel import Babel, gettext as _
from flask import session
from forms import RegisterForm, LoginForm, ResetPasswordForm, ForgotPasswordForm, DeleteAccountForm
from flask_wtf import FlaskForm
from wtforms import PasswordField, SubmitField
from wtforms.validators import DataRequired
from werkzeug.security import check_password_hash
from itsdangerous import URLSafeTimedSerializer

USE_DATABASE = True # Passe à True pour utiliser la base de données ou False pour le système de fichiers




app = Flask(__name__)
migrate = Migrate(app, db)
# Chargement des variables d'environnement depuis .env
load_dotenv()

# Configurations
app.config['SECRET_KEY'] = os.getenv('SECRET_KEY', 'une_clé_par_défaut_super_secure')

babel = Babel(app)
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///' + os.path.join(app.root_path, 'site.db')
app.config['SQLALCHEMY_ECHO'] = False
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
app.config['MAIL_SERVER'] = 'smtp.gmail.com'
app.config['MAIL_PORT'] = 587
app.config['MAIL_USE_TLS'] = True
app.config['MAIL_USERNAME'] = os.getenv('MAIL_USERNAME')
app.config['MAIL_PASSWORD'] = os.getenv('MAIL_PASSWORD')
app.config['BABEL_DEFAULT_LOCALE'] = 'fr'
app.config['BABEL_TRANSLATION_DIRECTORIES'] = 'translations'
app.config['RECAPTCHA_PUBLIC_KEY'] = '6LekNZcrAAAAAOB4HoGwzg0Fdx3DysnW2EJDXEuY'
app.config['RECAPTCHA_PRIVATE_KEY'] = '6LekNZcrAAAAAGJP2jvAad_UevJomx-SRriLUWak'
app.config['SITE_NAME'] = os.getenv('SITE_NAME', 'Yomi-Scan')



db.init_app(app)
mail = Mail(app)
MANGAS_DIR = os.path.join(app.root_path, "mangas")
POSSIBLE_COVER_FILENAMES = ["cover.webp", "cover.jpg", "cover.jpeg", "cover.png"]

login_manager = LoginManager(app)
login_manager.login_view = 'login'


@login_manager.user_loader
def load_user(user_id):
    return User.query.get(int(user_id))


@lru_cache(maxsize=128)
def get_manga_details_cached(manga_name_fs):
    return _get_manga_details_from_fs(manga_name_fs)

def is_valid_name(name):
    # Autorise lettres, chiffres, espaces, tirets, underscores, pas vide
    return bool(re.match(r'^[\w\s\-]+$', name)) and name.strip() != ""

def ajouter_chapitre(manga_name_fs, chapter_name_fs):
    chapter_dir = os.path.join(MANGAS_DIR, manga_name_fs, chapter_name_fs)
    os.makedirs(chapter_dir, exist_ok=True)
    with open(os.path.join(chapter_dir, "date_added.txt"), "w") as f:
        f.write(str(int(time.time())))
        
def parse_rating(rating):
    if not rating:
        return 0.0
    if isinstance(rating, (int, float)):
        return float(rating)
    if "/" in str(rating):
        return float(str(rating).split("/")[0].replace(",", "."))
    try:
        return float(str(rating).replace(",", "."))
    except Exception:
        return 0.0
    
   
def get_cover_url(manga_name):
    for ext in [".webp", ".jpg", ".jpeg", ".png"]:
        possible_path = os.path.join(MANGAS_DIR, manga_name, f"cover{ext}")
        if os.path.exists(possible_path):
            return url_for('serve_manga_file', manga=manga_name, filename=f"cover{ext}")
    # Ensure a default cover is returned if no cover file exists
    return url_for('static', filename='default-cover.jpg')


def compute_badges(manga):
    # NEW : moins de 7 jours
    is_new = False
    if manga.get("date_added"):
        try:
            is_new = (datetime.utcnow() - datetime.fromtimestamp(int(manga["date_added"]))) < timedelta(days=7)
        except Exception:
            is_new = False

    # HOT : plus de 100 lectures récentes
    is_hot = manga.get("nb_lectures_recent", 0)
    try:
        is_hot = int(is_hot) > 100
    except Exception:
        is_hot = False

    # TOP : note moyenne >= 4.5
    rating = manga.get("avg_rating") or manga.get("rating") or 0
    try:
        rating_float = float(str(rating).replace(",", ".").split("/")[0])
        is_top = rating_float >= 4.5
    except Exception:
        is_top = False

    manga["is_new"] = is_new
    manga["is_hot"] = is_hot
    manga["is_top"] = is_top
    return manga

@app.context_processor
def utility_processor():
    return dict(get_cover_url=get_cover_url)

def admin_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if not current_user.is_authenticated or not getattr(current_user, "is_admin", False):
            abort(403)
        return f(*args, **kwargs)
    return decorated_function

@app.route("/")
def index():
    source = get_source()
    search_query = request.args.get("q", "").lower()

    mangas_data = []
    if source == "db":
        mangas_db = Manga.query.all()
        for m in mangas_db:
            cover_url = None
            for ext in [".webp", ".jpg", ".jpeg", ".png"]:
                possible_path = os.path.join(MANGAS_DIR, m.name, f"cover{ext}")
                if os.path.exists(possible_path):
                    cover_url = url_for('serve_manga_file', manga=m.name, filename=f"cover{ext}")
                    break
            if not cover_url:
                cover_url = url_for('static', filename='default-cover.jpg')

            manga_dict = {
                "name": m.name,
                "cover": cover_url,
                "syllabus": m.syllabus,
                "date_added": (
                    m.date_added if isinstance(m.date_added, int)
                    else int(m.date_added) if isinstance(m.date_added, str) and m.date_added.strip() != ""
                    else int(m.date_added.timestamp()) if hasattr(m.date_added, "timestamp")
                    else 0
                ),
                "category": m.category,
                "author": m.author,
                "year": m.year,
                "rating": m.ratings,
                "nb_chapitres": len(getattr(m, "chapters", [])),
                "cover_filename": m.cover_filename,
                # Badges manuels
                "is_hot_manual": m.is_hot,
                "is_new_manual": m.is_new,
                "is_top_manual": m.is_top,
            }
            # Badges automatiques
            auto_badges = compute_badges(manga_dict.copy())
            manga_dict["is_hot_auto"] = auto_badges["is_hot"]
            manga_dict["is_new_auto"] = auto_badges["is_new"]
            manga_dict["is_top_auto"] = auto_badges["is_top"]

            mangas_data.append(manga_dict)
        now = datetime.utcnow()
        chapters_db = Chapter.query.order_by(Chapter.date_added.desc()).limit(32).all()
        recent_chapters = []
        manga_ids = [chap.manga_id for chap in chapters_db]
        mangas_dict = {m.id: m for m in Manga.query.filter(Manga.id.in_(manga_ids)).all()}
        
        recent_chapters_7j = [
        chap for chap in recent_chapters
        if chap.get('date_added') and (now - datetime.fromtimestamp(chap['date_added'])).days < 7
        ]
        
        for chap in chapters_db:
            if chap.date_added and (now - datetime.fromtimestamp(chap.date_added)).days < 7:
                manga = mangas_dict.get(chap.manga_id)
                cover_path = os.path.join(MANGAS_DIR, manga.name, manga.cover_filename) if manga and manga.cover_filename else None
                cover_url = url_for('serve_manga_file', manga=manga.name, filename=manga.cover_filename) if manga and manga.cover_filename and cover_path and os.path.exists(cover_path) else url_for('static', filename='default-cover.jpg')
                recent_chapters.append({
                    "manga_name": manga.name if manga else "",
                    "chapter_folder": chap.name,
                    "date_added": chap.date_added,
                    "cover": cover_url,
                    "chapter_title": chap.name,
                    "is_hot_auto": getattr(chap, "nb_lectures_recent", 0) > 100,
                    "is_new_auto": True,
                    # Ajoute aussi les badges manuels du manga
                    "is_hot_manual": manga.is_hot if manga else False,
                    "is_new_manual": manga.is_new if manga else False,
                    "is_top_manual": manga.is_top if manga else False,
                })
    else:
        mangas_data = [
            _get_manga_details_from_fs(manga_name_fs)
            for manga_name_fs in os.listdir(MANGAS_DIR)
            if os.path.isdir(os.path.join(MANGAS_DIR, manga_name_fs))
        ]
        mangas_data = [m for m in mangas_data if m is not None]
        mangas_data = [compute_badges(m) for m in mangas_data]
        # Pour le mode fichiers, les badges sont tous auto
        for m in mangas_data:
            m["is_hot_manual"] = False
            m["is_new_manual"] = False
            m["is_top_manual"] = False
            m["is_hot_auto"] = m["is_hot"]
            m["is_new_auto"] = m["is_new"]
            m["is_top_auto"] = m["is_top"]
        recent_chapters = get_recent_chapters()

    # Recherche (après les badges)
    if search_query:
        mangas_data = [m for m in mangas_data if search_query in m["name"].lower() or search_query in m["author"].lower() or search_query in m["category"].lower()]

    mangas_recents = sorted(
        mangas_data,
        key=lambda m: m["date_added"],
        reverse=True
    )[:6]

    popular_names = ["One Piece", "Naruto Shippuden", "Dragon Ball Z", "Solo Leveling"]
    popular_mangas = [m for m in mangas_data if m["name"] in popular_names]

    return render_template(
        "index.html",
        mangas=mangas_data,
        mangas_recents=mangas_recents,
        popular_mangas=popular_mangas,
        recent_chapters=recent_chapters,
        q=search_query,
        source=source,
        recent_chapters_7j=recent_chapters_7j,
        now=now
    )

@app.route('/ajouter_chapitre/<manga_name>', methods=['GET', 'POST'])
@login_required
@admin_required
def ajouter_chapitre_db(manga_name):
    source = get_source()
    if source == "db":
        manga = Manga.query.filter_by(name=manga_name).first_or_404()
        if request.method == 'POST':
            chapter_name = request.form['chapter_name'].strip()
            if not is_valid_name(chapter_name):
                flash("Nom de chapitre invalide.", "danger")
                return redirect(url_for('ajouter_chapitre_db', manga_name=manga_name, source=source))
            date_added = int(time.time())
            chapter = Chapter(name=chapter_name, manga_id=manga.id, date_added=date_added)
            db.session.add(chapter)
            db.session.flush()  # Pour obtenir l'ID si besoin

            # Crée le dossier physique pour le chapitre
            chapter_dir = os.path.join(MANGAS_DIR, manga.name, chapter_name)
            os.makedirs(chapter_dir, exist_ok=True)
            # Crée le fichier date_added.txt
            with open(os.path.join(chapter_dir, "date_added.txt"), "w") as f:
                f.write(str(date_added))
            # Ajoute les images au dossier du chapitre
            images = request.files.getlist('images')
            image_filenames = []
            for image in images:
                if image and image.filename:
                    filename = secure_filename(image.filename)
                    image.save(os.path.join(chapter_dir, filename))
                    image_filenames.append(filename)
            # Enregistre la liste des images dans le champ
            chapter.images = ";".join(image_filenames)  # ou json.dumps(image_filenames) si champ JSON
            db.session.commit()
            flash("Chapitre ajouté à la base de données avec images et dossier créé !", "success")
            return redirect(url_for('manga', manga_name=manga_name, source='db'))
        return render_template('ajouter_chapitre.html', manga=manga)
    else:
        if request.method == 'POST':
            chapter_name = request.form['chapter_name']
            ajouter_chapitre(manga_name, chapter_name)
            # Ajoute les images au dossier du chapitre
            chapter_dir = os.path.join(MANGAS_DIR, manga_name, chapter_name)
            images = request.files.getlist('images')
            for image in images:
                if image and image.filename:
                    filename = secure_filename(image.filename)
                    image.save(os.path.join(chapter_dir, filename))
            flash("Chapitre ajouté dans les fichiers avec images !", "success")
            return redirect(url_for('manga', manga_name=manga_name, source='fs'))
        return render_template(
            'ajouter_chapitre.html', 
            manga_name=manga_name
        )

@app.route('/ajouter_manga', methods=['GET', 'POST'])
@login_required
@admin_required
def ajouter_manga():
    source = get_source()
    if request.method == 'POST':
        name = request.form['name'].strip()
        if not is_valid_name(name):
            flash("Nom de manga invalide.", "danger")
            return redirect(url_for('ajouter_manga', source=source))
        author = request.form.get('author', '')
        year = request.form.get('year', '')
        category = request.form.get('category', '')
        syllabus = request.form.get('syllabus', '')
        rating = request.form.get('rating', '')
        date_added = int(time.time())

        # Gestion du fichier cover
        cover_file = request.files.get('cover')
        cover_filename = ''
        if cover_file and cover_file.filename:
            cover_filename = secure_filename(cover_file.filename)

        if source == "db":
            if Manga.query.filter_by(name=name).first():
                flash("Ce manga existe déjà.", "warning")
                return redirect(url_for('ajouter_manga', source=source))
            manga = Manga(
                name=name,
                author=author,
                year=year,
                category=category,
                syllabus=syllabus,
                cover_filename=cover_filename,
                date_added=date_added
            )
            db.session.add(manga)
            db.session.commit()
            # Crée le dossier physique du manga
            manga_dir = os.path.join(MANGAS_DIR, name)
            os.makedirs(manga_dir, exist_ok=True)
            # Sauvegarde la cover dans le dossier du manga
            if cover_file and cover_file.filename:
                cover_path = os.path.join(manga_dir, cover_filename)
                cover_file.save(cover_path)
            # --- Ajoute les fichiers texte ---
            with open(os.path.join(manga_dir, "author.txt"), "w", encoding="utf-8") as f:
                f.write(author)
            with open(os.path.join(manga_dir, "year.txt"), "w", encoding="utf-8") as f:
                f.write(year)
            with open(os.path.join(manga_dir, "category.txt"), "w", encoding="utf-8") as f:
                f.write(category)
            with open(os.path.join(manga_dir, "syllabus.txt"), "w", encoding="utf-8") as f:
                f.write(syllabus)
            with open(os.path.join(manga_dir, "cover.txt"), "w", encoding="utf-8") as f:
                f.write(cover_filename)
            with open(os.path.join(manga_dir, "rating.txt"), "w", encoding="utf-8") as f:
                f.write(rating)
            with open(os.path.join(manga_dir, "date_added.txt"), "w") as f:
                f.write(str(date_added))
        else:
            manga_dir = os.path.join(MANGAS_DIR, name)
            os.makedirs(manga_dir, exist_ok=True)
            if cover_file and cover_file.filename:
                cover_path = os.path.join(manga_dir, cover_filename)
                cover_file.save(cover_path)
            with open(os.path.join(manga_dir, "author.txt"), "w", encoding="utf-8") as f:
                f.write(author)
            with open(os.path.join(manga_dir, "year.txt"), "w", encoding="utf-8") as f:
                f.write(year)
            with open(os.path.join(manga_dir, "category.txt"), "w", encoding="utf-8") as f:
                f.write(category)
            with open(os.path.join(manga_dir, "syllabus.txt"), "w", encoding="utf-8") as f:
                f.write(syllabus)
            with open(os.path.join(manga_dir, "cover.txt"), "w", encoding="utf-8") as f:
                f.write(cover_filename)
            with open(os.path.join(manga_dir, "rating.txt"), "w", encoding="utf-8") as f:
                f.write(rating)
            with open(os.path.join(manga_dir, "date_added.txt"), "w") as f:
                f.write(str(date_added))

        flash("Manga ajouté avec succès !", "success")
        return redirect(url_for('index', source=source))
    return render_template('ajouter_manga.html')

def _get_manga_details_from_fs(manga_name_fs):
    """
    Récupère les détails d'un manga depuis le système de fichiers.
    Retourne un dictionnaire avec les détails, ou None si le manga n'est pas trouvé/valide.
    """
    manga_dir_path = os.path.join(MANGAS_DIR, manga_name_fs)
    if not os.path.isdir(manga_dir_path):
        app.logger.warning(f"Le chemin du manga n'est pas un dossier valide : {manga_dir_path}")
        return None

    cover_url = next((url_for('serve_manga_file', manga=manga_name_fs, filename=cover_file)
                      for cover_file in POSSIBLE_COVER_FILENAMES
                      if os.path.exists(os.path.join(manga_dir_path, cover_file))), None)

    syllabus_content = ""
    syllabus_path = os.path.join(manga_dir_path, "syllabus.txt")
    if os.path.exists(syllabus_path):
        try:
            with open(syllabus_path, 'r', encoding='utf-8') as f:
                syllabus_content = f.read().strip()
        except Exception as e:
            app.logger.error(f"Erreur lors de la lecture du syllabus {syllabus_path} pour {manga_name_fs}: {e}")

    date_added_path = os.path.join(manga_dir_path, "date_added.txt")
    date_added = 0
    if os.path.exists(date_added_path):
        try:
            with open(date_added_path, "r") as f:
                date_added = int(f.read().strip())
        except Exception:
            date_added = 0

    first_chapter = None
    try:
        chapter_dirs = sorted([d for d in os.listdir(manga_dir_path)
                               if os.path.isdir(os.path.join(manga_dir_path, d))])
        if chapter_dirs:
            first_chapter = chapter_dirs[0]
    except Exception as e:
        app.logger.error(f"Erreur lors de la récupération des chapitres pour {manga_name_fs}: {e}")

    category = "Autre"
    category_path = os.path.join(manga_dir_path, "category.txt")
    if os.path.exists(category_path):
        try:
            with open(category_path, 'r', encoding='utf-8') as f:
                category = f.read().strip()
        except Exception:
            category = "Autre"

    author = ""
    author_path = os.path.join(manga_dir_path, "author.txt")
    if os.path.exists(author_path):
        try:
            with open(author_path, 'r', encoding='utf-8') as f:
                author = f.read().strip()
        except Exception:
            author = ""

    year = ""
    year_path = os.path.join(manga_dir_path, "year.txt")
    if os.path.exists(year_path):
        try:
            with open(year_path, 'r', encoding='utf-8') as f:
                year = f.read().strip()
        except Exception:
            year = ""

    rating = ""
    rating_path = os.path.join(manga_dir_path, "rating.txt")
    if os.path.exists(rating_path):
        try:
            with open(rating_path, 'r', encoding='utf-8') as f:
                rating = f.read().strip()
        except Exception:
            rating = ""

    chapter_dirs = [
        d for d in os.listdir(manga_dir_path)
        if os.path.isdir(os.path.join(manga_dir_path, d))
    ]
    nb_chapitres = len(chapter_dirs)

    return {
        "name": manga_name_fs,
        "cover": cover_url,
        "syllabus": syllabus_content,
        "first_chapter": first_chapter,
        "date_added": date_added,
        "nb_chapitres": nb_chapitres,
        "category": category,
        "author": author,
        "year": year,
        "rating": rating
    }

@app.template_filter('datetimeformat')
def datetimeformat(value):
    if isinstance(value, (int, float)):
        return datetime.fromtimestamp(value).strftime('%d/%m/%Y')
    return value

def get_recent_chapters(limit=8):
    recent_chapters = []

    # 1. Récupération depuis la BDD
    now = datetime.utcnow()
    # 1. Récupération depuis la BDD (on prend plus large pour filtrer ensuite)
    for chapter in Chapter.query.order_by(Chapter.date_added.desc()).limit(limit * 4):
        if chapter.date_added and (now - datetime.fromtimestamp(chapter.date_added)).days < 7:
            manga = chapter.manga  # relation SQLAlchemy
            cover_url = url_for('serve_manga_file', manga=manga.name, filename=manga.cover_filename) if manga.cover_filename else url_for('static', filename='default-cover.jpg')
            recent_chapters.append({
                "manga_name": manga.name,
                "chapter_folder": chapter.name,
                "date_added": chapter.date_added,
                "cover": cover_url
            })

    seen = set((c["manga_name"], c["chapter_folder"]) for c in recent_chapters)
    for manga_name_fs in os.listdir(MANGAS_DIR):
        manga_dir = os.path.join(MANGAS_DIR, manga_name_fs)
        if not os.path.isdir(manga_dir):
            continue
        # Cherche la cover
        cover_url = next(
            (url_for('serve_manga_file', manga=manga_name_fs, filename=cover_file)
             for cover_file in POSSIBLE_COVER_FILENAMES
             if os.path.exists(os.path.join(manga_dir, cover_file))),
            url_for('static', filename='default-cover.jpg')
        )
        # Ajoute chaque chapitre
        for chapter_folder in os.listdir(manga_dir):
            chapter_path = os.path.join(manga_dir, chapter_folder)
            if os.path.isdir(chapter_path):
                if (manga_name_fs, chapter_folder) in seen:
                    continue
                date_added_path = os.path.join(chapter_path, "date_added.txt")
                try:
                    with open(date_added_path, "r") as f:
                        date_added = int(f.read().strip())
                except Exception:
                    date_added = 0
                if date_added and (now - datetime.fromtimestamp(date_added)).days < 7:
                    recent_chapters.append({
                        "manga_name": manga_name_fs,
                        "chapter_folder": chapter_folder,
                        "date_added": date_added,
                        "cover": cover_url
                    })

    # Trie et limite la liste finale
    recent_chapters = sorted(recent_chapters, key=lambda c: c["date_added"], reverse=True)[:limit]
    return recent_chapters

@app.route('/derniers-chapitres')
def derniers_chapitres():
    source = get_source()
    if source == "db":
        now = datetime.utcnow()
        chapters_db = Chapter.query.order_by(Chapter.date_added.desc()).limit(32).all()
        recent_chapters = []
        manga_ids = [chap.manga_id for chap in chapters_db]
        mangas_dict = {m.id: m for m in Manga.query.filter(Manga.id.in_(manga_ids)).all()}

        for chap in chapters_db:
            if chap.date_added or (now - datetime.fromtimestamp(chap.date_added)).days < 7:
                manga = mangas_dict.get(chap.manga_id)
                recent_chapters.append({
                    "manga_name": manga.name if manga else "",
                    "chapter_folder": chap.name,
                    "date_added": chap.date_added,
                    "cover": get_cover_url(manga.name) if manga else url_for('static', filename='default-cover.jpg'),
                    "chapter_title": chap.name,
                    "is_hot": hasattr(manga, "nb_lectures_recent") and manga.nb_lectures_recent > 100,
                    "is_new": (now - datetime.fromtimestamp(chap.date_added)).days < 7 if chap.date_added else False
                })
    else:
        recent_chapters = get_recent_chapters()
    return render_template('derniers_chapitres.html', recent_chapters=recent_chapters)

@app.route("/autocomplete")
def autocomplete():
    query = request.args.get("q", "").lower()
    all_mangas_data = [
        _get_manga_details_from_fs(manga_name_fs)
        for manga_name_fs in os.listdir(MANGAS_DIR)
        if os.path.isdir(os.path.join(MANGAS_DIR, manga_name_fs))
    ]
    all_mangas_data = [m for m in all_mangas_data if m is not None]
    results = [
        m["name"] for m in all_mangas_data
        if query in m["name"].lower()
    ][:8]
    return {"results": results}

@app.route("/annuaire")
def annuaire():
    categorie = request.args.get("categorie")
    lettre = request.args.get("lettre")
    source = get_source()
    if source == "db":
        mangas_db = Manga.query.all()
        all_mangas_data = []
        for m in mangas_db:
            manga_dict = {
                "name": m.name,
                "cover": get_cover_url(m.name),
                "syllabus": m.syllabus,
                "date_added": m.date_added,
                "category": m.category,
                "author": m.author,
                "year": m.year,
                "rating": m.ratings,
                "nb_chapitres": len(getattr(m, "chapters", [])),
                "is_hot_manual": m.is_hot,
                "is_new_manual": m.is_new,
                "is_top_manual": m.is_top,
            }
            auto_badges = compute_badges(manga_dict.copy())
            manga_dict["is_hot_auto"] = auto_badges["is_hot"]
            manga_dict["is_new_auto"] = auto_badges["is_new"]
            manga_dict["is_top_auto"] = auto_badges["is_top"]
            all_mangas_data.append(manga_dict)
    else:
        all_mangas_data = []
        for m in os.listdir(MANGAS_DIR):
            manga = _get_manga_details_from_fs(m)
            if manga:
                manga = compute_badges(manga)
                all_mangas_data.append(manga)
    all_mangas_data = [m for m in all_mangas_data if m is not None]

    # Filtrage par catégorie
    if categorie:
        all_mangas_data = [m for m in all_mangas_data if m.get('category', 'Toutes') == categorie]

    # Filtrage par lettre
    if lettre:
        all_mangas_data = [m for m in all_mangas_data if m["name"].upper().startswith(lettre.upper())]

    # Indexation alphabetique
    lettres = sorted({m["name"][0].upper() for m in all_mangas_data if m["name"]})

    # Liste des catégories
    categories = sorted({m.get('category', 'Toutes') for m in all_mangas_data})

    mangas_sorted = sorted(all_mangas_data, key=lambda m: m['name'].lower())

    return render_template(
        "annuaire.html",
        mangas=mangas_sorted,
        categories=categories,
        selected_category=categorie,
        lettres=lettres,
        selected_lettre=lettre
    )

@app.route('/contact', methods=['GET', 'POST'])
def contact():
    if request.method == 'POST':
        email = request.form.get('email')
        message = request.form.get('message')
        if not email or not message or not re.match(r"[^@]+@[^@]+\.[^@]+", email):
            flash("Veuillez remplir tous les champs avec un email valide.", "danger")
            return redirect(url_for('contact'))

        msg = Message(
            subject="Nouveau message d'un utilisateur de Yomi-Scan",
            sender=email,
            reply_to=email,
            recipients=[app.config['MAIL_USERNAME']],
            body=f"Message de : {email}\n\n{message}"
        )
        try:
            mail.send(msg)
            flash("Votre message a bien été envoyé. Merci !", "success")
        except Exception as e:
            flash("Erreur lors de l'envoi du message. Veuillez réessayer plus tard.", "danger")
    return render_template('contact.html')

@app.route("/manga/<manga_name>/<chapter_name>")
def reader(manga_name, chapter_name):
    chapter_dir = os.path.join(MANGAS_DIR, manga_name, chapter_name)
    if not os.path.isdir(chapter_dir):
        return render_template("erreur_chapitre.html", manga_name=manga_name, chapter_name=chapter_name), 404

    images = sorted([
        f for f in os.listdir(chapter_dir)
        if f.lower().endswith(('.jpg', '.jpeg', '.png', '.webp'))
    ])
    if not images:
        return render_template("erreur_chapitre.html", manga_name=manga_name, chapter_name=chapter_name), 404

    # Marquer le chapitre comme "lu" pour l'utilisateur connecté
    if current_user.is_authenticated:
        manga = Manga.query.filter_by(name=manga_name).first()
        if manga:
            # Marque comme lu
            progress = ReadingProgress.query.filter_by(
                user_id=current_user.id, manga_id=manga.id, chapter_name=chapter_name
            ).first()
            if not progress:
                progress = ReadingProgress(user_id=current_user.id, manga_id=manga.id, chapter_name=chapter_name)
                db.session.add(progress)
            else:
                progress.last_read_at = datetime.utcnow()
            db.session.commit()
            # Ajoute à l'historique
            add_to_history(current_user.id, manga.id, chapter_name)
    # Récupère la liste des chapitres pour ce manga
    chapters = sorted(
        [d for d in os.listdir(os.path.join(MANGAS_DIR, manga_name)) if os.path.isdir(os.path.join(MANGAS_DIR, manga_name, d))],
        key=lambda x: (0, int(re.findall(r'\d+', x)[0])) if re.findall(r'\d+', x) else (1, x.lower())
    )
    try:
        idx = chapters.index(chapter_name)
    except ValueError:
        idx = -1
    prev_chapter = url_for('reader', manga_name=manga_name, chapter_name=chapters[idx-1]) if idx > 0 else None
    next_chapter = url_for('reader', manga_name=manga_name, chapter_name=chapters[idx+1]) if idx != -1 and idx < len(chapters)-1 else None

    return render_template(
        "reader.html",
        manga_name=manga_name,
        chapter_name=chapter_name,
        images=images,
        prev_chapter=prev_chapter,
        next_chapter=next_chapter,
        all_chapters=chapters
    )

# Helpers pour token / mails
def _get_serializer():
    return URLSafeTimedSerializer(app.config['SECRET_KEY'])

def generate_reset_token(email):
    s = _get_serializer()
    return s.dumps(email, salt='password-reset-salt')

def verify_reset_token(token, max_age=1800):
    s = _get_serializer()
    try:
        email = s.loads(token, salt='password-reset-salt', max_age=max_age)
        return email
    except Exception:
        return None

def send_reset_email(user):
    token = generate_reset_token(user.email)
    created_at = int(time.time())  # Timestamp actuel
    reset_url = url_for('reset_password', token=token, created_at=created_at, _external=True)
    body = render_template('emails/reset_password.txt', user=user, site_name=app.config['SITE_NAME'], reset_url=reset_url)
    sender = f"{app.config['SITE_NAME']} <{app.config.get('MAIL_USERNAME')}>"
    msg = Message('Réinitialisation du mot de passe - Yomi-Scan',
                  sender=sender,
                  recipients=[user.email])
    msg.body = body
    try:
        mail.send(msg)
    except Exception as e:
        app.logger.error(f"Erreur envoi email reset à {user.email}: {e}")

def send_welcome_email(user):
    body = render_template('emails/welcome.txt', user=user, site_name=app.config['SITE_NAME'])
    sender = f"{app.config['SITE_NAME']} <{app.config.get('MAIL_USERNAME')}>"
    msg = Message('Bienvenue sur Yomi-Scan',
                  sender=sender,
                  recipients=[user.email])
    msg.body = body
    try:
        mail.send(msg)
    except Exception as e:
        app.logger.error(f"Erreur envoi email bienvenue à {user.email}: {e}")

@app.route('/register', methods=['GET', 'POST'])
def register():
    if current_user.is_authenticated:
        flash("Vous êtes déjà connecté. Veuillez vous déconnecter avant de créer un nouveau compte.", "info")
        return redirect(url_for('profile'))

    form = RegisterForm()
    if form.validate_on_submit():
        username = form.username.data
        email = form.email.data
        password = form.password.data

        # Vérifie si l'utilisateur existe déjà
        if User.query.filter_by(username=username).first():
            flash("Nom d'utilisateur déjà pris.", 'danger')
            return render_template('register.html', form=form)
        if User.query.filter_by(email=email).first():
            flash("Email déjà utilisé.", 'danger')
            return render_template('register.html', form=form)

        user = User(username=username, email=email)
        user.set_password(password)
        db.session.add(user)
        try:
            db.session.commit()
        except Exception:
            db.session.rollback()
            flash("Nom d'utilisateur ou email déjà utilisé.", "danger")
            return render_template('register.html', form=form)
        # envoi email de bienvenue (silencieux en cas d'erreur)
        send_welcome_email(user)
        flash("Inscription réussie, un email de bienvenue a été envoyé.", "success")
        return redirect(url_for('login'))
    return render_template('register.html', form=form)

@app.route('/login', methods=['GET', 'POST'])
def login():
    login_form = LoginForm()
    register_form = RegisterForm()

    form_type = request.form.get('form_type')

    if form_type == 'login' and login_form.validate_on_submit():
        # Vérifie si l'utilisateur se connecte avec un email ou un nom d'utilisateur
        user = User.query.filter(
            (User.username == login_form.username.data) | (User.email == login_form.username.data)
        ).first()

        if user and user.check_password(login_form.password.data):
            login_user(user)
            return redirect(url_for('index'))
        else:
            flash('Nom d\'utilisateur, email ou mot de passe incorrect.', 'danger')

    elif form_type == 'register' and register_form.validate_on_submit():
        username = register_form.username.data
        email = register_form.email.data
        password = register_form.password.data

        # Vérifie si l'utilisateur existe déjà
        if User.query.filter_by(username=username).first():
            flash("Nom d'utilisateur déjà pris.", 'danger')
        elif User.query.filter_by(email=email).first():
            flash("Email déjà utilisé.", 'danger')
        else:
            user = User(username=username, email=email)
            user.set_password(password)
            db.session.add(user)
            db.session.commit()
            flash("Inscription réussie, connectez-vous !", 'success')
            return redirect(url_for('login'))

    return render_template('login.html', login_form=login_form, register_form=register_form)

@app.route('/logout')
@login_required
def logout():
    logout_user()
    flash("Déconnexion réussie. Connectez-vous pour commencer à profiter de vos mangas préférés.", "success")
    return redirect(url_for('login'))

@app.route('/profile')
@login_required
def profile():
    favorites = Favorite.query.filter_by(user_id=current_user.id).all()
    history = ReadingHistory.query.filter_by(user_id=current_user.id)\
        .order_by(ReadingHistory.last_read_at.desc()).all()
    return render_template('profile.html', favorites=favorites, history=history)

@app.route("/mangas/<manga_name>/<chapter_name>/<filename>")
def manga_image(manga_name, chapter_name, filename):
    file_path = os.path.join(MANGAS_DIR, manga_name, chapter_name, filename)
    if not os.path.exists(file_path):
        return "Fichier introuvable", 404
    return send_from_directory(os.path.join(MANGAS_DIR, manga_name, chapter_name), filename)

@app.route('/admin/manga_status/<manga_name>', methods=['GET', 'POST'])
@login_required
def admin_manga_status(manga_name):
    manga = Manga.query.filter_by(name=manga_name).first_or_404()
    if request.method == 'POST':
        # Mettre à jour l'état du manga
        manga.status = request.form.get('status')

        # Mettre à jour les badges
        manga.is_hot = 'is_hot' in request.form
        manga.is_new = 'is_new' in request.form
        manga.is_top = 'is_top' in request.form

        # Sauvegarder les modifications
        db.session.commit()
        flash("Statuts et état du manga mis à jour avec succès.", "success")
        return redirect(url_for('manga', manga_name=manga.name))

    return render_template('admin_manga_status.html', manga=manga)


@app.route("/manga/<manga_name>")
def manga(manga_name):
    source = get_source()
    page = int(request.args.get("page", 1))
    per_page = 10

    if source == "db":
        manga_obj = Manga.query.filter_by(name=manga_name).first_or_404()

        # Incrémenter les vues
        manga_obj.views = (manga_obj.views or 0) + 1
        db.session.commit()

        # Récupérer les chapitres
        chapters = Chapter.query.filter_by(manga_id=manga_obj.id).order_by(Chapter.date_added.desc()).all()
        chapters_data = []
        for chap in chapters:
            is_read = False
            if current_user.is_authenticated:
                progress = ReadingProgress.query.filter_by(user_id=current_user.id, manga_id=manga_obj.id, chapter_name=chap.name).first()
                is_read = progress is not None

            chapters_data.append({
                "folder": chap.name,
                "display": getattr(chap, 'display_name', chap.name),
                "date_added": chap.date_added,
                "is_new_auto": (datetime.utcnow() - datetime.fromtimestamp(chap.date_added)).days < 7 if chap.date_added else False,
                "is_hot_auto": getattr(chap, 'nb_lectures_recent', 0) > 100,
                "is_top_auto": False,  # Non applicable par chapitre
                "is_read": is_read  # Ajout de la logique is_read
            })

        # Pagination des chapitres
        total = len(chapters_data)
        start = (page - 1) * per_page
        end = start + per_page
        chapters_paginated = chapters_data[start:end]
        total_pages = (total + per_page - 1) // per_page

        manga_data = {
            "name": manga_obj.name,
            "cover": get_cover_url(manga_obj.name),
            "syllabus": manga_obj.syllabus,
            "category": manga_obj.category,
            "author": manga_obj.author,
            "year": manga_obj.year,
            "rating": manga_obj.ratings,
            "date_added": manga_obj.date_added,
            "views": manga_obj.views,
            "status": manga_obj.status,
            "is_hot_manual": manga_obj.is_hot,
            "is_new_manual": manga_obj.is_new,
            "is_top_manual": manga_obj.is_top
        }

        # Calcul des badges automatiques
        auto_badges = compute_badges(manga_data.copy())
        manga_data["is_hot_auto"] = auto_badges["is_hot"]
        manga_data["is_new_auto"] = auto_badges["is_new"]
        manga_data["is_top_auto"] = auto_badges["is_top"]

        # Vérifier si le manga est dans les favoris
        is_fav = False
        if current_user.is_authenticated:
            is_fav = Favorite.query.filter_by(user_id=current_user.id, manga_id=manga_obj.id).first() is not None
        manga_data["is_favorite"] = is_fav

        # Récupérer les commentaires
        comments = Comment.query.filter_by(manga_id=manga_obj.id).order_by(Comment.created_at.desc()).all()
        manga_data["comments"] = comments

    else:
        # Gestion pour le système de fichiers
        manga_data = _get_manga_details_from_fs(manga_name)
        if not manga_data:
            abort(404)

        chapters = sorted(
            [d for d in os.listdir(os.path.join(MANGAS_DIR, manga_name)) if os.path.isdir(os.path.join(MANGAS_DIR, manga_name, d))],
            key=lambda x: x.lower()
        )
        total = len(chapters)
        start = (page - 1) * per_page
        end = start + per_page
        chapters_paginated = []
        for chap in chapters[start:end]:
            is_read = False
            if current_user.is_authenticated:
                progress = ReadingProgress.query.filter_by(user_id=current_user.id, manga_id=manga_data["id"], chapter_name=chap).first()
                is_read = progress is not None

            chapters_paginated.append({
                'folder': chap,
                'display': chap,
                'date_added': None,  # Ajoute une valeur par défaut si non disponible
                'is_new_auto': False,  # Ajoute une valeur par défaut si non disponible
                'is_hot_auto': False,  # Ajoute une valeur par défaut si non disponible
                'is_top_auto': False,  # Ajoute une valeur par défaut si non disponible
                'is_read': is_read  # Ajout de la logique is_read
            })

    return render_template(
        "manga.html",
        manga_name=manga_data["name"],
        manga=manga_data,
        avg_rating=manga_data.get("avg_rating", "Non noté"),
        chapters=chapters_paginated,
        page=page,
        total_pages=total_pages
    )

@app.route('/manga/<manga_name>/<chapter_name>/mark_as_read', methods=['POST'])
@login_required
def mark_as_read(manga_name, chapter_name):
    manga = Manga.query.filter_by(name=manga_name).first_or_404()
    progress = ReadingProgress.query.filter_by(
        user_id=current_user.id, manga_id=manga.id, chapter_name=chapter_name
    ).first()

    if not progress:
        progress = ReadingProgress(user_id=current_user.id, manga_id=manga.id, chapter_name=chapter_name)
        db.session.add(progress)
    else:
        progress.last_read_at = datetime.utcnow()

    db.session.commit()
    return redirect(url_for('manga', manga_name=manga_name))

@app.route("/mangas/<manga>/<filename>")
def serve_manga_file(manga, filename):
    file_path = os.path.join(MANGAS_DIR, manga, filename)
    if not os.path.exists(file_path):
        return "Fichier introuvable", 404
    return send_from_directory(os.path.join(MANGAS_DIR, manga), filename)

def safe_name(name):
    # Autorise seulement lettres, chiffres, tirets, underscores
    return re.sub(r'[^a-zA-Z0-9_\-]', '', name)

@app.context_processor
def inject_categories():
    source = get_source()
    if source == "db":
        categories = sorted({m.category or "Autre" for m in Manga.query.all()})
    else:
        all_mangas_data = [
            _get_manga_details_from_fs(manga_name_fs)
            for manga_name_fs in os.listdir(MANGAS_DIR)
            if os.path.isdir(os.path.join(MANGAS_DIR, manga_name_fs))
        ]
        all_mangas_data = [m for m in all_mangas_data if m is not None]
        categories = sorted({m.get('category', 'Autre') for m in all_mangas_data})
    return dict(categories=categories)

def get_source():
    source = request.args.get("source")
    if source == "db":
        return "db"
    elif source == "fs":
        return "fs"
    return "db" if USE_DATABASE else "fs"

@app.route("/manga/<manga_name>/<chapter_name>/download")
def download_chapter(manga_name, chapter_name):
    chapter_dir = os.path.join(MANGAS_DIR, manga_name, chapter_name)
    if not os.path.isdir(chapter_dir):
        return "Chapitre introuvable", 404

    images = [f for f in sorted(os.listdir(chapter_dir)) if f.lower().endswith(('.jpg', '.jpeg', '.png', '.webp'))]
    if not images:
        return "Aucune image à télécharger", 404

    zip_buffer = io.BytesIO()
    with zipfile.ZipFile(zip_buffer, "w") as zip_file:
        for img in images:
            img_path = os.path.join(chapter_dir, img)
            zip_file.write(img_path, arcname=img)
    zip_buffer.seek(0)

    return (
        zip_buffer.getvalue(), 200, {
            "Content-Type": "application/cbz",
            "Content-Disposition": f"attachment; filename={chapter_name}.cbz"
        }
    )
@app.route('/manga/<manga_name>/favori', methods=['POST'])
@login_required
def toggle_favorite(manga_name):
    manga = Manga.query.filter_by(name=manga_name).first_or_404()
    fav = Favorite.query.filter_by(user_id=current_user.id, manga_id=manga.id).first()
    if fav:
        # Supprime le favori existant
        db.session.delete(fav)
        db.session.commit()
    else:
        # Ajoute un nouveau favori
        new_fav = Favorite(user_id=current_user.id, manga_id=manga.id)
        db.session.add(new_fav)
        db.session.commit()
    return redirect(url_for('manga', manga_name=manga_name))

@app.route('/manga/<manga_name>/comment', methods=['POST'])
@login_required
def add_comment(manga_name):
    manga = Manga.query.filter_by(name=manga_name).first_or_404()
    content = request.form.get('content')
    if not content:
        flash("Le contenu du commentaire ne peut pas être vide.", "danger")
        return redirect(url_for('manga', manga_name=manga_name))
    
    
    comment = Comment(user_id=current_user.id, manga_id=manga.id, content=content)
    db.session.add(comment)
    db.session.commit()
    flash("Commentaire ajouté.", "success")
    return redirect(url_for('manga', manga_name=manga_name))

@app.route('/rate_manga/<manga_name>', methods=['POST'])
def rate_manga(manga_name):
    manga = Manga.query.filter_by(name=manga_name).first_or_404()
    # Utilise .get() pour éviter l'erreur KeyError si le champ 'rating' est absent
    rating_value = request.form.get('rating')
    if not rating_value:
        flash("Veuillez fournir une note valide.", "danger")
        return redirect(url_for('manga', manga_name=manga_name))
    
    try:
        value = float(rating_value)
    except ValueError:
        flash("La note doit être un nombre valide.", "danger")
        return redirect(url_for('manga', manga_name=manga_name))
    
    user_id = current_user.id if current_user.is_authenticated else None
    rating = Rating(manga_id=manga.id, value=value, user_id=user_id)
    db.session.add(rating)
    db.session.commit()
    flash("Merci pour votre note !", "success")
    return redirect(url_for('manga', manga_name=manga_name))

def add_to_history(user_id, manga_id, chapter_name):
    hist = ReadingHistory.query.filter_by(
        user_id=user_id,
        manga_id=manga_id,
        chapter_name=chapter_name
    ).first()
    if hist:
        hist.last_read_at = datetime.utcnow()
    else:
        hist = ReadingHistory(
            user_id=user_id,
            manga_id=manga_id,
            chapter_name=chapter_name,
            last_read_at=datetime.utcnow()
        )
        db.session.add(hist)
    db.session.commit()
    
@app.route('/reset_password/<token>', methods=['GET', 'POST'])
def reset_password(token):
    max_age = app.config.get('RESET_TOKEN_MAX_AGE', 1800)  # Durée de validité du token en secondes
    created_at = request.args.get('created_at', type=int)
    seconds_left = max_age 
    email = verify_reset_token(token, max_age=max_age)
    if not email:
        flash("Le lien de réinitialisation est invalide ou a expiré.", "danger")
        return redirect(url_for('forgot_password'))
    user = User.query.filter_by(email=email).first()
    if not user:
        flash("Utilisateur introuvable.", "danger")
        return redirect(url_for('forgot_password'))

    form = ResetPasswordForm()
    if form.validate_on_submit():
        user.set_password(form.password.data)
        user.reset_token_used = True  # Marque le token comme utilisé
        db.session.commit()
        flash("Mot de passe mis à jour !", "success")
        return redirect(url_for('login'))

    # Passe seconds_left au template
    return render_template('reset_password.html', form=form, token=token, created_at=created_at, max_age=max_age, seconds_left=seconds_left)


@app.route('/forgot_password', methods=['GET', 'POST'])
def forgot_password():
    form = ForgotPasswordForm()
    if form.validate_on_submit():
        user = User.query.filter_by(email=form.email.data).first()
        if user:
            user.reset_token_used = False  # Réinitialise l'état du token
            db.session.commit()
            send_reset_email(user)
        # Réponse non révélatrice pour sécurité
        flash("Si un compte existe pour cet email, un lien de réinitialisation a été envoyé.", "info")
        return redirect(url_for('login'))
    return render_template('forgot_password.html', form=form)


@app.route('/manga/<manga_name>/toggle_hot', methods=['POST'])
@login_required
def toggle_hot(manga_name):
    manga = Manga.query.filter_by(name=manga_name).first_or_404()
    manga.is_hot = not manga.is_hot  # Inverse le statut Hot
    db.session.commit()
    if manga.is_hot:
        flash(f"Le manga '{manga_name}' est maintenant marqué comme Hot.", "success")
    else:
        flash(f"Le manga '{manga_name}' n'est plus marqué comme Hot.", "success")
    return redirect(url_for('manga', manga_name=manga_name))


@app.route('/comment/<int:comment_id>/like', methods=['POST'])
@login_required
def like_comment(comment_id):
    comment = Comment.query.get_or_404(comment_id)
    existing = CommentLike.query.filter_by(user_id=current_user.id, comment_id=comment_id).first()
    if existing:
        if existing.is_like:
            flash("Vous avez déjà liké ce commentaire.", "danger")
        else:
            existing.is_like = True
            comment.likes = max((comment.likes if comment.likes is not None else 0) + 1, 0)
            comment.dislikes = max((comment.dislikes or 0) - 1, 0)
            db.session.commit()
            flash("Votre vote a été changé en like.", "success")
    else:
        like = CommentLike(user_id=current_user.id, comment_id=comment_id, is_like=True)
        db.session.add(like)
        comment.likes = (comment.likes if comment.likes is not None else 0) + 1
        db.session.commit()
        flash("Commentaire liké.", "success")
    return redirect(request.referrer or url_for('manga'))

@app.route('/comment/<int:comment_id>/dislike', methods=['POST'])
@login_required
def dislike_comment(comment_id):
    comment = Comment.query.get_or_404(comment_id)
    existing = CommentLike.query.filter_by(user_id=current_user.id, comment_id=comment_id).first()
    if existing:
        if not existing.is_like:
            flash("Vous avez déjà disliké ce commentaire.", "danger")
        else:
            existing.is_like = False
            comment.dislikes = (comment.dislikes if comment.dislikes is not None else 0) + 1
            comment.likes = (comment.likes if comment.likes is not None else 0) - 1
            db.session.commit()
            flash("Votre vote a été changé en dislike.", "success")
    else:
        dislike = CommentLike(user_id=current_user.id, comment_id=comment_id, is_like=False)
        db.session.add(dislike)
        comment.dislikes = (comment.dislikes or 0) + 1
        db.session.commit()
        flash("Commentaire disliké.", "success")
    return redirect(request.referrer or url_for('manga'))

@app.route('/comment/<int:comment_id>/report', methods=['POST'])
@login_required
def report_comment(comment_id):
    comment = Comment.query.get_or_404(comment_id)
    comment.reported = True
    db.session.commit()
    flash("Commentaire signalé à la modération.", "info")
    return redirect(request.referrer or url_for('manga'))

@app.route('/admin/moderation')
@login_required
@admin_required
def moderation():
    reported_comments = Comment.query.filter_by(reported=True).order_by(Comment.created_at.desc()).all()
    flash("Section de modération - Gérez les commentaires signalés.", "info")
    return render_template('moderation.html', comments=reported_comments)

@app.route('/comment/<int:comment_id>/delete', methods=['POST'])
@login_required
def delete_comment(comment_id):
    comment = Comment.query.get_or_404(comment_id)
    db.session.delete(comment)
    db.session.commit()
    flash("Commentaire supprimé.", "success")
    return redirect(url_for('moderation'))

@app.route('/comment/<int:comment_id>/ignore', methods=['POST'])
@login_required
def ignore_report(comment_id):
    comment = Comment.query.get_or_404(comment_id)
    comment.reported = False
    db.session.commit()
    flash("Signalement ignoré.", "info")
    return redirect(url_for('moderation'))

@app.route('/delete_account', methods=['GET', 'POST'])
@login_required
def delete_account():
    form = DeleteAccountForm()
    if form.validate_on_submit():
        if not current_user.check_password(form.password.data):
            flash("Mot de passe incorrect.", "danger")
            return redirect(url_for('delete_account'))
        user_id = current_user.id
        logout_user()
        user = User.query.get(user_id)
        if user:
            db.session.delete(user)
            db.session.commit()
            flash("Votre compte a bien été supprimé.", "success")
        return redirect(url_for('login'))
    return render_template('delete_account.html', form=form)

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000)) # Ensure all required configurations are set
    app.run(host="0.0.0.0", port=port, debug=True)