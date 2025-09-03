from app import app, db
from models import Manga

with app.app_context():
    manga = Manga.query.filter_by(name="Solo Leveling").first()
    if manga:
        manga.is_hot = True      # Pour HOT
        manga.is_new = False      # Pour NEW
        manga.is_top = False      # Pour TOP
        db.session.commit()
        print("Statuts mis à jour !")
        print("is_hot:", manga.is_hot, "is_new:", manga.is_new, "is_top:", manga.is_top)
    else:
        print("Manga non trouvé.")