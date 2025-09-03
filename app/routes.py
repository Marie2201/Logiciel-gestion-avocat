from flask import render_template, redirect, url_for, session, flash, request, jsonify, send_from_directory, abort, make_response, current_app
from app.forms import TimesheetForm, ClientForm, DossierForm, DeleteForm, FactureForm, AjoutUtilisateurForm, LoginForm, GenererFactureForm, DummyForm
from app.forms import DocumentForm, RegistrationForm, UserForm, AttributionForm, FlaskForm, ChangerReferentForm, ChangePasswordForm
from app.forms import RequestResetForm, ResetPasswordForm
from app.models import Timesheet, Dossier, Client, Facture, User, Document, AttributionHistorique, CalendarEvent
from app import app, db
from datetime import datetime, timedelta, date
from sqlalchemy.sql import func, case, cast
from werkzeug.security import generate_password_hash, check_password_hash
from flask_login import login_user, logout_user, login_required, current_user
from werkzeug.utils import secure_filename, send_file
import os
import traceback
from functools import wraps
from wtforms import SelectField
from sqlalchemy.orm import joinedload
from flask_mail import Message
from app import mail
import re
from sqlalchemy.exc import IntegrityError
from decimal import Decimal, ROUND_HALF_UP
from wtforms.validators import DataRequired, Optional, NumberRange
from app.utils import generate_reset_token, verify_reset_token, send_reset_email, make_reset_token, reset_url_for
from itsdangerous import URLSafeTimedSerializer, BadSignature, SignatureExpired
import time
from sqlalchemy import or_,  extract
from collections import defaultdict
from sqlalchemy import  Numeric
from .auth import get_client_ip, issue_email_otp, has_valid_trusted_device, set_trusted_cookie, device_fingerprint
from .models import TrustedDevice
import io, pyotp, qrcode

@app.context_processor
def inject_now():
    return {'current_year': datetime.now().year}
#from app import app
#from flask import render_template
def roles_required(*roles):
    def decorator(func):
        @wraps(func)
        def wrapper(*args, **kwargs):
            if not current_user.is_authenticated:
                abort(403)
            if current_user.role not in roles:
                abort(403)
            return func(*args, **kwargs)
        return wrapper
    return decorator

def has_role(*roles):
    return current_user.is_authenticated and getattr(current_user, 'role', None) in roles


@app.route('/')
@login_required
def index():
    # Si l'utilisateur est déjà connecté, redirigez-le vers le tableau de bord ou timesheets
    if current_user.is_authenticated:
        return redirect(url_for('dashboard')) # Ou 'dashboard' si c'est votre page principale

    # Sinon, redirigez vers la page de connexion
    return redirect(url_for('login')) # Assurez-vous que le nom de l'endpoint est 'login'

def get_factures_totaux_devises(base_query):
    # Normalisation large
    dev_raw = func.upper(func.trim(Facture.devise))
    dev_case = case(
        (dev_raw.in_(['XOF', 'FCFA', 'CFA', 'XAF']), 'XOF'),
        (dev_raw.in_(['EUR', 'EURO', 'EUROS']), 'EUR'),
        (dev_raw.in_(['USD', 'US$', '$', 'DOLLAR', 'DOLLARS']), 'USD'),
        else_='XOF'
    ).label('dev')

    # Cast en numérique au cas où la colonne ne serait pas DECIMAL
    montant = cast(Facture.montant_ttc, Numeric(18, 2))

    rows = (
        base_query
        .with_entities(dev_case, func.coalesce(func.sum(montant), 0.0))
        .group_by(dev_case)
        .all()
    )

    totaux = {'XOF': 0.0, 'EUR': 0.0, 'USD': 0.0}
    for dev, total in rows:
        totaux[dev] = float(total or 0)
    return totaux

@app.route('/dashboard')
@login_required
def dashboard():
    # rôles "global" (voient tout)
    admin_roles = ['admin','managing-partner','partner','managing-associate','comptabilité']
    is_admin = current_user.role in admin_roles

    # bases des requêtes
    q_clients   = Client.query.filter_by(supprimé=False)
    q_dossiers  = Dossier.query.filter_by(supprimé=False)
    q_factures  = Facture.query.filter_by(supprimé=False)
    q_timesheet = Timesheet.query.filter_by(supprimé=False)

    # restriction par utilisateur si non-admin
    if not is_admin:
        q_clients   = q_clients.filter(Client.user_id == current_user.id)
        q_dossiers  = q_dossiers.filter(Dossier.user_id == current_user.id)
        q_factures  = q_factures.join(Dossier, Facture.dossier_id == Dossier.id)\
                                .filter(Dossier.user_id == current_user.id)
        q_timesheet = q_timesheet.filter(Timesheet.user_id == current_user.id)

    # === KPIs pour ton template ===
    total_clients  = q_clients.count()

    # "Dossiers Actifs" = statut 'En cours'
    dossiers_actifs = q_dossiers.filter(Dossier.statut == 'En cours').count()

    # "Factures En Attente" = tout sauf payé (ajuste la liste si besoin)
    factures_en_attente = q_factures.filter(
        Facture.statut.in_(['Brouillon','En attente','Non payée','Partiellement payée','Impayée'])
    ).count()

    factures_totaux_devises = get_factures_totaux_devises(q_factures)
    # "Timesheets à facturer" = non rattachés à une facture
    timesheets_en_attente_facturation = q_timesheet.filter(
        Timesheet.facture_id.is_(None)
    ).count()

    # pour {{ moment(now) }} dans le template
    now = datetime.utcnow()

    return render_template(
        'dashboard.html',
        total_clients=total_clients,
        dossiers_actifs=dossiers_actifs,
        factures_en_attente=factures_en_attente,
        factures_totaux_devises=factures_totaux_devises,
        timesheets_en_attente_facturation=timesheets_en_attente_facturation,
        is_admin=is_admin,
        now=now
    )


#notifications mail
def envoyer_mail_attribution(user, dossier):
    if not user or not user.email:
        return

    # URL complète vers le dossier
    lien_dossier = url_for('dossiers', _external=True) + f"#dossier-{dossier.id}"

    msg = Message(
        subject="📌 Nouveau dossier attribué",
        recipients=[user.email],
        body=f"""Bonjour {user.nom},

Un nouveau dossier vous a été attribué :

- 📁 Nom du dossier : {dossier.nom}
- 🏢 Client : {dossier.client.societe}
- 📅 Date d'ouverture : {dossier.date_ouverture.strftime('%d/%m/%Y')}
- 🔗 Lien direct : {lien_dossier}

Merci de vous connecter à la plateforme pour consulter ce dossier.

Bien cordialement,
Le Cabinet
"""
    )

    try:
        mail.send(msg)
    except Exception as e:
        print(f"Erreur lors de l'envoi du mail : {e}")
        flash("Le mail n’a pas pu être envoyé, mais le dossier a bien été attribué.", "warning")



#ajout client
@app.route('/clients', methods=['GET', 'POST'])
@login_required
def clients():
    form = ClientForm()
    delete_form = DeleteForm()
    
    if form.validate_on_submit():
        client = Client(
            societe=form.societe.data,
            #prenom=form.prenom.data,
            email=form.email.data,
            telephone=form.telephone.data,
            adresse=form.adresse.data,
            user_id=current_user.id
        )
        db.session.add(client)
        db.session.commit()
        flash("Client ajouté avec succès.", "success")
        return redirect(url_for('clients'))

    clients = Client.query.filter_by(supprimé=False).all()
    if has_role('admin','managing-partner','partner','managing-associate','comptabilité','qualité','user-manager'):
        clients = Client.query.filter_by(supprimé=False).all()
    else:
        clients = Client.query.filter_by(supprimé=False, user_id=current_user.id).all()
    return render_template('clients.html', form=form, delete_form=delete_form, clients=clients)


