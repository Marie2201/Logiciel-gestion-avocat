from flask_wtf import FlaskForm
from wtforms import StringField, TextAreaField, SelectField, DateField, TimeField, SubmitField, DecimalField, PasswordField, BooleanField, HiddenField
from wtforms.validators import DataRequired, Optional, Email, NumberRange, Length, EqualTo, Regexp, ValidationError
from wtforms.fields import EmailField
from wtforms_sqlalchemy.fields import QuerySelectField
from datetime import date
from app.models import Dossier, Client
from flask_wtf.file import FileField, FileAllowed, FileRequired

#formulaire timesheet
STATUT_CHOICES = [
    ('En cours',    'En cours'),
    ('À facturer',  'À facturer'),
    ('Facturée',    'Facturée'),
    ('Payée',       'Payée'),
    ('Annulée',     'Annulée'),
]

class TimesheetForm(FlaskForm):
    date = DateField('Date', format='%Y-%m-%d', validators=[DataRequired()])
    type_facturation = SelectField(
        'Type',
        choices=[('horaire', 'À l’heure'), ('forfait', 'Forfait')],
        validators=[DataRequired()],
        default='horaire'
    )

    # HORAIRE (optionnels au niveau du Form ; imposés conditionnellement)
    heure_debut   = TimeField('Heure début',  format='%H:%M', validators=[Optional()])
    heure_fin     = TimeField('Heure fin',    format='%H:%M', validators=[Optional()])
    taux_horaire  = DecimalField('Taux horaire', places=2, validators=[Optional(), NumberRange(min=0)])

    # Statut (nouveau)
    statut = SelectField('Statut', choices=STATUT_CHOICES,
                         validators=[DataRequired()], default='En cours')

    # FORFAIT (optionnel ici, imposé conditionnellement)
    montant_forfait = DecimalField('Montant forfait', places=2, validators=[Optional(), NumberRange(min=0)])

    tva_applicable = SelectField('TVA', choices=[('non', 'Non'), ('oui', 'Oui')],
                                 validators=[DataRequired()], default='non')
    devise = SelectField('Devise',
                         choices=[('XOF','FCFA'),('EUR','EUR'),('USD','USD')],
                         validators=[DataRequired()], default='XOF')

    description = TextAreaField('Description', validators=[Optional()])
    dossier_id = SelectField('Dossier', coerce=int, validators=[DataRequired()],
                             choices=[], render_kw={'class': 'form-select select2-ajax'})
    submit = SubmitField('Enregistrer')

    def validate(self, extra_validators=None):
        base_ok = super().validate(extra_validators)
        ok = True

        if self.type_facturation.data == 'horaire':
            if not self.heure_debut.data:
                self.heure_debut.errors.append('Requis pour la facturation horaire.')
                ok = False
            if not self.heure_fin.data:
                self.heure_fin.errors.append('Requis pour la facturation horaire.')
                ok = False
            if self.taux_horaire.data is None:
                self.taux_horaire.errors.append('Requis pour la facturation horaire.')
                ok = False

        elif self.type_facturation.data == 'forfait':
            if self.montant_forfait.data is None:
                self.montant_forfait.errors.append('Requis pour la facturation au forfait.')
                ok = False

        return base_ok and ok


#formulaire client
class ClientForm(FlaskForm):
    societe = StringField("Client", validators=[DataRequired()])
    email = StringField("Email", validators=[Optional(), Email()])
    telephone = StringField("Téléphone", validators=[Optional()])
    adresse = StringField("Adresse", validators=[Optional()])
    submit = SubmitField("Enregistrer")

#formulaire Dossiers
NUMERO_REGEX = r'^\d{1,3}(?:\.\d{3})*/\d{2}$'
class DossierForm(FlaskForm):
    numero = StringField(
        'ID Dossier',
        validators=[
            Optional(),
            Regexp(NUMERO_REGEX, message="Format attendu : 13.897/25")
        ]
    )
    nom = StringField("Nature du dossier", validators=[DataRequired()])
    description = TextAreaField('Description')
    date_ouverture = DateField("Date d'ouverture", validators=[DataRequired()])
    procedures = StringField("Procédures", validators=[Optional(), Length(max=1000)])
    statut = SelectField("Statut", choices=[('En cours', 'En cours'), ('Clôturé', 'Clôturé')], validators=[DataRequired()])
    client_id = SelectField("Client", coerce=int, validators=[DataRequired()],
                            choices=[], render_kw={'class': 'form-select select2-ajax'})
    user_id = SelectField('Attribuer à', coerce=int, choices=[])
    submit = SubmitField("Enregistrer")

    def validate_numero(self, field):
        """Optionnel : lever uniquement si VRAI doublon (même client, même numéro, même procédure)."""
        q = Dossier.query.filter_by(
            client_id=self.client_id.data,
            numero=field.data,
            procedures=self.procedures.data  # ou 'procedure=self.procedure.data' si texte
        )
        # si édition, exclure le dossier en cours
        if getattr(self, 'obj_id', None):
            q = q.filter(Dossier.id != self.obj_id)

        if q.count() > 0:
            # soit lever une erreur, soit juste un message flash si tu veux autoriser malgré tout
            raise ValidationError("Ce numéro existe déjà pour ce client et cette procédure.")
        
# Fonction pour les choix de Dossier dans QuerySelectField
def get_dossiers_choices():
    from app import app, db
    with app.app_context(): # Ensure we are in an application context
        return db.session.query(Dossier).filter_by(supprimé=False)

