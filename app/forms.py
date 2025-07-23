from flask_wtf import FlaskForm
from wtforms import StringField, TextAreaField, SelectField, DateField, TimeField, SubmitField, DecimalField, PasswordField, BooleanField
from wtforms.validators import DataRequired, Optional, Email, NumberRange, Length
from wtforms.fields import EmailField
from wtforms_sqlalchemy.fields import QuerySelectField
from datetime import date
from app.models import Dossier

#formulaire timesheet
class TimesheetForm(FlaskForm):
    date = DateField('Date', format='%Y-%m-%d', validators=[DataRequired()])
    heure_debut = TimeField('Heure de début', format='%H:%M', validators=[DataRequired()])
    heure_fin = TimeField('Heure de fin', format='%H:%M', validators=[DataRequired()])
    
    description = TextAreaField('Description de la tâche', validators=[DataRequired()])
    dossier_id = SelectField("Dossier", choices=[], coerce=int, validators=[DataRequired()])
    #user_id = SelectField('Utilisateur', coerce=int)
    statut = SelectField('Statut', choices=[('en cours', 'En cours'), ('facturée', 'Facturée')], validators=[DataRequired()])
    taux_horaire = DecimalField("Taux horaire (€)", validators=[DataRequired(), NumberRange(min=0)], places=2)
    tva_applicable = SelectField('TVA applicable ?', choices=[('oui', 'Oui'), ('non', 'Non')], default='oui')

    submit = SubmitField('Enregistrer')

#formulaire client
class ClientForm(FlaskForm):
    societe = StringField("Socété", validators=[DataRequired()])
    email = StringField("Email", validators=[Optional(), Email()])
    telephone = StringField("Téléphone", validators=[Optional()])
    adresse = StringField("Adresse", validators=[Optional()])
    submit = SubmitField("Enregistrer")

#formulaire Dossiers
class DossierForm(FlaskForm):
    nom = StringField("Nature du dossier", validators=[DataRequired()])
    description = TextAreaField('Description')
    date_ouverture = DateField("Date d'ouverture", validators=[DataRequired()])
    procedure = SelectField("Procédures", choices=[('1ère Instance', '1ère Instance'), ('Appel', 'Appel'), ('Cassation', 'Cassation'), ('Conseil/Consultance','Conseil/Consultance')], validators=[DataRequired()])
    statut = SelectField("Statut", choices=[('En cours', 'En cours'), ('Clôturé', 'Clôturé')], validators=[DataRequired()])
    client_id = SelectField("Client", coerce=int, validators=[DataRequired()])
    submit = SubmitField("Enregistrer")


# Fonction pour les choix de Dossier dans QuerySelectField
def get_dossiers_choices():
    from app import app, db
    with app.app_context(): # Ensure we are in an application context
        return db.session.query(Dossier).filter_by(supprimé=False)

#formulaire Factures
class FactureForm(FlaskForm):
    date = DateField('Date', validators=[DataRequired()], default=date.today)
    montant_ht = DecimalField('Montant HT', validators=[DataRequired()])
    montant_ttc = DecimalField('Montant TTC', validators=[DataRequired()])
    statut = SelectField('Statut', choices=[('En attente', 'En attente'), ('Payée', 'Payée'), ('Annulée', 'Annulée')], validators=[DataRequired()])
    # Utilise query_factory et spécifie get_label
    dossier = QuerySelectField(
        'Dossier',
        query_factory=get_dossiers_choices, # Appelle cette fonction pour obtenir la requête
        get_label='nom', # Utilise 'nom' comme étiquette d'affichage pour les objets Dossier
        allow_blank=False, # Ne pas autoriser un choix vide
        validators=[DataRequired()]
    )
    submit = SubmitField('Enregistrer')


class LoginForm(FlaskForm):
    email = StringField('Email', validators=[DataRequired(), Email()])
    password = PasswordField('Mot de passe', validators=[DataRequired()])
    remember_me = BooleanField('Se souvenir de moi')
    submit = SubmitField('Se connecter')



class AjoutUtilisateurForm(FlaskForm):
    nom = StringField("Nom", validators=[DataRequired()])
    email = StringField("Email", validators=[DataRequired(), Email()])
    role = SelectField("Rôle", choices=[
        ('associé', 'Associé'),
        ('avocat', 'Avocat'),
        ('juriste', 'Juriste'),
        ('admin', 'Admin')
    ], validators=[DataRequired()])
    password = PasswordField("Mot de passe", validators=[DataRequired(), Length(min=6)])
    submit = SubmitField("Ajouter l'utilisateur")

class GenererFactureForm(FlaskForm):
    date = DateField('Date de la facture', validators=[DataRequired()])
    dossier = SelectField('Dossier concerné', coerce=int, validators=[DataRequired()])
    submit = SubmitField('Générer la facture')

class DummyForm(FlaskForm):
    pass  # uniquement utilisé pour CSRF dans le formulaire POST    

class DeleteForm(FlaskForm):
    submit = SubmitField("Supprimer")