#modifier un client
@app.route('/clients/modifier/<int:client_id>', methods=['GET', 'POST'])
@login_required
def modifier_client(client_id):
    client = Client.query.get_or_404(client_id)
    form = ClientForm(obj=client)

    if form.validate_on_submit():
        client.societe = form.societe.data
        #client.prenom = form.prenom.data
        client.email = form.email.data
        client.telephone = form.telephone.data
        client.adresse = form.adresse.data
        db.session.commit()
        flash('Client modifié avec succès.', 'success')
        return redirect(url_for('clients'))

    return render_template('modifier_client.html', form=form, client=client)

#supprimer un client
@app.route('/clients/supprimer/<int:client_id>', methods=['POST'])
@login_required
def supprimer_client(client_id):
    client = Client.query.get_or_404(client_id)
    client.supprimé = True
    db.session.commit()
    flash('Client supprimé avec succès.', 'warning')
    return redirect(url_for('clients'))

NUMERO_RE = re.compile(r'^(\d{1,3}(?:\.\d{3})*)/(\d{2})$')

def parse_numero_to_components(numero: str):
    m = NUMERO_RE.match(numero)
    if not m:
        raise ValueError("Format invalide")
    seq_str, yy = m.groups()
    sequence = int(seq_str.replace('.', ''))
    annee = 2000 + int(yy)  # "25" -> 2025
    return annee, sequence

def compute_numero(sequence: int, annee: int) -> str:
    """
    (sequence=13897, annee=2025) -> '13.897/25'
    """
    seq_str = f"{sequence:,}".replace(",", ".")
    yy = str(annee % 100).zfill(2)
    return f"{seq_str}/{yy}"

#ajout dossiers
ADMIN_ROLES = {"admin", "managing-partner", "partner", "managing-associate", "comptabilité", "qualité","user-manager"}
@app.route('/dossiers', methods=['GET', 'POST'])
@login_required
def dossiers():
    form = DossierForm()
    delete_form = DeleteForm()
    changer_form = ChangerReferentForm()

    # ——— Select2 AJAX : forcer les attributs côté serveur ———
    form.client_id.render_kw = {**(form.client_id.render_kw or {}),  # /api/clients
        'class': 'form-select select2-ajax',
        'data-ajax_url': url_for('api_clients'),
        'data-placeholder': 'Rechercher un client…'
    }

    # Utilisateurs (liste locale classique)
    utilisateurs_possibles = User.query.filter(
        User.supprimé == False,
        User.role.in_([
            'admin','managing-partner','partner','managing-associate',
            'juriste','avocat','comptabilité','qualité','clerc','secrétaire','user-manager'
        ])
    ).order_by(User.nom).all()
    form.user_id.choices = [(u.id, u.nom) for u in utilisateurs_possibles]
    changer_form.nouveau_referent.choices = [(u.id, u.nom) for u in utilisateurs_possibles]

    # Select2 AJAX: ne pas précharger 10k+ clients, juste l’option sélectionnée si besoin
    if form.client_id.data:
        c = Client.query.get(form.client_id.data)
        form.client_id.choices = [(c.id, c.societe)] if c and not getattr(c, 'supprimé', False) else []
    else:
        form.client_id.choices = []

    # Pré-remplir référent à l’ouverture
    if request.method == "GET" and not form.user_id.data:
        form.user_id.data = current_user.id

    # --- Création d'un dossier ---
    if form.validate_on_submit():
        try:
            user_id = form.user_id.data or current_user.id
            numero_input = (form.numero.data or "").strip() if hasattr(form, "numero") else ""

            if numero_input:
                annee, sequence = parse_numero_to_components(numero_input)
                numero_norm = compute_numero(sequence, annee)

                nouveau_dossier = Dossier(
                    nom=form.nom.data,
                    description=form.description.data,
                    date_ouverture=form.date_ouverture.data,
                    procedures=(form.procedures.data or "").strip() or None,
                    statut=form.statut.data,
                    client_id=form.client_id.data,
                    user_id=user_id,
                    annee=annee, sequence=sequence, numero=numero_norm
                )
                db.session.add(nouveau_dossier)
                db.session.flush()

                hist = AttributionHistorique(
                    dossier_id=nouveau_dossier.id,
                    ancien_referent_id=None,
                    nouveau_referent_id=user_id,
                    auteur_id=current_user.id,
                    date_attribution=datetime.utcnow(),
                    motif="Attribution initiale"
                )
                db.session.add(hist)

                try:
                    db.session.commit()
                    flash("✅ Dossier ajouté avec succès.", "success")
                    return redirect(url_for('dossiers'))
                except IntegrityError as e:
                    db.session.rollback()
                    # ⬇️  RESTE DANS LE except + RETOURNE LE TEMPLATE
                    if "uq_dossier_client_numero_procedures" in str(getattr(e, "orig", e)):
                        form.numero.errors.append("Ce numéro existe déjà pour ce client et cette procédure.")
                    else:
                        current_app.logger.exception("Erreur lors de l'ajout du dossier")
                        flash("Erreur lors de l'ajout du dossier.", "danger")
                    # Revenir au template avec erreurs => la modale se rouvre (voir script dans le template)
                    return render_template(
                        "dossiers.html",
                        form=form,
                        delete_form=delete_form,
                        dossiers=Dossier.query.filter_by(supprimé=False).order_by(Dossier.id.desc()).all(),
                        clients=[],
                        users=utilisateurs_possibles,
                        changer_form=changer_form,
                        AttributionHistorique=AttributionHistorique,
                        hist_map=defaultdict(list)
                    ), 400

            else:
                # ... (ta génération auto inchangée)
                # si ça échoue 5 fois :
                flash("❌ Impossible de générer un numéro unique. Réessayez.", "danger")

        except ValueError as ve:
            db.session.rollback()
            flash(f"❌ {str(ve)}", "danger")
        except Exception:
            db.session.rollback()
            current_app.logger.exception("Erreur lors de l'ajout du dossier")
            flash("❌ Une erreur s’est produite lors de l’ajout du dossier.", "danger")
    else:
        if request.method == "POST":
            current_app.logger.info(f"⚠️ Erreurs formulaire : {form.errors}")

    # --- Liste des dossiers (droits/filtre) ---
    client_id = request.args.get('client_id', type=int)
    query = Dossier.query.filter_by(supprimé=False)
    if current_user.role not in ['admin','managing-partner','partner','managing-associate','comptabilité','qualité', 'user-manager']:
        query = query.filter_by(user_id=current_user.id)
    if client_id:
        query = query.filter_by(client_id=client_id)
    dossiers_list = query.order_by(Dossier.id.desc()).all()

    # ---- Charger les historiques (APRES avoir la liste) ----
    hist_map = defaultdict(list)
    if dossiers_list:
        dossier_ids = [d.id for d in dossiers_list]
        rows = (AttributionHistorique.query
                .filter(AttributionHistorique.dossier_id.in_(dossier_ids))
                .order_by(AttributionHistorique.date_attribution.desc())
                .all())
        for h in rows:
            hist_map[h.dossier_id].append(h)

    return render_template(
        'dossiers.html',
        form=form,
        delete_form=delete_form,
        dossiers=dossiers_list,
        clients=[],  # on ne pousse plus la liste complète
        users=utilisateurs_possibles,
        changer_form=changer_form,
        AttributionHistorique=AttributionHistorique,
        hist_map=hist_map
    )



