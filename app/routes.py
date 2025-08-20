from flask import render_template, redirect, url_for, flash, request, jsonify, send_from_directory, abort, make_response, current_app
from app.forms import TimesheetForm, ClientForm, DossierForm, DeleteForm, FactureForm, AjoutUtilisateurForm, LoginForm, GenererFactureForm, DummyForm
from app.forms import DocumentForm, RegistrationForm, UserForm, AttributionForm, FlaskForm, ChangerReferentForm, ChangePasswordForm
from app.forms import RequestResetForm, ResetPasswordForm
from app.models import Timesheet, Dossier, Client, Facture, User, Document, AttributionHistorique, CalendarEvent
from app import app, db
from datetime import datetime, timedelta, date
from sqlalchemy.sql import func
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
from datetime import time


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

@app.route('/')
def index():
    # Si l'utilisateur est déjà connecté, redirigez-le vers le tableau de bord ou timesheets
    if current_user.is_authenticated:
        return redirect(url_for('dashboard')) # Ou 'dashboard' si c'est votre page principale

    # Sinon, redirigez vers la page de connexion
    return redirect(url_for('login')) # Assurez-vous que le nom de l'endpoint est 'login'


@app.route('/dashboard') # Tu peux avoir les deux ou juste /dashboard
@login_required
def dashboard():
    # KPI 1: Total Clients
  # Obtenir la liste des rôles autorisés à tout voir
    roles_autorises = ['admin', 'managing-partner', 'partner', 'managing-associate', 'comptabilité', 'qualité']

    # KPI 1: Total Clients
    if current_user.role in roles_autorises:
        total_clients = Client.query.count()
    else:
        total_clients = Client.query.filter_by(user_id=current_user.id).count()

    # KPI 2: Total Dossiers (Statut 'En cours')
    if current_user.role in roles_autorises:
        total_dossiers = Dossier.query.count()
    else:
        total_dossiers = Dossier.query.filter_by(user_id=current_user.id).count()

    # --- Dossiers de l'utilisateur pour les restrictions ---
    dossiers_ids = [d.id for d in Dossier.query.filter_by(user_id=current_user.id).all()] \
        if current_user.role not in roles_autorises else None

    # KPI 3: Factures En Attente
    if current_user.role in roles_autorises:
        factures_en_attente = Facture.query.count()
    else:
        factures_en_attente = Facture.query.filter(Facture.dossier_id.in_(dossiers_ids)).count()

    # KPI 4: Montant Total Facturé (TTC)
    if current_user.role in roles_autorises:
        montant_total = db.session.query(func.sum(Facture.montant_ttc)).scalar() or 0
    else:
        montant_total = db.session.query(func.sum(Facture.montant_ttc))\
            .filter(Facture.dossier_id.in_(dossiers_ids)).scalar() or 0

    # KPI 5: Timesheets en attente de facturation
    if current_user.role in roles_autorises:
        total_ts = Timesheet.query.count()
    else:
        total_ts = Timesheet.query.filter_by(user_id=current_user.id).count()



    # Données pour les graphiques (Exemple : Répartition des statuts de dossiers)
    dossier_statuts = db.session.query(Dossier.statut, func.count(Dossier.id))\
                              .filter_by(supprimé=False)\
                              .group_by(Dossier.statut)\
                              .all()
    # Formatage pour Chart.js
    labels_statuts = [s[0] for s in dossier_statuts]
    data_statuts = [s[1] for s in dossier_statuts]
    current_time = datetime.utcnow()
    # Tu pourrais ajouter plus de données pour d'autres graphiques (ex: factures par mois)

    return render_template('dashboard.html',
                           total_clients=total_clients,
                           dossiers_actifs=total_dossiers,
                           factures_en_attente=factures_en_attente,
                           montant_total_facture_ttc=montant_total,
                           timesheets_en_attente_facturation=total_ts,
                           labels_statuts=labels_statuts,
                           data_statuts=data_statuts,
                           now=current_time)


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
    if current_user.role in ['admin', 'managing-partner', 'partner','managing-associate', 'comptabilité', 'qualité']:
        clients = Client.query.filter_by(supprimé=False).all()
    else:
        clients = Client.query.filter_by(supprimé=False, user_id=current_user.id).all()
    return render_template('clients.html', form=form, delete_form=delete_form, clients=clients)


