from flask_sqlalchemy import SQLAlchemy
from datetime import datetime
from flask_login import UserMixin
from flask_bcrypt import generate_password_hash, check_password_hash
from itsdangerous import URLSafeTimedSerializer
from flask import current_app as app
import time


db = SQLAlchemy()

class Manga(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(120), unique=True, nullable=False)
    author = db.Column(db.String(120))
    year = db.Column(db.String(4))
    category = db.Column(db.String(64))
    syllabus = db.Column(db.Text)
    cover_filename = db.Column(db.String(256))
    date_added = db.Column(db.Integer, default=lambda: int(time.time()))
    is_hot = db.Column(db.Boolean, default=False)
    is_new = db.Column(db.Boolean, default=False)
    is_top = db.Column(db.Boolean, default=False)
    views = db.Column(db.Integer, default=0)
    status = db.Column(db.String(20), default="En cours")
    chapters = db.relationship('Chapter', backref='manga', lazy=True)
    ratings = db.relationship('Rating', backref='manga', lazy=True)
    comments = db.relationship('Comment', lazy=True)
    favorites = db.relationship('Favorite', backref='manga', lazy=True)
    histories = db.relationship('ReadingHistory', lazy=True)
    
class Chapter(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    manga_id = db.Column(db.Integer, db.ForeignKey('manga.id'), nullable=False)
    name = db.Column(db.String(128), nullable=False)
    date_added = db.Column(db.Integer)  # timestamp
    

class User(db.Model, UserMixin):
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(64), unique=True, nullable=False)
    email = db.Column(db.String(120), unique=True, nullable=False)
    password_hash = db.Column(db.String(128))
    reset_token_used = db.Column(db.Boolean, default=False)  # Nouveau champ
    role = db.Column(db.String(16), default="user")  # "admin" ou "user"
    is_admin = db.Column(db.Boolean, default=False)
    

    def set_password(self, password):
        self.password_hash = generate_password_hash(password).decode('utf-8')
    def check_password(self, password):
        return check_password_hash(self.password_hash, password)
    def get_reset_token(self):
        s = URLSafeTimedSerializer(app.config['SECRET_KEY'])
        return s.dumps({'user_id': self.id, 'created_at': int(time.time())})

    @staticmethod
    def verify_reset_token(token, expiration=1800):
        s = URLSafeTimedSerializer(app.config['SECRET_KEY'])
        try:
            data = s.loads(token, max_age=expiration)
        except Exception:
            return None, None
        return User.query.get(data['user_id']), data.get('created_at')

class Favorite(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    manga_id = db.Column(db.Integer, db.ForeignKey('manga.id'), nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

class Comment(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'))
    manga_id = db.Column(db.Integer, db.ForeignKey('manga.id'))
    content = db.Column(db.Text, nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    likes = db.Column(db.Integer, default=0)
    dislikes = db.Column(db.Integer, default=0)
    reported = db.Column(db.Boolean, default=False)
    user = db.relationship('User', backref='comments')

class Rating(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    manga_id = db.Column(db.Integer, db.ForeignKey('manga.id'), nullable=False)
    value = db.Column(db.Float, nullable=False)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=True)  # Null pour visiteurs anonymes
    timestamp = db.Column(db.DateTime, default=datetime.utcnow)

class ReadingHistory(db.Model):
    __tablename__ = 'reading_history'
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), primary_key=True)
    manga_id = db.Column(db.Integer, db.ForeignKey('manga.id'), primary_key=True)
    chapter_name = db.Column(db.String(120), primary_key=True)
    last_read_at = db.Column(db.DateTime, default=datetime.utcnow)

    user = db.relationship('User', backref='reading_history')
    manga = db.relationship('Manga', backref='reading_histories')

class CommentLike(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'))
    comment_id = db.Column(db.Integer, db.ForeignKey('comment.id'))
    is_like = db.Column(db.Boolean)  # True=like, False=dislike

    __table_args__ = (db.UniqueConstraint('user_id', 'comment_id', name='_user_comment_uc'),)

class ReadingProgress(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    manga_id = db.Column(db.Integer, db.ForeignKey('manga.id'), nullable=False)
    chapter_name = db.Column(db.String(120), nullable=False)
    last_read_at = db.Column(db.DateTime, default=datetime.utcnow)

    user = db.relationship('User', backref='reading_progress')
    manga = db.relationship('Manga', backref='progress_entries')  # Renommé ici pour éviter les conflits