#modifier dossier
@app.route('/dossiers/modifier/<int:dossier_id>', methods=['GET', 'POST'])
@login_required
def modifier_dossier(dossier_id):
    dossier = Dossier.query.get_or_404(dossier_id)
    form = DossierForm(obj=dossier)

    form.client_id.choices = [(c.id, f"{c.societe}") for c in Client.query.filter_by(supprimé=False).all()]
    form.user_id.choices = [(u.id, u.nom) for u in User.query.filter(
        User.role.in_(['admin','managing-partner','partner','managing-associate',
                       'juriste','avocat','comptabilité','qualité','clerc','secrétaire', 'user-manager']),
        User.supprimé == False
    ).all()]

    if form.validate_on_submit():
        try:
            ancien_user_id = dossier.user_id
            nouveau_user_id = form.user_id.data

            # champs habituels
            dossier.nom = form.nom.data
            dossier.description = form.description.data
            dossier.date_ouverture = form.date_ouverture.data
            dossier.procedures = (form.procedures.data or "").strip() or None
            dossier.statut = form.statut.data
            dossier.client_id = form.client_id.data
            dossier.user_id = nouveau_user_id

            # ➜ Historiser si le référent change
            if ancien_user_id != nouveau_user_id:
                hist = AttributionHistorique(
                    dossier_id=dossier.id,
                    ancien_referent_id=ancien_user_id,
                    nouveau_referent_id=nouveau_user_id,
                    auteur_id=current_user.id,               # ✅ bon nom de colonne
                    date_attribution=datetime.utcnow(),       # ✅ timestamp
                    motif="Changement de référent"
                )
                db.session.add(hist)

            db.session.commit()

            # (optionnel) notifier le nouveau référent
            if ancien_user_id != nouveau_user_id:
                nouveau_referent = User.query.get(nouveau_user_id)
                if nouveau_referent:
                    envoyer_mail_attribution(nouveau_referent, dossier)

            flash("Dossier modifié avec succès.", "success")
            return redirect(url_for('dossiers'))

        except Exception:
            db.session.rollback()
            current_app.logger.exception("Erreur modification dossier")
            flash("❌ Erreur lors de la modification.", "danger")

    return render_template('modifier_dossier.html', form=form, dossier=dossier)


    # delete_form = DeleteForm()  # formulaire WTForm minimal
    # return render_template('dossiers.html', form=form, delete_form=delete_form, dossiers=dossiers_list)


#supprimer dossier
@app.route('/dossiers/supprimer/<int:dossier_id>', methods=['POST'])
@login_required
def supprimer_dossier(dossier_id):
    dossier = Dossier.query.get_or_404(dossier_id)
    dossier.supprimé = True
    db.session.commit()
    flash("Dossier supprimé avec succès.", "warning")
    return redirect(url_for('dossiers'))


#ajout facture
@app.route('/factures', methods=['GET', 'POST'])
@login_required
def factures():
    add_form = FactureForm()
    delete_form = DeleteForm()

    if has_role('admin','managing-partner','partner','managing-associate','comptabilité', 'user-manager'):
        factures = Facture.query.filter_by(supprimé=False).all()
    else:
        # dossiers de l'utilisateur
        dossiers_utilisateur = Dossier.query.filter_by(user_id=current_user.id).all()
        dossier_ids = [d.id for d in dossiers_utilisateur]
        factures = Facture.query.filter(
            Facture.supprimé == False,
            Facture.dossier_id.in_(dossier_ids)
        ).all()

    facture_data = []
    for f in factures:
        dossier = f.dossier
        client = dossier.client if dossier else None

        # Devise prioritaire: celle stockée sur la facture
        devise = (f.devise or '').strip() or None
        if not devise:
            # Déduire depuis un timesheet lié si possible
            ts = Timesheet.query.filter_by(facture_id=f.id).first()
            devise = (ts.devise if ts and ts.devise else 'XOF')

        facture_data.append({
            'id': f.id,
            'date': f.date,
            'montant_ht': f.montant_ht,
            'montant_ttc': f.montant_ttc,
            'devise': devise,  # ← NEW
            'statut': f.statut,
            'dossier_nom': dossier.nom if dossier else '',
            'client_nom': client.societe if client else ''
        })

    return render_template('factures.html', factures=facture_data, add_form=add_form, delete_form=delete_form)



# --- Nouvelle Route pour la Modification d'une Facture ---
@app.route('/factures/modifier/<int:facture_id>', methods=['GET', 'POST'])
@login_required
def modifier_facture(facture_id):
    facture = Facture.query.get_or_404(facture_id)
    form = FactureForm(obj=facture)

    # CHARGER LES CHOICES DU SELECT « dossier » À CHAQUE REQUÊTE
    dossiers = (Dossier.query
            .filter_by(supprimé=False)
            .order_by(
                (Dossier.numero == None),  # ORDER BY dossier.numero IS NULL (0 avant 1)
                Dossier.numero,
                Dossier.id
            )
            .all())
    form.dossier.choices = [(d.id, f"{d.numero or d.id} – {d.nom}") for d in dossiers]

    # Pré-sélectionner la valeur actuelle du dossier
    if request.method == 'GET':
        form.dossier.data = facture.dossier_id

    if form.validate_on_submit():
        try:
            facture.date = form.date.data
            facture.dossier_id = form.dossier.data            # <- corrige ici
            facture.montant_ht = Decimal(str(form.montant_ht.data or 0))
            facture.tva_applicable = bool(form.tva_applicable.data)
            facture.montant_ttc = Decimal(str(form.montant_ttc.data or 0))

            # normaliser la devise
            devise = (form.devise.data or 'XOF').strip().upper()
            if devise in ('FCFA', 'CFA'): 
                devise = 'XOF'
            facture.devise = devise

            facture.statut = form.statut.data

            db.session.commit()
            flash("✅ Facture mise à jour.", "success")
            return redirect(url_for('factures'))
        except Exception:
            db.session.rollback()
            current_app.logger.exception("Erreur maj facture")
            flash("❌ Erreur lors de la mise à jour de la facture.", "danger")
    else:
        if request.method == 'POST':
            # Log + feedback si le formulaire n’est pas valide
            current_app.logger.warning(f"Erreurs formulaire (edit facture): {form.errors}")
            flash("Le formulaire contient des erreurs. Merci de corriger.", "warning")

    return render_template('modifier_facture.html', form=form, facture=facture)
 # Crée un template modifier_facture.html

# --- Nouvelle Route pour la Suppression d'une Facture ---
@app.route('/supprimer_facture/<int:id>', methods=['POST'])
@login_required
def supprimer_facture(id):
    facture = Facture.query.get_or_404(id)
    db.session.delete(facture)
    db.session.commit()
    flash("La facture a été supprimée avec succès.", "success")
    return redirect(url_for('factures'))





import sys

def _to_decimal(x):
    return Decimal(str(x)).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)

def _calc_ttc(montant_ht, tva_applicable):
    if tva_applicable == 'oui':
        # adapte le taux (ex 18% ci-dessous)
        return (montant_ht * Decimal('1.18')).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
    return montant_ht

