from app import app, db
from models import User

with app.app_context():
    for user in User.query.all():
        if user.username != "ykalipo":
            user.is_admin = False
        else:
            user.is_admin = True
    db.session.commit()
    print("Mise à jour des droits admin terminée.")