#modifier un client
@app.route('/clients/modifier/<int:client_id>', methods=['GET', 'POST'])
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
ADMIN_ROLES = {"admin", "managing-partner", "partner", "managing-associate", "comptabilité", "qualité"}
@app.route('/dossiers', methods=['GET', 'POST'])
@login_required
def dossiers():
    form = DossierForm()
    delete_form = DeleteForm()
    changer_form = ChangerReferentForm()

    # Clients actifs
    clients = Client.query.filter_by(supprimé=False).all()
    form.client_id.choices = [(c.id, c.societe) for c in clients]

    # Utilisateurs pour attribution
    utilisateurs_possibles = User.query.filter(
        User.supprimé == False,
        User.role.in_(['admin','managing-partner', 'partner', 'managing-associate', 'juriste', 'avocat', 'comptabilité', 'qualité', 'clerc', 'secrétaire'])
    ).all()
    form.user_id.choices = [(u.id, u.nom) for u in utilisateurs_possibles]

    # Pour changement de référent
    changer_form.nouveau_referent.choices = [(u.id, u.nom) for u in utilisateurs_possibles]

    # Pré-remplir user_id à l'ouverture
    if request.method == "GET":
        form.user_id.default = current_user.id
        form.process()
        print("📥 Données POST reçues :", request.form)

    # --- Création d'un dossier (POST valide) ---
    if form.validate_on_submit():
        try:
            user_id = form.user_id.data or current_user.id

            # 1) Numéro saisi manuellement ?
            numero_input = ""
            if hasattr(form, "numero") and form.numero.data:
                numero_input = form.numero.data.strip()

            if numero_input:
                # Valider & normaliser
                annee, sequence = parse_numero_to_components(numero_input)
                numero_norm = compute_numero(sequence, annee)

                nouveau_dossier = Dossier(
                    nom=form.nom.data,
                    description=form.description.data,
                    date_ouverture=form.date_ouverture.data,
                    procedure=form.procedure.data,
                    statut=form.statut.data,
                    client_id=form.client_id.data,
                    user_id=user_id,
                    # champs liés au numéro
                    annee=annee,
                    sequence=sequence,
                    numero=numero_norm
                )
                db.session.add(nouveau_dossier)
                try:
                    db.session.commit()
                    flash("✅ Dossier ajouté avec succès.", "success")
                    return redirect(url_for('dossiers'))
                except IntegrityError:
                    db.session.rollback()
                    flash("❌ Numéro de dossier déjà utilisé. Merci d’en saisir un autre.", "danger")
                    # On retombe plus bas pour ré-afficher la page avec le formulaire et les erreurs
            else:
                # 2) Génération automatique (année courante, incrément de séquence)
                annee = datetime.now().year
                MAX_RETRY = 5
                for _ in range(MAX_RETRY):
                    max_seq = db.session.query(func.max(Dossier.sequence)).filter_by(annee=annee).scalar() or 0
                    sequence = max_seq + 1
                    numero_gen = compute_numero(sequence, annee)

                    nouveau_dossier = Dossier(
                        nom=form.nom.data,
                        description=form.description.data,
                        date_ouverture=form.date_ouverture.data,
                        procedure=form.procedure.data,
                        statut=form.statut.data,
                        client_id=form.client_id.data,
                        user_id=user_id,
                        annee=annee,
                        sequence=sequence,
                        numero=numero_gen
                    )
                    db.session.add(nouveau_dossier)
                    try:
                        db.session.commit()
                        flash("✅ Dossier ajouté avec succès.", "success")
                        return redirect(url_for('dossiers'))
                    except IntegrityError:
                        # collision de concurrence (rare) → on retente
                        db.session.rollback()
                        continue

                flash("❌ Impossible de générer un numéro unique. Réessayez.", "danger")

        except ValueError as ve:
            db.session.rollback()
            flash(f"❌ {str(ve)}", "danger")
        except Exception as e:
            db.session.rollback()
            print("❌ Erreur lors de l'ajout du dossier :", e)
            flash("❌ Une erreur s’est produite lors de l’ajout du dossier.", "danger")
    else:
        if request.method == "POST":
            print("⚠️ Erreurs formulaire :", form.errors)

    # --- Liste des dossiers selon les droits ---
    client_id = request.args.get('client_id', type=int)
    query = Dossier.query.filter_by(supprimé=False)

    if current_user.role not in ['admin', 'managing-partner', 'partner', 'managing-associate', 'comptabilité', 'qualité']:
        query = query.filter_by(user_id=current_user.id)

    if client_id:
        query = query.filter_by(client_id=client_id)

    dossiers_list = query.order_by(Dossier.id.desc()).all()

    return render_template(
        'dossiers.html',
        form=form,
        delete_form=delete_form,
        dossiers=dossiers_list,
        clients=clients,
        users=utilisateurs_possibles,
        changer_form=changer_form
    )