# ----------------------------
# LISTE + CREATION TIMESHEETS
# ----------------------------
@app.route('/timesheets', methods=['GET', 'POST'])
@login_required
def timesheets():
    form = TimesheetForm()

    # ——— Select2 AJAX : forcer les attributs côté serveur ———
    form.dossier_id.render_kw = {**(form.dossier_id.render_kw or {}),
        'class': 'form-select select2-ajax',
        'data-ajax_url': url_for('api_dossiers'),
        'data-placeholder': 'Rechercher un dossier…'
    }

    # NE PAS précharger tous les dossiers
    if form.dossier_id.data:
        d = Dossier.query.get(form.dossier_id.data)
        if d and not getattr(d, 'supprimé', False) and d.client and not getattr(d.client, 'supprimé', False):
            form.dossier_id.choices = [(d.id, f"{d.client.societe} - {d.nom}")]
        else:
            form.dossier_id.choices = []
    else:
        form.dossier_id.choices = []

    if form.validate_on_submit():
        tva_bool = (form.tva_applicable.data == 'oui')
        tva_rate = 0.18

        if form.type_facturation.data == 'horaire':
            dt_debut = datetime.combine(form.date.data, form.heure_debut.data)
            dt_fin   = datetime.combine(form.date.data, form.heure_fin.data)
            if dt_fin < dt_debut:
                dt_fin += timedelta(days=1)
            duree_h = round((dt_fin - dt_debut).total_seconds() / 3600.0, 2)

            ht  = round(duree_h * float(form.taux_horaire.data), 2)
            ttc = round(ht * (1 + tva_rate), 2) if tva_bool else ht

            ts = Timesheet(
                date=form.date.data,
                type_facturation='horaire',
                heure_debut=form.heure_debut.data,
                heure_fin=form.heure_fin.data,
                duree_heures=duree_h,
                taux_horaire=form.taux_horaire.data,
                montant_forfait=None,
                tva_applicable=tva_bool,
                montant_ht=ht,
                montant_ttc=ttc,
                statut=form.statut.data,
                devise=(form.devise.data or "XOF").upper(),
                description=form.description.data or '',
                dossier_id=form.dossier_id.data,
                user_id=current_user.id
            )
        else:
            ht  = round(float(form.montant_forfait.data), 2)
            ttc = round(ht * (1 + tva_rate), 2) if tva_bool else ht

            ts = Timesheet(
                date=form.date.data,
                type_facturation='forfait',
                heure_debut=time(0,0,0),
                heure_fin=time(0,0,0),
                duree_heures=0,
                taux_horaire=None,
                montant_forfait=form.montant_forfait.data,
                tva_applicable=tva_bool,
                montant_ht=ht,
                montant_ttc=ttc,
                statut=form.statut.data,
                devise=(form.devise.data or "XOF").upper(),
                description=form.description.data or '',
                dossier_id=form.dossier_id.data,
                user_id=current_user.id
            )

        db.session.add(ts)
        db.session.commit()
        flash("Timesheet enregistré avec succès.", "success")
        return redirect(url_for('timesheets'))
    
    if form.errors:
        current_app.logger.info(form.errors)

    client_id = request.args.get('client_id', type=int)

    q = (Timesheet.query
         .options(
             joinedload(Timesheet.dossier).joinedload(Dossier.client),
             joinedload(Timesheet.user))
         .filter(Timesheet.supprimé == False))

    if not has_role('admin','managing-partner','partner','managing-associate','comptabilité','qualité','user-manager'):
        q = q.filter(Timesheet.user_id == current_user.id)

    if client_id:
        q = (q.join(Timesheet.dossier)
               .join(Dossier.client)
               .filter(Client.id == client_id))

    timesheets_list = q.order_by(Timesheet.date.desc(), Timesheet.id.desc()).all()
    # Affichage filtré selon rôle
    # if current_user.role in ['admin', 'managing-partner', 'partner', 'managing-associate', 'comptabilité', 'qualité']:
    #     timesheets_list = Timesheet.query.filter_by(supprimé=False)\
    #                          .order_by(Timesheet.date.desc(), Timesheet.id.desc()).all()
    # else:
    #     timesheets_list = Timesheet.query.filter_by(user_id=current_user.id, supprimé=False)\
    #                          .order_by(Timesheet.date.desc(), Timesheet.id.desc()).all()

    return render_template("timesheets.html", form=form, timesheets=timesheets_list, 
                           delete_form=DeleteForm(),
                           selected_client_id=client_id)

#timesheet par client
@app.route('/timesheets/clients', methods=['GET'])
@login_required
def timesheets_par_client():
    # Base query avec jointures
    q = (db.session.query(
            Client.id.label('client_id'),
            Client.societe.label('client'),
            func.count(Timesheet.id).label('nb_ts'),
            func.coalesce(func.sum(Timesheet.duree_heures), 0).label('heures_total'),
            func.coalesce(func.sum(Timesheet.montant_ht), 0).label('ht_total'),
            func.coalesce(func.sum(Timesheet.montant_ttc), 0).label('ttc_total'))
         .join(Dossier, Dossier.client_id == Client.id)
         .join(Timesheet, Timesheet.dossier_id == Dossier.id)
         .filter(Timesheet.supprimé == False))

    # Rôles
    if not has_role('admin','managing-partner','partner','managing-associate','comptabilité','qualité','user-manager'):
        q = q.filter(Timesheet.user_id == current_user.id)

    # Évite d’afficher les clients/dossiers supprimés si tu as la colonne
    if hasattr(Client, 'supprimé'):
        q = q.filter(Client.supprimé == False)
    if hasattr(Dossier, 'supprimé'):
        q = q.filter(Dossier.supprimé == False)

    rows = (q.group_by(Client.id, Client.societe)
              .order_by(Client.societe.asc())
              .all())

    return render_template("timesheets_par_client.html", rows=rows)


# ----------------------------
# EDITION TIMESHEET
# ----------------------------
@app.route('/edit_timesheet/<int:id>', methods=['GET', 'POST'])
@login_required
def edit_timesheet(id):
    timesheet = Timesheet.query.get_or_404(id)
    form = TimesheetForm(obj=timesheet)

    # Choix dossiers
    form.dossier_id.choices = [
        (d.id, f"{d.client.societe} - {d.nom}")
        for d in Dossier.query.join(Client)
              .filter(Dossier.supprimé == False, Client.supprimé == False)
              .order_by(Client.societe, Dossier.nom)
              .all()
    ]

    # Pré-remplissages/normalisations GET
    if request.method == 'GET':
        form.tva_applicable.data = 'oui' if timesheet.tva_applicable else 'non'
        form.type_facturation.data = timesheet.type_facturation or 'horaire'
        form.devise.data = (timesheet.devise or "XOF").upper()
        if not timesheet.statut:
            form.statut.data = 'En cours'  # garde-fou
        if timesheet.type_facturation == 'forfait':
            form.montant_forfait.data = timesheet.montant_forfait

    if form.validate_on_submit():
        tva_rate = 0.18
        devise = (form.devise.data or "XOF").upper()
        tva_bool = (form.tva_applicable.data in ("oui", "1", True, "True"))
        type_fact = form.type_facturation.data or 'horaire'

        timesheet.date = form.date.data
        timesheet.description = form.description.data
        timesheet.statut = form.statut.data
        timesheet.devise = devise
        timesheet.dossier_id = form.dossier_id.data
        timesheet.tva_applicable = tva_bool

        if type_fact == 'forfait':
            timesheet.type_facturation = 'forfait'
            timesheet.montant_forfait = float(form.montant_forfait.data or 0)
            timesheet.heure_debut = time(0, 0, 0)
            timesheet.heure_fin   = time(0, 0, 0)
            timesheet.duree_heures = 0 
            timesheet.taux_horaire = None
            timesheet.montant_ht = round(timesheet.montant_forfait, 2)
            timesheet.montant_ttc = round(timesheet.montant_ht * (1 + tva_rate), 2) if tva_bool else timesheet.montant_ht

        else:
            timesheet.type_facturation = 'horaire'
            timesheet.heure_debut = form.heure_debut.data
            timesheet.heure_fin = form.heure_fin.data
            dt_debut = datetime.combine(form.date.data, form.heure_debut.data)
            dt_fin = datetime.combine(form.date.data, form.heure_fin.data)
            if dt_fin < dt_debut:
                dt_fin += timedelta(days=1)  # ✅ passage minuit aussi en édition
            timesheet.duree_heures = round((dt_fin - dt_debut).total_seconds() / 3600, 2)
            timesheet.taux_horaire = float(form.taux_horaire.data or 0)
            timesheet.montant_ht = round(timesheet.duree_heures * timesheet.taux_horaire, 2)
            timesheet.montant_ttc = round(timesheet.montant_ht * (1 + tva_rate), 2) if tva_bool else timesheet.montant_ht

        db.session.commit()
        flash("Timesheet modifié avec succès ✅", "success")
        return redirect(url_for('timesheets'))

    return render_template('edit_timesheet.html', form=form, timesheet=timesheet)