#formulaire Factures
class FactureForm(FlaskForm):
    date = DateField('Date', validators=[DataRequired()])
    dossier = SelectField('Dossier', coerce=int, validators=[DataRequired()])
    devise = SelectField('Devise', choices=[('XOF', 'FCFA'), ('EUR', 'EUR'), ('USD', 'USD')])
    montant_ht = DecimalField('Montant HT', places=2, rounding=None)
    tva_applicable = BooleanField('TVA')
    montant_ttc = DecimalField('Montant TTC', places=2, rounding=None)
    statut = SelectField('Statut', choices=[
        ('Brouillon','Brouillon'),
        ('En attente','En attente'),
        ('Non payée','Non payée'),
        ('Partiellement payée','Partiellement payée'),
        ('Payée','Payée'),
        ('Impayée','Impayée'),
        ('Annulée','Annulée'),
    ])
    submit = SubmitField('Enregistrer les modifications')


class LoginForm(FlaskForm):
    email = StringField('Email', validators=[DataRequired(), Email()])
    password = PasswordField('Mot de passe', validators=[DataRequired()])
    remember_me = BooleanField('Se souvenir de moi')
    submit = SubmitField('Se connecter')



class AjoutUtilisateurForm(FlaskForm):
    nom = StringField("Nom", validators=[DataRequired()])
    email = StringField("Email", validators=[DataRequired(), Email()])
    role = SelectField("Rôle", choices=[
        ('managing-partner', 'Managing-Partner'),
        ('partner', 'Partner'),
        ('managing-associate', 'Managing-Associate'),
        ('avocat', 'Avocat'),
        ('juriste', 'Juriste'),
        ('admin', 'Admin'),
        ('clerc', 'Clerc'),
        ('secrétaire', 'Secrétaire'),
        ('comptabilité', 'Comptabilité'),
        ('qualité', 'Qualité'),
        ('user-manager', 'User-manager')

    ], validators=[DataRequired()])
    password = PasswordField("Mot de passe", validators=[DataRequired(), Length(min=6)])
    submit = SubmitField("Ajouter l'utilisateur")

class GenererFactureForm(FlaskForm):
    date = DateField('Date de la facture', validators=[DataRequired()])
    dossier = SelectField('Dossier concerné', coerce=int, validators=[DataRequired()])
    submit = SubmitField('Générer la facture')


class DocumentForm(FlaskForm):
    fichier = FileField('Document', validators=[FileRequired(), FileAllowed(['pdf', 'doc', 'docx', 'png', 'jpg', 'jpeg'], 'Fichiers autorisés uniquement')])
    dossier_id = SelectField('Dossier', coerce=int)
    submit = SubmitField('Téléverser')


class RegistrationForm(FlaskForm):
    nom = StringField('Nom', validators=[DataRequired()])
    email = StringField('Email', validators=[DataRequired(), Email()])
    password = PasswordField('Mot de passe', validators=[DataRequired(), Length(min=6)])
    confirm_password = PasswordField('Confirmer le mot de passe', validators=[DataRequired(), EqualTo('password')])
    role = SelectField('Rôle', choices=[('admin', 'Admin'), ('managing-partner', 'Managing-Partner'), ('partner', 'Partner'),('managing-associate', 'Managing-Associate'),('avocat', 'Avocat'), ('juriste', 'Juriste')], validators=[DataRequired()])
    submit = SubmitField('Créer le compte')


class UserForm(FlaskForm):
    nom = StringField('Nom', validators=[DataRequired()])
    email = StringField('Email', validators=[DataRequired(), Email()])
    role = SelectField("Rôle", choices=[
        ('managing-partner', 'Managing-Partner'),
        ('partner', 'Partner'),
        ('managing-associate', 'Managing-Associate'),
        ('avocat', 'Avocat'),
        ('juriste', 'Juriste'),
        ('admin', 'Admin'),
        ('clerc', 'Clerc'),
        ('secrétaire', 'Secrétaire'),
        ('comptabilité', 'Comptabilité'),
        ('qualité', 'Qualité'),
        ('user-manager', 'User-manager')])


#attribuer un dossier à 
class AttributionForm(FlaskForm):
    dossier_id = SelectField('Dossier', coerce=int)
    user_id = SelectField('Attribuer à', coerce=int)
    submit = SubmitField('Attribuer')


class ChangerReferentForm(FlaskForm):
    nouveau_referent = SelectField('Nouveau référent', coerce=int, validators=[DataRequired()])
    motif = StringField('Motif (optionnel)')
    submit = SubmitField('Changer')

#changement de mot de passe
class ChangePasswordForm(FlaskForm):
    ancien_password = PasswordField("Mot de passe actuel", validators=[DataRequired()])
    nouveau_password = PasswordField("Nouveau mot de passe", validators=[
        DataRequired(),
        Length(min=6, message="Le mot de passe doit contenir au moins 6 caractères")
    ])
    confirmer_password = PasswordField("Confirmer le nouveau mot de passe", validators=[
        DataRequired(),
        EqualTo('nouveau_password', message="Les mots de passe ne correspondent pas")
    ])
    submit = SubmitField("Modifier le mot de passe")

#envoi lien de réinitiliation
class RequestResetForm(FlaskForm):
    email = StringField("Email", validators=[DataRequired(), Email()])
    submit = SubmitField("Envoyer le lien de réinitialisation")

class ResetPasswordForm(FlaskForm):
    password = PasswordField(
        "Nouveau mot de passe",
        validators=[DataRequired(message="Champ requis"), Length(min=8, message="8 caractères minimum")]
    )
    confirm = PasswordField(
        "Confirmer le mot de passe",
        validators=[DataRequired(message="Champ requis"), EqualTo("password", message="Les mots de passe ne correspondent pas")]
    )
    submit = SubmitField("Réinitialiser")


class DummyForm(FlaskForm):
    pass  # uniquement utilisé pour CSRF dans le formulaire POST    

class DeleteForm(FlaskForm):
    submit = SubmitField("Supprimer")