#modifier dossier
@app.route('/dossiers/modifier/<int:dossier_id>', methods=['GET', 'POST'])
def modifier_dossier(dossier_id):
    dossier = Dossier.query.get_or_404(dossier_id)
    form = DossierForm(obj=dossier)

    form.client_id.choices = [(client.id, f"{client.societe}") for client in Client.query.filter_by(supprimé=False).all()]
    form.user_id.choices = [(user.id, user.nom) for user in User.query.filter(
        User.role.in_(['admin','managing-partner', 'partner', 'managing-associate', 'juriste', 'avocat', 'comptabilité', 'qualité', 'clerc', 'secrétaire']),
        User.supprimé == False
    ).all()]
#     utilisateurs = User.query.filter(
#     User.role.in_(['admin', 'managing-partner', 'partner', 'managing-associate', 'juriste', 'avocat']),
#     User.supprimé == False
# ).all()
    print("📋 Utilisateurs disponibles pour attribution :")
    tous_les_users = User.query.all()
    print("🧾 Liste complète des utilisateurs en base :")
    for u in tous_les_users:
        print(f"- {u.id} | {u.nom} | {u.email} | rôle: '{u.role}' | supprimé: {u.supprimé}")

    if form.validate_on_submit():
        ancien_user_id = dossier.user_id
        nouveau_user_id = form.user_id.data

        dossier.nom = form.nom.data
        dossier.description = form.description.data
        dossier.date_ouverture = form.date_ouverture.data
        dossier.procedure = form.procedure.data
        dossier.statut = form.statut.data
        dossier.client_id = form.client_id.data
        dossier.user_id = nouveau_user_id

        db.session.commit()

        # 💌 Envoi de notification si changement
        if ancien_user_id != nouveau_user_id:
            nouveau_referent = User.query.get(nouveau_user_id)
            envoyer_mail_attribution(nouveau_referent, dossier)

        flash("Dossier modifié avec succès.", "success")
        return redirect(url_for('dossiers'))

    return render_template('modifier_dossier.html', form=form, dossier=dossier)

    # delete_form = DeleteForm()  # formulaire WTForm minimal
    # return render_template('dossiers.html', form=form, delete_form=delete_form, dossiers=dossiers_list)


#supprimer dossier
@app.route('/dossiers/supprimer/<int:dossier_id>', methods=['POST'])
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

    if current_user.role in ['admin', 'managing-partner', 'partner','managing-associate', 'comptabilité', 'qualité']:
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
def modifier_facture(facture_id):
    facture = Facture.query.get_or_404(facture_id)
    form = FactureForm(obj=facture) # Pré-remplit le formulaire avec les données de la facture
    #form.dossier.query = Dossier.query.filter_by(supprimé=False).all() # S'assurer que les choix du dossier sont à jour

    if form.validate_on_submit():
        facture.date = form.date.data
        facture.montant_ht = form.montant_ht.data
        facture.montant_ttc = form.montant_ttc.data
        facture.devise = form.devise.data
        facture.statut = form.statut.data
        facture.dossier_id = form.dossier.data.id
        db.session.commit()
        flash('Facture modifiée avec succès.', 'success')
        return redirect(url_for('factures'))

    
    return render_template('modifier_facture.html', form=form, facture=facture) # Crée un template modifier_facture.html