#supprimer un timesheet
@app.route('/timesheet/delete/<int:id>', methods=['POST'])
@login_required
def delete_timesheet(id):
    ts = Timesheet.query.get_or_404(id)
    ts.supprimé = True  # Ne pas supprimer réellement
    db.session.commit()
    flash("Timesheet archivé avec succès.", "warning")
    return redirect(url_for('timesheets'))



# @app.route('/login', methods=['GET', 'POST'])
# def login():
#     form = LoginForm()
#     if form.validate_on_submit():
#         user = User.query.filter_by(email=form.email.data.lower()).first()
#         print("USER TROUVÉ :", user) 
#         if user and check_password_hash(user.password_hash, form.password.data):  # ou form.mot_de_passe.data
#             login_user(user, remember=form.remember_me.data)
#             flash('Connexion réussie', 'success')
#             return redirect(url_for('dashboard'))  # ou une autre route après login
#         else:
#             flash('Identifiants incorrects', 'danger')
#     return render_template('login.html', form=form)

# Vous aurez aussi besoin de routes pour 'forgot_password' et 'register' si vous incluez les liens.
# @app.route('/forgot_password')
# def forgot_password():
#     flash("La page de réinitialisation de mot de passe n'est pas encore implémentée.", "info")
#     return redirect(url_for('login')) # Redirige vers la page de connexion pour l'instant

@app.route('/register', methods=['GET', 'POST'])
@login_required
def register():
    if not has_role('admin','managing-partner','partner','managing-associate','comptabilité','user-manager'):
        flash("⛔ Accès non autorisé.", "danger")
        return redirect(url_for('dashboard'))
    form = RegistrationForm()
    if form.validate_on_submit():
        if User.query.filter_by(email=form.email.data).first():
            flash('🚫 Un utilisateur avec cet email existe déjà.', 'danger')
            return redirect(url_for('register'))
        
        user = User(
            nom=form.nom.data,
            email=form.email.data,
            role=form.role.data
        )
        user.set_password(form.password.data)
        db.session.add(user)
        db.session.commit()
        flash('✅ Utilisateur créé avec succès.', 'success')
        return redirect(url_for('login'))  # ou tableau de bord
    return render_template('register.html', form=form) # Redirige vers la page de connexion pour l'instant


@app.route('/logout')
@login_required
def logout():
    logout_user()
    flash("Déconnexion réussie", "success")
    return redirect(url_for('login'))

#ajout utilisateur
@app.route('/ajouter_utilisateur', methods=['GET', 'POST'])
@login_required
def ajouter_utilisateur():
    if not has_role('admin','managing-partner','partner','managing-associate','comptabilité','user-manager'):
        flash("Vous n'avez pas l'autorisation d'accéder à cette page.", "danger")
        return redirect(url_for('index'))

    form = AjoutUtilisateurForm()
    if form.validate_on_submit():
        nouvel_utilisateur = User(
            nom=form.nom.data,
            email=form.email.data,
            role=form.role.data,
            password_hash=generate_password_hash(form.password.data),
            supprimé=False
        )
        db.session.add(nouvel_utilisateur)
        db.session.commit()
        flash("Utilisateur ajouté avec succès ✅", "success")
        return redirect(url_for('utilisateurs'))  # Page liste des utilisateurs
    return render_template('ajouter_utilisateur.html', form=form)


@app.route('/generer_facture', methods=['GET', 'POST'])
@login_required
def generer_facture():
    form = DummyForm()

    # POST : Générer une facture
    if request.method == 'POST':
        selected_ids = request.form.getlist('timesheet_ids')
        if not selected_ids:
            flash("Veuillez sélectionner au moins un timesheet.", "warning")
            return redirect(url_for('generer_facture'))

        # Récupération des timesheets sélectionnés
        timesheets = Timesheet.query.filter(Timesheet.id.in_(selected_ids)).all()
        if not timesheets:
            flash("Aucun timesheet valide sélectionné.", "danger")
            return redirect(url_for('generer_facture'))

        # Vérification d'unicité du dossier
        dossiers = {ts.dossier_id for ts in timesheets}
        if len(dossiers) != 1:
            flash("Les timesheets doivent appartenir au même dossier pour générer une facture.", "danger")
            return redirect(url_for('generer_facture'))

        # Vérification d'unicité de la devise (ex: 'XOF', 'EUR', 'USD' ...)
        devises = { (ts.devise or 'XOF') for ts in timesheets }
        if len(devises) != 1:
            msg = "Les timesheets sélectionnés doivent être dans la même devise (trouvées : "
            msg += ", ".join(sorted(devises)) + ")."
            flash(msg, "danger")
            return redirect(url_for('generer_facture'))
        devise_commune = devises.pop()

        # Sommes brutes, SANS conversion
        montant_ht_total = sum(ts.montant_ht for ts in timesheets)
        montant_ttc_total = sum(ts.montant_ttc for ts in timesheets)
        dossier_id = timesheets[0].dossier_id

        # ⚠️ Assure-toi que Facture a bien un champ 'devise' (String).
        facture = Facture(
            date=datetime.utcnow().date(),
            montant_ht=montant_ht_total,
            montant_ttc=montant_ttc_total,
            statut="En attente",
            dossier_id=dossier_id,
            devise=devise_commune  # <— on garde la devise telle quelle
        )
        db.session.add(facture)
        db.session.commit()

        # Associer les timesheets à la facture
        for ts in timesheets:
            ts.facture = facture
        db.session.commit()

        flash(f"Facture générée avec succès pour {len(timesheets)} timesheet(s).", "success")
        return redirect(url_for('factures'))

    # GET : Affichage avec filtres (aucune conversion ici)
    utilisateur_id = request.args.get('utilisateur_id', type=int)
    date_debut = request.args.get('date_debut')
    date_fin = request.args.get('date_fin')

    query = Timesheet.query.join(Dossier).filter(Timesheet.facture == None)

    # Seuls les associés/admins peuvent filtrer par utilisateur
    if not has_role('admin','managing-partner','partner','managing-associate','comptabilité','user-manager'):
        query = query.filter(Timesheet.user_id == current_user.id)
    elif utilisateur_id:
        query = query.filter(Timesheet.user_id == utilisateur_id)

    # Filtrage par dates
    if date_debut:
        query = query.filter(Timesheet.date >= date_debut)
    if date_fin:
        query = query.filter(Timesheet.date <= date_fin)

    timesheets = query.order_by(Timesheet.date).all()
    utilisateurs = User.query.all() if has_role('admin','managing-partner','partner','managing-associate','comptabilité','qualité','user-manager') else []

    return render_template(
        'generer_facture.html',
        timesheets=timesheets,
        utilisateurs=utilisateurs,
        form=form
    )


#récupérer dossier et mettre dans client
@app.route('/client/<int:id>')
def get_client(id):
    client = Client.query.get_or_404(id)
    dossiers = Dossier.query.filter_by(client_id=id).all()
    return jsonify({
        'id': client.id,
        'societe': client.societe,
        'email': client.email,
        'telephone': client.telephone,
        'adresse': client.adresse,
        'dossiers': [{'id': d.id, 'nom': d.nom, 'statut': d.statut} for d in dossiers]
    })


#pour ouvrir un document
UPLOAD_FOLDER = os.path.join(app.root_path, 'uploads')
os.makedirs(UPLOAD_FOLDER, exist_ok=True)
app.config['UPLOAD_FOLDER'] = UPLOAD_FOLDER

