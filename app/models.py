from sqlalchemy import Boolean, JSON
from sqlalchemy.dialects.mysql import TINYINT
from flask_login import UserMixin
from werkzeug.security import generate_password_hash, check_password_hash
import datetime
from app import db

class Client(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    societe = db.Column(db.String(100))
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
    numero = db.Column(db.String(20), nullable=False)
    nom = db.Column(db.String(100), nullable=False)
    description = db.Column(db.Text, nullable=True)
    date_ouverture = db.Column(db.Date, nullable=False)
    procedures = db.Column(db.String(191), nullable=True)
    
    __table_args__ = (
        db.UniqueConstraint('client_id', 'numero', 'procedures',
                            name='uq_dossier_client_numero_procedure'),
        db.Index('ix_dossier_numero', 'numero'),
    )
    
    statut = db.Column(db.String(50), nullable=False)
    client_id = db.Column(db.Integer, db.ForeignKey('client.id'), nullable=False)
    timesheets = db.relationship("Timesheet", back_populates="dossier")
    factures = db.relationship('Facture', backref='dossier', lazy=True)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'))
    referent = db.relationship("User", backref="dossiers")
    supprimé = db.Column(db.Boolean, default=False)

    def compute_numero(self):
        seq = f"{self.sequence:,}".replace(",", ".")
        yy = str(self.annee % 100).zfill(2)
        return f"{seq}/{yy}"

class Timesheet(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    # Fix: use datetime.datetime.utcnow
    date = db.Column(db.Date, default=datetime.datetime.utcnow)
    heure_debut = db.Column(db.Time, nullable=False, default=datetime.time(0, 0, 0))
    heure_fin = db.Column(db.Time, nullable=False, default=datetime.time(0, 0, 0))
    duree_heures = db.Column(db.Float)
    description = db.Column(db.Text)
    statut = db.Column(db.String(50))
    taux_horaire = db.Column(db.Float, nullable=True)
    devise = db.Column(db.String(3), default='XOF')
    tva_applicable = db.Column(db.Boolean, default=True)
    type_facturation = db.Column(db.String(10), nullable=False, default='horaire')
    montant_forfait = db.Column(db.Numeric(10, 2), nullable=True)
    montant_ht = db.Column(db.Float)
    montant_ttc = db.Column(db.Float)
    dossier_id = db.Column(db.Integer, db.ForeignKey('dossier.id'), nullable=False)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=True)
    dossier = db.relationship("Dossier", back_populates="timesheets")
    user = db.relationship("User", backref="timesheets")
    facture_id = db.Column(db.Integer, db.ForeignKey('facture.id', ondelete='CASCADE'))
    supprimé = db.Column(db.Boolean, default=False)

    def calculate_amounts(self, tva_rate=0.20):
        # Fix: datetime.datetime.combine
        start_dt = datetime.datetime.combine(self.date, self.heure_debut)
        end_dt = datetime.datetime.combine(self.date, self.heure_fin)
        duration_timedelta = end_dt - start_dt
        self.duree = duration_timedelta
        total_seconds = duration_timedelta.total_seconds()
        hours_decimal = total_seconds / 3600
        self.montant_ht = round(hours_decimal * (self.taux_horaire or 0), 2)
        self.montant_ttc = round(self.montant_ht * (1 + tva_rate), 2)

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

class User(UserMixin, db.Model):
    __tablename__ = 'users'
    id = db.Column(db.Integer, primary_key=True)
    nom = db.Column(db.String(100))
    role = db.Column(db.String(50))
    email = db.Column(db.String(120), unique=True, nullable=False)
    password_hash = db.Column(db.String(256), nullable=False)
    supprimé = db.Column(db.Boolean, default=False)
    two_factor_enabled = db.Column(db.Boolean, nullable=False, default=False)
    two_factor_method = db.Column(db.String(20), default='email')
    two_factor_secret = db.Column(db.String(32), nullable=True)
    two_factor_backup = db.Column(db.Text, nullable=True)
    last_2fa_at = db.Column(db.DateTime, nullable=True)
    last_login_ip = db.Column(db.String(45))
    last_device_fp = db.Column(db.String(64))
    suspended = db.Column(db.Boolean, nullable=False, default=False, server_default=db.text('0'))

    def set_password(self, password):
        self.password_hash = generate_password_hash(password)

    def check_password(self, password):
        return check_password_hash(self.password_hash or '', password)

class Document(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    nom_fichier = db.Column(db.String(255), nullable=False)
    chemin = db.Column(db.String(255), nullable=False)
    dossier_id = db.Column(db.Integer, db.ForeignKey('dossier.id'), nullable=False)
    # Fix: use datetime.datetime.utcnow
    date_upload = db.Column(db.DateTime, default=datetime.datetime.utcnow)
    dossier = db.relationship('Dossier', backref=db.backref('documents', lazy=True))
    supprimé = db.Column(db.Boolean, default=False)

class AttributionHistorique(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    dossier_id = db.Column(db.Integer, db.ForeignKey('dossier.id'), nullable=False)
    ancien_referent_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=True)
    nouveau_referent_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    # Fix: use datetime.datetime.utcnow
    date_attribution = db.Column(db.DateTime, default=datetime.datetime.utcnow)
    auteur_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    motif = db.Column(db.String(255), nullable=True)
    dossier = db.relationship('Dossier', backref='historique_attributions', lazy=True)
    ancien_referent = db.relationship('User', foreign_keys=[ancien_referent_id])
    nouveau_referent = db.relationship('User', foreign_keys=[nouveau_referent_id])
    auteur = db.relationship('User', foreign_keys=[auteur_id])

class CalendarEvent(db.Model):
    __tablename__ = 'calendar_event'
    id = db.Column(db.Integer, primary_key=True)
    title = db.Column(db.String(255), nullable=False)
    start = db.Column(db.DateTime, nullable=False)
    end = db.Column(db.DateTime, nullable=True)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=True)
    # Fix: use datetime.datetime.utcnow
    created_at = db.Column(db.DateTime, default=datetime.datetime.utcnow)
    description = db.Column(db.String(500), nullable=True)
    user = db.relationship('User', backref='calendar_events')

class TrustedDevice(db.Model):
    __tablename__ = 'trusted_devices'
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'), index=True, nullable=False)
    device_token = db.Column(db.String(64), unique=True, nullable=False)
    # Fix: use datetime.datetime.utcnow
    created_at = db.Column(db.DateTime, default=datetime.datetime.utcnow, nullable=False)
    expires_at = db.Column(db.DateTime, nullable=False)
    user = db.relationship('User', backref='trusted_devices')