# --- Nouvelle Route pour la Suppression d'une Facture ---
@app.route('/supprimer_facture/<int:id>', methods=['POST'])
#@login_required
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

    # Choix dossiers (clients non supprimés + dossiers non supprimés)
    form.dossier_id.choices = [
        (d.id, f"{d.client.societe} - {d.nom}")
        for d in Dossier.query.join(Client)
              .filter(Dossier.supprimé == False, Client.supprimé == False)
              .order_by(Client.societe, Dossier.nom)
              .all()
    ]

    if form.validate_on_submit():
        tva_bool = (form.tva_applicable.data == 'oui')
        tva_rate = 0.18

        if form.type_facturation.data == 'horaire':
            dt_debut = datetime.combine(form.date.data, form.heure_debut.data)
            dt_fin   = datetime.combine(form.date.data, form.heure_fin.data)
            if dt_fin < dt_debut:
                dt_fin += timedelta(days=1)  # passage minuit
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
                statut=form.statut.data,              # ✅ AJOUTÉ
                devise=(form.devise.data or "XOF").upper(),
                description=form.description.data or '',
                dossier_id=form.dossier_id.data,
                user_id=current_user.id
            )

        else:  # forfait
            ht  = round(float(form.montant_forfait.data), 2)
            ttc = round(ht * (1 + tva_rate), 2) if tva_bool else ht

            ts = Timesheet(
                date=form.date.data,
                type_facturation='forfait',
                heure_debut = time(0, 0, 0),
                heure_fin   = time(0, 0, 0),
                duree_heures = 0,
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

    # Affichage filtré selon rôle
    if current_user.role in ['admin', 'managing-partner', 'partner', 'managing-associate', 'comptabilité', 'qualité']:
        timesheets_list = Timesheet.query.filter_by(supprimé=False)\
                            .order_by(Timesheet.date.desc(), Timesheet.id.desc()).all()
    else:
        timesheets_list = Timesheet.query.filter_by(user_id=current_user.id, supprimé=False)\
                            .order_by(Timesheet.date.desc(), Timesheet.id.desc()).all()

    return render_template("timesheets.html", form=form, timesheets=timesheets_list, delete_form=DeleteForm())


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
def delete_timesheet(id):
    ts = Timesheet.query.get_or_404(id)
    ts.supprimé = True  # Ne pas supprimer réellement
    db.session.commit()
    flash("Timesheet archivé avec succès.", "warning")
    return redirect(url_for('timesheets'))



@app.route('/login', methods=['GET', 'POST'])
def login():
    form = LoginForm()
    if form.validate_on_submit():
        user = User.query.filter_by(email=form.email.data.lower()).first()
        print("USER TROUVÉ :", user) 
        if user and check_password_hash(user.password_hash, form.password.data):  # ou form.mot_de_passe.data
            login_user(user, remember=form.remember_me.data)
            flash('Connexion réussie', 'success')
            return redirect(url_for('dashboard'))  # ou une autre route après login
        else:
            flash('Identifiants incorrects', 'danger')
    return render_template('login.html', form=form)

# Vous aurez aussi besoin de routes pour 'forgot_password' et 'register' si vous incluez les liens.
# @app.route('/forgot_password')
# def forgot_password():
#     flash("La page de réinitialisation de mot de passe n'est pas encore implémentée.", "info")
#     return redirect(url_for('login')) # Redirige vers la page de connexion pour l'instant

@app.route('/register', methods=['GET', 'POST'])
def register():
    if current_user.role not in ['admin', 'managing-partner', 'partner','managing-associate','comptabilité', 'qualité']:
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
    if current_user.role not in ['admin', 'managing-partner', 'partner','managing-associate','comptabilité', 'qualité']:
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
    if current_user.role not in ['admin', 'managing-partner', 'partner','managing-associate','comptabilité', 'qualité']:
        query = query.filter(Timesheet.user_id == current_user.id)
    elif utilisateur_id:
        query = query.filter(Timesheet.user_id == utilisateur_id)

    # Filtrage par dates
    if date_debut:
        query = query.filter(Timesheet.date >= date_debut)
    if date_fin:
        query = query.filter(Timesheet.date <= date_fin)

    timesheets = query.order_by(Timesheet.date).all()
    utilisateurs = User.query.all() if current_user.role in ['admin', 'managing-partner', 'partner','managing-associate', 'comptabilité', 'qualité'] else []

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
    if current_user.role not in ['admin', 'managing-partner', 'partner','managing-associate','comptabilité', 'qualité']:
        flash("Accès refusé. Page réservée aux administrateurs.", "danger")
        return redirect(url_for('index'))

    users = User.query.all()
    print("Utilisateurs récupérés :", [u.email for u in users])  # 👈 pour débug

    return render_template('utilisateurs.html', users=users)


@app.route('/utilisateur/modifier/<int:id>', methods=['GET', 'POST'])
@login_required
def modifier_utilisateur(id):
    if current_user.role not in ['admin', 'managing-partner', 'partner','managing-associate', 'comptabilité', 'qualité']:
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
    if current_user.role not in ['admin', 'managing-partner', 'partner','managing-associate', 'comptabilité', 'qualité']:
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





# @app.route('/changer_referent_popup', methods=['POST'])
# @login_required
# def changer_referent_popup():
#     form = ChangerReferentForm()

#     # Recharge les choix dans le SelectField
#     form.nouveau_referent.choices = [(u.id, u.nom) for u in User.query.all()]

#     if form.validate_on_submit():
#         dossier_id = form.dossier_id.data
#         nouveau_referent_id = form.nouveau_referent.data

#         dossier = Dossier.query.get_or_404(dossier_id)
#         ancien_referent_id = dossier.user_id

#         if int(nouveau_referent_id) != ancien_referent_id:
#             dossier.user_id = nouveau_referent_id

#             historique = AttributionHistorique(
#                 dossier_id=dossier.id,
#                 ancien_referent_id=ancien_referent_id,
#                 nouveau_referent_id=nouveau_referent_id,
#                 auteur_id=current_user.id
#             )

#             db.session.add(historique)
#             db.session.commit()
#             flash("Référent modifié avec succès.", "success")
#         else:
#             flash("Aucun changement effectué.", "info")
#     else:
#         flash("Erreur dans le formulaire.", "danger")
#         print("Form errors:", form.errors)

#     return redirect(url_for('dossiers'))




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