@app.route('/documents', methods=['GET', 'POST'])
@login_required
def documents():
    form = DocumentForm()
    form.dossier_id.choices = [
    (d.id, f"{d.nom} - {d.client.societe}") for d in Dossier.query
    .filter_by(supprimé=False)
    .join(Client)
    .order_by(Client.societe.asc(), Dossier.nom.asc())
    .all()]

    
    if form.validate_on_submit():
        try:
            fichier = request.files['fichier']
            if fichier.filename != '':
                nom_fichier = secure_filename(fichier.filename)
                chemin_complet = os.path.join(app.config['UPLOAD_FOLDER'], nom_fichier)
                fichier.save(chemin_complet)

                document = Document(
                    nom_fichier=fichier.filename,
                    chemin=nom_fichier,
                    dossier_id=form.dossier_id.data
                )
                db.session.add(document)
                db.session.commit()
                flash("Document ajouté avec succès.", "success")
                return redirect(url_for('documents'))
            else:
                flash("Aucun fichier sélectionné.", "warning")
        except Exception as e:
            db.session.rollback()
            print("❌ ERREUR DOCUMENT :", e)
            flash("Une erreur est survenue lors de l'ajout du document.", "danger")
    
    documents = Document.query.order_by(Document.date_upload.desc()).all()
    delete_form = DeleteForm()
    return render_template('documents.html', form=form, documents=documents, delete_form=delete_form)


#pour télécharger un document
@app.route('/documents/ouvrir/<int:document_id>')
@login_required
def ouvrir_document(document_id):
    document = Document.query.get_or_404(document_id)
    return send_from_directory(
        app.config['UPLOAD_FOLDER'],
        document.chemin,
        as_attachment=False  # Important : pas de téléchargement forcé
    )


@app.route('/dossier/<int:id>')
@login_required
def get_dossier(id):
    dossier = Dossier.query.get_or_404(id)
    documents = [
        {
            'id': doc.id,
            'nom_fichier': doc.nom_fichier,
            'url': url_for('ouvrir_document', document_id=doc.id)
        }
        for doc in dossier.documents
    ]
    return jsonify({
        'id': dossier.id,
        'nom': dossier.nom,
        'description': dossier.description,
        'statut': dossier.statut,
        'documents': documents
    })


#suppression d'un document
@app.route('/documents/supprimer/<int:id>', methods=['POST'])
@login_required
def supprimer_document(id):
    document = Document.query.get_or_404(id)
    try:
        db.session.delete(document)
        db.session.commit()
        flash("Document supprimé avec succès.", "success")
    except Exception as e:
        db.session.rollback()
        flash("Erreur lors de la suppression du document.", "danger")
    return redirect(url_for('documents'))


#ajout utilisateurs
@app.route('/utilisateurs')
@login_required
def utilisateurs():
    print(current_user)
    if not has_role('admin','managing-partner','partner','managing-associate','comptabilité','qualité','user-manager'):
        flash("Accès refusé. Page réservée aux administrateurs.", "danger")
        return redirect(url_for('index'))

    users = User.query.all()
    print("Utilisateurs récupérés :", [u.email for u in users])  # 👈 pour débug

    return render_template('utilisateurs.html', users=users)


@app.route('/utilisateur/modifier/<int:id>', methods=['GET', 'POST'])
@login_required
def modifier_utilisateur(id):
    if not has_role('admin','managing-partner','partner','managing-associate','comptabilité','qualité','user-manager'):
        flash("Accès refusé.", "danger")
        return redirect(url_for('dashboard'))

    utilisateur = User.query.get_or_404(id)
    form = UserForm(obj=utilisateur)

    if form.validate_on_submit():
        utilisateur.nom = form.nom.data
        utilisateur.email = form.email.data
        utilisateur.role = form.role.data
        db.session.commit()
        flash('Utilisateur modifié avec succès.', 'success')
        return redirect(url_for('utilisateurs'))

    return render_template('modifier_utilisateur.html', form=form)

@app.route('/utilisateur/supprimer/<int:id>', methods=['POST', 'GET'])
@login_required
def supprimer_utilisateur(id):
    if not has_role('admin','managing-partner','partner','managing-associate','comptabilité','user-manager'):
        flash("Accès refusé.", "danger")
        return redirect(url_for('dashboard'))

    utilisateur = User.query.get_or_404(id)

    # 🔥 Supprimer ses événements
    from app.models import CalendarEvent
    CalendarEvent.query.filter_by(user_id=utilisateur.id).delete()

    db.session.delete(utilisateur)
    db.session.commit()
    flash('Utilisateur supprimé avec succès.', 'success')
    return redirect(url_for('utilisateurs'))





@app.route('/dossiers/<int:dossier_id>/changer_referent', methods=['POST'])
@login_required
def changer_referent(dossier_id):
    dossier = Dossier.query.get_or_404(dossier_id)
    form = ChangerReferentForm()

    utilisateurs_possibles = User.query.filter(
        User.supprimé == False,
        User.role.in_(['admin','managing-partner','partner','managing-associate',
                       'juriste','avocat','comptabilité','qualité','clerc','secrétaire','user-manager'])
    ).order_by(User.nom).all()
    form.nouveau_referent.choices = [(u.id, u.nom) for u in utilisateurs_possibles]

    if not form.validate_on_submit():
        flash("Formulaire invalide.", "danger")
        return redirect(url_for('dossiers'))

    nouveau_id = form.nouveau_referent.data
    ancien_id = dossier.user_id

    if ancien_id == nouveau_id:
        flash("Aucun changement : le référent est identique.", "info")
        return redirect(url_for('dossiers'))

    try:
        dossier.user_id = nouveau_id
        db.session.add(dossier)

        hist = AttributionHistorique(
            dossier_id=dossier.id,
            ancien_referent_id=ancien_id,
            nouveau_referent_id=nouveau_id,
            auteur_id=current_user.id,                 # ✅ bon champ
            date_attribution=datetime.utcnow(),        # ✅ timestamp
            motif=(form.motif.data or '').strip() or None
        )
        db.session.add(hist)

        db.session.commit()
        flash("Référent modifié et historisé ✅", "success")
    except Exception:
        db.session.rollback()
        current_app.logger.exception("Erreur changement référent")
        flash("❌ Erreur lors du changement de référent.", "danger")

    return redirect(url_for('dossiers'))






#calendrier



# ── 1) exposer TES dossiers ─────────────────────────────────────────────
# ── API : événements dossiers ──────────────────────────────────────────────
# @app.route("/api/events")
# @login_required
# def api_dossier_events():
#     query = Dossier.query.filter_by(supprimé=False)
#     if current_user.role not in ADMIN_ROLES:
#         query = query.filter_by(user_id=current_user.id)

#     evts = [
#         {
#             "id"    : f"d{d.id}",
#             "title" : d.nom,
#             "start" : d.date_ouverture.strftime("%Y-%m-%dT08:00:00"),
#             "end" : d.date_ouverture.strftime("%Y-%m-%dT09:00:00"),
#             "description": d.description or "Pas de description",
#             "allDay": False,
#             "color" : "#1393EE"
#         }
#         for d in query if d.date_ouverture
#     ]
#     return jsonify(evts)

# # ── API : calendrier partagé ───────────────────────────────────────────────
# @app.route("/api/calendar/events", methods=["GET", "POST"])
# @login_required
# def api_calendar_events():
#     if request.method == "POST":
#         data  = request.get_json(silent=True) or {}
#         title = data.get("title", "").strip()
#         start = data.get("start")
#         end   = data.get("end")

#         if not title or not start:
#             return "Titre ou date manquants", 400
#         try:
#             start_dt = datetime.fromisoformat(start)
#             end_dt   = datetime.fromisoformat(end) if end else None
#         except ValueError:
#             return "Format de date invalide", 400

#         ev = CalendarEvent(title=title, start=start_dt, end=end_dt, user_id=current_user.id)
#         db.session.add(ev)
#         db.session.commit()
#         return jsonify({"id": ev.id}), 201

