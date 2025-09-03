from flask_wtf import FlaskForm
from wtforms import StringField, PasswordField, SubmitField
from wtforms.validators import DataRequired, Email

class LoginForm(FlaskForm):
    username = StringField('Nom d\'utilisateur ou Email :', validators=[DataRequired()])
    password = PasswordField('Mot de passe :', validators=[DataRequired()])
    submit = SubmitField('Connexion')

class RegisterForm(FlaskForm):
    username = StringField('Nom d\'utilisateur :', validators=[DataRequired()])
    email = StringField('Email :', validators=[DataRequired(), Email()])
    password = PasswordField('Mot de passe :', validators=[DataRequired()])
    submit = SubmitField('S\'inscrire')

class ForgotPasswordForm(FlaskForm):
    email = StringField('Email :', validators=[DataRequired(), Email()])
    submit = SubmitField('Envoyer')

class ResetPasswordForm(FlaskForm):
    password = PasswordField('Nouveau mot de passe :', validators=[DataRequired()])
    submit = SubmitField('Réinitialiser')

class DeleteAccountForm(FlaskForm):
    password = PasswordField('Mot de passe', validators=[DataRequired()])
    submit = SubmitField('Supprimer mon compte')