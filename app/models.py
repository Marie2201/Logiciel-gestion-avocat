from sqlalchemy import Boolean
from datetime import datetime
from app import db
from werkzeug.security import generate_password_hash, check_password_hash
from flask_login import UserMixin

class Client(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    societe = db.Column(db.String(100))
    #prenom = db.Column(db.String(100))
    email = db.Column(db.String(120))
    telephone = db.Column(db.String(20))
    adresse = db.Column(db.String(255))
    dossiers = db.relationship('Dossier', backref='client', lazy=True)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'))
    user = db.relationship("User", backref="clients")
    supprimé = db.Column(db.Boolean, default=False) 
    

class Dossier(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    annee = db.Column(db.Integer, nullable=False) 
    sequence = db.Column(db.Integer, nullable=False)
    numero = db.Column(db.String(20), nullable=False, unique=True) 
    nom = db.Column(db.String(100), nullable=False)
    description = db.Column(db.Text, nullable=True)
    date_ouverture = db.Column(db.Date, nullable=False)
    procedures = db.Column(db.Text, nullable=True)
    statut = db.Column(db.String(50), nullable=False)
    supprimé = db.Column(db.Boolean, default=False)
    client_id = db.Column(db.Integer, db.ForeignKey('client.id'), nullable=False)
    timesheets = db.relationship("Timesheet", back_populates="dossier")
    factures = db.relationship('Facture', backref='dossier', lazy=True)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'))
    referent = db.relationship("User", backref="dossiers")
    #user = db.relationship('User', backref='dossiers_attribués')
    supprimé = db.Column(Boolean, default=False)


    __table_args__ = (
        db.UniqueConstraint('annee', 'sequence', name='uq_dossier_annee_sequence'),
    )
    def compute_numero(self):
        # "13.897/25" → points tous les 3 chiffres + "/YY"
        seq = f"{self.sequence:,}".replace(",", ".")   # groupement par milliers avec des points
        yy = str(self.annee % 100).zfill(2)
        return f"{seq}/{yy}"
    #client = db.relationship('Client', backref=db.backref('dossiers', lazy=True))

    # def __repr__(self):
    #     return f'<Dossier {self.id} - {self.nom}>'


class Timesheet(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    date = db.Column(db.Date, default=datetime.utcnow)
    supprimé = db.Column(Boolean, default=False)  # Pour garder l’historique intact
    
    heure_debut = db.Column(db.Time, nullable=False)
    heure_fin = db.Column(db.Time, nullable=False)
    duree_heures = db.Column(db.Float)  # à calculer automatiquement

    description = db.Column(db.Text)
    statut = db.Column(db.String(50))  # en cours, facturée...
    taux_horaire = db.Column(db.Float, nullable=True)
    devise = db.Column(db.String(3), default='XOF')
    tva_applicable = db.Column(db.Boolean, default=True)  # True = oui, False = non

    type_facturation = db.Column(db.String(10), nullable=False, default='horaire')  # 'horaire' | 'forfait'
    montant_forfait = db.Column(db.Numeric(10, 2), nullable=True)
    montant_ht = db.Column(db.Float)
    montant_ttc = db.Column(db.Float)

    dossier_id = db.Column(db.Integer, db.ForeignKey('dossier.id'), nullable=False)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=True)

    dossier = db.relationship("Dossier", back_populates="timesheets")
    user = db.relationship("User", backref="timesheets")

    facture_id = db.Column(db.Integer, db.ForeignKey('facture.id'), nullable=True)
    facture_id = db.Column(db.Integer, db.ForeignKey('facture.id', ondelete='CASCADE'))
    supprimé = db.Column(db.Boolean, default=False)


    def __repr__(self):
        return f'<Timesheet {self.id} - {self.date}>'

    # Méthode pour calculer la durée, HT, TTC
    def calculate_amounts(self, tva_rate=0.20): # Taux de TVA par défaut
        start_dt = datetime.combine(self.date, self.heure_debut)
        end_dt = datetime.combine(self.date, self.heure_fin)
        duration_timedelta = end_dt - start_dt

        # Stocker la durée comme un timedelta
        self.duree = duration_timedelta

        # Calculer les heures décimales
        total_seconds = duration_timedelta.total_seconds()
        hours_decimal = total_seconds / 3600

        self.montant_ht = hours_decimal * self.taux_horaire
        self.montant_ttc = self.montant_ht * (1 + tva_rate)
        # Assurez-vous que les montants sont stockés avec la bonne précision
        self.montant_ht = round(self.montant_ht, 2)
        self.montant_ttc = round(self.montant_ttc, 2)

class Facture(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    date = db.Column(db.Date)
    montant_ht = db.Column(db.Float)
    montant_ttc = db.Column(db.Float)
    statut = db.Column(db.String(50))
    devise = db.Column(db.String(8), nullable=True)
    dossier_id = db.Column(db.Integer, db.ForeignKey('dossier.id'), nullable=False)
    timesheets = db.relationship("Timesheet", backref="facture", cascade="all, delete", passive_deletes=True)
    supprimé = db.Column(db.Boolean, default=False)
    #dossier = db.relationship('Dossier', backref='factures')
    def __repr__(self):
        return f'<Facture {self.id} - {self.montant_ttc} {self.statut}>'

class User(UserMixin, db.Model): # <-- Héritez de UserMixin
    __tablename__ = 'users'
    id = db.Column(db.Integer, primary_key=True)
    nom = db.Column(db.String(100))
    role = db.Column(db.String(50))
    email = db.Column(db.String(120), unique=True, nullable=False)
    password_hash = db.Column(db.String(256), nullable=False)
    supprimé = db.Column(db.Boolean, default=False)
    


    def set_password(self, password):
        self.password_hash = generate_password_hash(password)

    def check_password(self, password):
        return check_password_hash(self.password_hash or '', password)

    # Ces méthodes sont requises par UserMixin
    def get_id(self):
        return str(self.id)

    def is_active(self):
        return True # L'utilisateur est actif, non bloqué

    def is_authenticated(self):
        return True # L'utilisateur est authentifié

    def is_anonymous(self):
        return False # L'utilisateur n'est pas anonyme (connecté)

    def __repr__(self):
        return f'<User {self.email}>'


#ajout de document
class Document(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    nom_fichier = db.Column(db.String(255), nullable=False)
    chemin = db.Column(db.String(255), nullable=False)
    dossier_id = db.Column(db.Integer, db.ForeignKey('dossier.id'), nullable=False)
    date_upload = db.Column(db.DateTime, default=datetime.utcnow)

    dossier = db.relationship('Dossier', backref=db.backref('documents', lazy=True))
    supprimé = db.Column(db.Boolean, default=False)




#changement d'attribution
class AttributionHistorique(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    dossier_id = db.Column(db.Integer, db.ForeignKey('dossier.id'), nullable=False)
    ancien_referent_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=True)
    nouveau_referent_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    date_attribution = db.Column(db.DateTime, default=datetime.utcnow)
    auteur_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    motif = db.Column(db.String(255), nullable=True)
    dossier = db.relationship('Dossier', backref='historique_attributions', lazy=True)
    ancien_referent = db.relationship('User', foreign_keys=[ancien_referent_id])
    nouveau_referent = db.relationship('User', foreign_keys=[nouveau_referent_id])
    auteur = db.relationship('User', foreign_keys=[auteur_id])


#ajout calendrier
class CalendarEvent(db.Model):
    __tablename__ = 'calendar_event'
    id        = db.Column(db.Integer, primary_key=True)
    title     = db.Column(db.String(255), nullable=False)
    start     = db.Column(db.DateTime, nullable=False)
    end       = db.Column(db.DateTime, nullable=True)
    user_id   = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    created_at= db.Column(db.DateTime, default=datetime.utcnow)
    description = db.Column(db.String(500), nullable=True)
    user = db.relationship('User', backref='calendar_events')

from app import app, db
with app.app_context():
    db.create_all()