#     # GET --------------------------------------------------------------
#     query = CalendarEvent.query.order_by(CalendarEvent.start)
#     if current_user.role not in ADMIN_ROLES:
#         query = query.filter_by(user_id=current_user.id)

#     evts = [
#         {
#             "id"    : ev.id,
#             "title" : ev.title,
#             "start" : ev.start.isoformat(),
#             "end"   : ev.end.isoformat() if ev.end else None,
#             "description": ev.description or "Pas de description",
#             "allDay": False,
#             "color" : "#27e777"
#         }
#         for ev in query
#     ]
#     return jsonify(evts)

# # ── API : suppression d’un événement ───────────────────────────────────────
# @app.route("/api/calendar/events/<int:event_id>", methods=["DELETE"])
# @login_required
# def delete_calendar_event(event_id):
#     ev = CalendarEvent.query.get_or_404(event_id)
#     if ev.user_id != current_user.id and current_user.role not in ADMIN_ROLES:
#         abort(403)

#     db.session.delete(ev)
#     db.session.commit()
#     return "", 204

@app.route('/changer_mdp', methods=['GET', 'POST'])
@login_required
def changer_mdp():
    form = ChangePasswordForm()
    if form.validate_on_submit():
        if not check_password_hash(current_user.password_hash, form.ancien_password.data):
            flash("Mot de passe actuel incorrect", "danger")
            return redirect(url_for('changer_mdp'))
        
        current_user.password_hash = generate_password_hash(form.nouveau_password.data)
        db.session.commit()
        flash("Votre mot de passe a été mis à jour avec succès.", "success")
        return redirect(url_for('dashboard'))

    return render_template('changer_mdp.html', form=form)


#mot de passe oublié


from flask import send_from_directory

# @app.route('/robots.txt')
# def robots_txt():
#     return send_from_directory('static', 'robots.txt')


#notifications 
def create_notification(*, user_id:int, title:str, message:str, url:str|None=None):
    # notifications in-app désactivées volontairement
    return

ATTRIBUTORS = {'admin','managing-partner','partner','managing-associate',}
ASSIGNEE_ROLES = {'avocat','juriste','associate','managing-associate'}  # qui peut recevoir un dossier




#attribution dossier
# ✅ ROUTE UNIQUE pour attribuer
import logging
log = logging.getLogger(__name__)

@app.route('/dossiers/attribuer', methods=['GET','POST'])
@roles_required('admin','managing-partner','partner','managing-associate')
def attribuer_dossier():
    form = AttributionForm()
    form.dossier_id.choices = [(d.id, f"{d.client.societe} - {d.nom}") for d in Dossier.query.order_by(Dossier.id)]
    form.user_id.choices    = [(u.id, u.nom) for u in User.query.order_by(User.nom)]  # ← test sans filtre

    if form.validate_on_submit():
        dossier_id  = form.dossier_id.data
        new_user_id = form.user_id.data

        dossier = Dossier.query.get_or_404(dossier_id)
        dossier.user_id = new_user_id

        # url = url_for('dossiers', _anchor=f'dossier-{dossier.id}')
        # create_notification(
        #     user_id=new_user_id,
        #     title="Nouveau dossier attribué",
        #     message=f"Vous avez reçu le dossier « {dossier.nom} ».",
        #     url=url
        # )
        db.session.commit()
        flash("Dossier attribué et notification créée.", "success")
        return redirect(url_for('dossiers'))
    else:
        if request.method == 'POST':
            current_app.logger.warning(f"[attribuer] form errors: {form.errors}")

    return render_template('attribuer_dossier.html', form=form)  # ← correspond au vrai fichier







# #modifier référent
# @app.route('/modifier_referent/<int:dossier_id>', methods=['GET', 'POST'])
# @login_required
# def modifier_referent(dossier_id):
#     require_attributor()  # ⛔

#     dossier = Dossier.query.get_or_404(dossier_id)
#     anciens_referents = User.query.filter(User.role.in_(ASSIGNEE_ROLES)).all()

#     form = FlaskForm()
#     form.referent_id = SelectField('Nouveau référent', coerce=int,
#                                    choices=[(u.id, u.nom) for u in anciens_referents])

#     if request.method == 'POST' and 'referent_id' in request.form:
#         ancien_id = dossier.user_id
#         nouveau_id = int(request.form['referent_id'])

#         if nouveau_id != ancien_id:
#             dossier.user_id = nouveau_id
#             historique = AttributionHistorique(
#                 dossier_id=dossier.id,
#                 ancien_referent_id=ancien_id,
#                 nouveau_referent_id=nouveau_id,
#                 auteur_id=current_user.id
#             )
#             db.session.add(historique)

#             # notif
#             try:
#                 url = url_for('get_dossier', id=dossier.id)
#                 create_notification(
#                     user_id=nouveau_id,
#                     title="Nouveau référent",
#                     message=f"Vous êtes désormais référent du dossier « {dossier.nom} ».",
#                     url=url
#                 )
#                 db.session.commit()
#                 flash("Référent modifié avec succès, historique mis à jour.", "success")
#             except Exception:
#                 db.session.rollback()
#                 flash("Erreur lors de la modification du référent.", "danger")
#         else:
#             flash("Le nouveau référent est identique à l'actuel.", "warning")

#         return redirect(url_for('dossiers'))

#     return render_template("modifier_referent.html", dossier=dossier, form=form)


def roles_required(*roles):
    def deco(f):
        @wraps(f)
        def wrapper(*a, **kw):
            if not current_user.is_authenticated or current_user.role not in roles:
                abort(403)  # ou flash + redirect si tu préfères
            return f(*a, **kw)
        return wrapper
    return deco

#réinitialisation du mot de passe
# def send_reset_email(user, token):
#     # Si tu as un SMTP/Flask-Mail, envoie un vrai mail ici.
#     # En dev, on affiche juste le lien pour cliquer.
#     reset_url = url_for('reset_password', token=token, _external=True)
#     app.logger.warning("🔐 Lien de réinitialisation (DEV) : %s", reset_url)
#     flash("Un lien de réinitialisation a été généré. (En dev: regarde les logs / console)", "info")
#     # Optionnel: pour debug, tu peux aussi l’afficher à l’écran:
#     flash(reset_url, "warning")

# @app.route('/password/forgot', methods=['GET', 'POST'])
# def forgot_password():
#     if current_user.is_authenticated:
#         return redirect(url_for('dashboard'))

#     form = RequestResetForm()
#     if form.validate_on_submit():
#         email = form.email.data.strip().lower()
#         user = User.query.filter_by(email=email).first()

#         # Toujours répondre pareil (ne pas divulguer si l'email existe)
#         if user:
#             token = generate_reset_token(user.email)
#             try:
#                 send_reset_email(user, token)
#             except Exception as e:
#                 app.logger.exception("Erreur envoi email reset: %s", e)
#                 # On ne révèle rien à l’utilisateur pour sécurité

#         flash("Si un compte existe avec cet email, un lien a été envoyé.", "success")
#         return redirect(url_for('login'))

#     return render_template('auth/forgot_password.html', form=form)
@app.route('/password/forgot', methods=['GET', 'POST'])
def forgot_password():
    form = RequestResetForm()
    if form.validate_on_submit():
        user = User.query.filter_by(email=form.email.data.strip()).first()
        # Toujours dire "si l'email existe, on envoie", pour ne pas leak les comptes.
        if user:
            token = make_reset_token(user)
            reset_link = reset_url_for(token)
            try:
                send_reset_email(user, token)  # cette fonction doit utiliser reset_url_for(token)
                current_app.logger.info("🔗 RESET URL sent: %s", reset_link)
            except Exception as e:
                current_app.logger.error("Erreur envoi email reset: %s", e, exc_info=True)
        flash("Si cet e-mail existe, un lien de réinitialisation a été envoyé.", "info")
        return redirect(url_for('login'))
    return render_template('auth/forgot_password.html', form=form)


serializer = URLSafeTimedSerializer(app.config["SECRET_KEY"])

@app.route('/password/reset/<token>', methods=['GET', 'POST'])
def reset_password(token):
    data = verify_reset_token(token, max_age=3600)
    if data is None:
        flash("Lien de réinitialisation invalide.", "danger")
        return redirect(url_for('forgot_password'))
    if data == "expired":
        flash("Lien de réinitialisation expiré. Merci de refaire la demande.", "warning")
        return redirect(url_for('forgot_password'))

    user = User.query.filter_by(id=data.get("uid"), email=data.get("e")).first()
    if not user:
        flash("Lien de réinitialisation invalide.", "danger")
        return redirect(url_for('forgot_password'))

    form = ResetPasswordForm()
    if form.validate_on_submit():
        user.set_password(form.password.data)
        db.session.commit()
        flash("Votre mot de passe a été réinitialisé avec succès.", "success")
        return redirect(url_for('login'))
    return render_template('auth/reset_password.html', form=form)

#création api
from flask import jsonify, request
from sqlalchemy import or_

@app.route('/api/clients')
@login_required
def api_clients():
    q = (request.args.get('q') or '').strip()
    page = request.args.get('page', type=int, default=1)
    per_page = 20

    query = Client.query.filter_by(supprimé=False)
    if q:
        like = f"%{q}%"
        query = query.filter(or_(
            Client.societe.ilike(like),
            # dé-commente/ajoute d'autres colonnes si utiles :
            # Client.email.ilike(like),
            # Client.telephone.ilike(like),
        ))

    p = query.order_by(Client.societe).paginate(page=page, per_page=per_page, error_out=False)
    return jsonify({
        'results': [{'id': c.id, 'text': c.societe} for c in p.items],
        'pagination': {'more': p.has_next}
    })


@app.route('/api/dossiers')
@login_required
def api_dossiers():
    q = (request.args.get('q') or '').strip()
    page = request.args.get('page', type=int, default=1)
    per_page = 20
    client_id = request.args.get('client_id', type=int)

    query = Dossier.query.filter(Dossier.supprimé == False)
    if client_id:
        query = query.filter(Dossier.client_id == client_id)
    if q:
        like = f"%{q}%"
        query = query.filter(Dossier.nom.ilike(like))

    # éviter les clients supprimés
    query = query.join(Client).filter(Client.supprimé == False)

    p = query.order_by(Dossier.nom).paginate(page=page, per_page=per_page, error_out=False)
    return jsonify({
        'results': [{
            'id': d.id,
            'text': f"{d.nom} — {d.client.societe}"
        } for d in p.items],
        'pagination': {'more': p.has_next}
    })


# LOGIN (1er facteur)
@app.route('/login', methods=['GET', 'POST'])
def login():
    form = LoginForm()

    # GET → afficher le formulaire
    if request.method == 'GET':
        return render_template('login.html', form=form)

    # POST sans validation → réafficher avec erreurs (toujours RETURN)
    if not form.validate_on_submit():
        flash('Veuillez remplir correctement le formulaire.')
        return render_template('login.html', form=form), 400

    # Auth 1er facteur
    email = form.email.data.strip().lower()
    pwd   = form.password.data
    user = User.query.filter_by(email=email).first()
    if not user or not user.check_password(pwd):
        flash('Identifiants invalides')
        return render_template('login.html', form=form), 401

    # Déclencheurs OTP e-mail
    ip = get_client_ip()
    fp = device_fingerprint()
    first_time = (not user.two_factor_enabled) or (user.two_factor_method != 'email')
    ip_changed = bool(user.last_login_ip) and user.last_login_ip != ip
    new_device = not has_valid_trusted_device(user)

    if first_time or ip_changed or new_device:
        session['preauth_user_id'] = user.id
        issue_email_otp(user.id, user.email)  # envoi du code
        return redirect(url_for('twofa_verify'))

    # Pas d’OTP nécessaire → connexion directe
    login_user(user, remember=True)
    user.last_login_ip = ip
    user.last_device_fp = fp
    user.two_factor_enabled = True
    user.two_factor_method = 'email'
    db.session.commit()
    return redirect(url_for('dashboard'))

# SETUP (QR + activation)
@app.route('/2fa/setup', methods=['GET','POST'])
@login_required
def twofa_setup():
    u = current_user
    if request.method == 'GET':
        if not u.two_factor_secret:
            u.two_factor_secret = pyotp.random_base32(); db.session.commit()
        return render_template('2fa_setup.html')  # affiche <img src="/2fa/qrcode"> + input code
    code = request.form.get('code','').strip()
    totp = pyotp.TOTP(u.two_factor_secret)
    if totp.verify(code, valid_window=current_app.config['TFA_TOTP_WINDOW']):
        u.two_factor_enabled = 1; u.two_factor_method = 'totp'; db.session.commit()
        flash("Double authentification activée.")
        return redirect(url_for('profile'))
    flash("Code invalide."); return redirect(url_for('twofa_setup'))

@app.route('/2fa/qrcode')
@login_required
def twofa_qrcode():
    u = current_user
    issuer = "MyHouda"
    uri = pyotp.totp.TOTP(u.two_factor_secret).provisioning_uri(name=u.email, issuer_name=issuer)
    img = qrcode.make(uri); buf = io.BytesIO(); img.save(buf, format='PNG'); buf.seek(0)
    return send_file(buf, mimetype='image/png')

# VERIFY (2e facteur)
@app.route('/2fa/verify', methods=['GET','POST'])
def twofa_verify():
    uid = session.get('preauth_user_id')
    if not uid: return redirect(url_for('login'))
    user = User.query.get(uid)

    if request.method == 'POST':
        data = session.get('email_otp') or {}
        if data.get('uid') != user.id:
            flash("Session OTP invalide."); return redirect(url_for('login'))

        # expire au bout de 10 min, max 5 essais
        if time.time() - data['ts'] > 600:
            flash("Code expiré, un nouveau a été envoyé.")
            issue_email_otp(user.id, user.email); return redirect(url_for('twofa_verify'))
        if data['tries'] >= 5:
            flash("Trop d'essais. Nouveau code envoyé.")
            issue_email_otp(user.id, user.email); return redirect(url_for('twofa_verify'))

        code = request.form.get('code','').strip()
        if code != data['code']:
            data['tries'] += 1
            session['email_otp'] = data
            flash("Code incorrect."); return redirect(url_for('twofa_verify'))

        # Succès
        from flask_login import login_user
        login_user(user, remember=True)

        ip = get_client_ip()
        fp = device_fingerprint()
        user.last_login_ip = ip
        user.last_device_fp = fp
        user.two_factor_enabled = True
        user.two_factor_method = 'email'
        db.session.commit()

        resp = redirect(url_for('dashboard'))
        if request.form.get('remember_device') == 'on':
            resp = set_trusted_cookie(resp, user)

        # clean session
        session.pop('preauth_user_id', None)
        session.pop('email_otp', None)
        return resp

    return render_template('2fa_verify.html')

@app.post('/2fa/email/send')
def twofa_email_send():
    uid = session.get('preauth_user_id')
    if not uid:
        flash("Session expirée, reconnectez-vous.")
        return redirect(url_for('login'))
    # retrouve l'utilisateur si besoin d'une vérification
    from app.models import User
    u = User.query.get(uid)
    if not u:
        flash("Utilisateur introuvable.")
        return redirect(url_for('login'))

    issue_email_otp(u.id, u.email)  # renvoi du code
    flash("Nouveau code envoyé par e-mail.")
    return redirect(url_for('twofa_verify'))