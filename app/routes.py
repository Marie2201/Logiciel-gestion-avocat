from flask import render_template, redirect, url_for, flash, request
from app.forms import TimesheetForm, ClientForm, DossierForm, DeleteForm, FactureForm, AjoutUtilisateurForm, LoginForm, GenererFactureForm, DummyForm
from app.models import Timesheet, Dossier, Client, Facture, User
from app import app, db
from datetime import datetime, timedelta, date
from sqlalchemy.sql import func
from werkzeug.security import generate_password_hash, check_password_hash
from flask_login import login_user, logout_user, login_required, current_user


#from app import app
#from flask import render_template

@app.route('/')
def index():
    # Si l'utilisateur est déjà connecté, redirigez-le vers le tableau de bord ou timesheets
    if current_user.is_authenticated:
        return redirect(url_for('dashboard')) # Ou 'dashboard' si c'est votre page principale

    # Sinon, redirigez vers la page de connexion
    return redirect(url_for('login')) # Assurez-vous que le nom de l'endpoint est 'login'


@app.route('/dashboard') # Tu peux avoir les deux ou juste /dashboard
#@login_required
def dashboard():
    # KPI 1: Total Clients
    total_clients = Client.query.count()

    # KPI 2: Dossiers Actifs (Statut 'En cours')
    dossiers_actifs = Dossier.query.filter_by(statut='En cours', supprimé=False).count()

    # KPI 3: Factures En Attente
    factures_en_attente = Facture.query.filter_by(statut='En attente').count()

    # KPI 4: Montant Total Facturé (TTC)
    # Utilise func.sum pour sommer les montants_ttc
    montant_total_facture_ttc = db.session.query(func.sum(Facture.montant_ttc)).scalar()
    montant_total_facture_ttc = float(montant_total_facture_ttc) if montant_total_facture_ttc else 0.0

    # KPI 5: Timesheets en attente de facturation
    timesheets_en_attente_facturation = Timesheet.query.filter_by(statut='en cours').count()

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
                           dossiers_actifs=dossiers_actifs,
                           factures_en_attente=factures_en_attente,
                           montant_total_facture_ttc=montant_total_facture_ttc,
                           timesheets_en_attente_facturation=timesheets_en_attente_facturation,
                           labels_statuts=labels_statuts,
                           data_statuts=data_statuts,
                           now=current_time)


# @app.route('/clients')
# def clients():
#     return render_template('clients.html')

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
            adresse=form.adresse.data
        )
        db.session.add(client)
        db.session.commit()
        flash("Client ajouté avec succès.", "success")
        return redirect(url_for('clients'))

    clients_list = Client.query.filter_by(supprimé=False).all()
    return render_template('clients.html', form=form, delete_form=delete_form, clients=clients_list)


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


#ajout dossiers
@app.route('/dossiers', methods=['GET', 'POST'])
def dossiers():
    form = DossierForm()
    delete_form = DeleteForm()
    form.client_id.choices = [(client.id, f"{client.societe}") for client in Client.query.filter_by(supprimé=False).all()]

    #print("Client ID sélectionné :", form.client_id.data)
    if form.validate_on_submit():
        dossier = Dossier(
            nom=form.nom.data,
            description=form.description.data,
            date_ouverture=form.date_ouverture.data,
            procedure=form.procedure.data,
            statut=form.statut.data,
            client_id=form.client_id.data 
        )
        db.session.add(dossier)
        db.session.commit()
        flash("Dossier ajouté avec succès.", "success")
        return redirect(url_for('dossiers'))

    dossiers_list = Dossier.query.filter_by(supprimé=False).join(Client).all()
    return render_template('dossiers.html', form=form, delete_form=delete_form, dossiers=dossiers_list)

#modifier dossier
@app.route('/dossiers/modifier/<int:dossier_id>', methods=['GET', 'POST'])
def modifier_dossier(dossier_id):
    dossier = Dossier.query.get_or_404(dossier_id)
    form = DossierForm(obj=dossier)
    form.client_id.choices = [(client.id, f"{client.societe}") for client in Client.query.filter_by(supprimé=False).all()]


    if form.validate_on_submit():
        dossier.nom = form.nom.data
        dossier.description = form.description.data
        dossier.date_ouverture = form.date_ouverture.data
        dossier.procedure = form.procedure.data
        dossier.statut = form.statut.data
        dossier.client_id = form.client_id.data

        db.session.commit()
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
    factures = Facture.query.all()
    add_form = FactureForm()
    delete_form = DeleteForm()

    return render_template('factures.html', factures=factures, add_form=add_form, delete_form=delete_form)


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
        facture.statut = form.statut.data
        facture.dossier_id = form.dossier.data.id
        db.session.commit()
        flash('Facture modifiée avec succès.', 'success')
        return redirect(url_for('factures'))

    # Si la requête est GET, ou si la validation a échoué, on rend le template de modification
    # Il est préférable d'avoir un formulaire de modification dans un modal ou une page séparée
    # Pour l'instant, je vais juste te montrer la logique côté backend.
    # Tu pourrais renvoyer un JSON si tu fais une modif via AJAX, ou rediriger vers une page de modification dédiée.
    # Pour rester simple avec les modaux, souvent on fait une requête GET pour récupérer les données dans le modal, puis POST pour soumettre.
    # Si tu as un modal de modification à part, tu n'aurais pas besoin d'une page HTML dédiée ici,
    # mais juste d'une route API qui gère le POST.
    # Puisque tu as un bouton "Modifier" qui fait un lien, on va assumer une redirection simple pour l'exemple.
    return render_template('modifier_facture.html', form=form, facture=facture) # Crée un template modifier_facture.html

# --- Nouvelle Route pour la Suppression d'une Facture ---


@app.route('/timesheets', methods=['GET', 'POST'])
@login_required
def timesheets():
    form = TimesheetForm()

    # Charger les dossiers pour le formulaire
    form.dossier_id.choices = [(d.id, d.nom) for d in Dossier.query.all()]

    # ➤ Ajouter automatiquement l'utilisateur connecté lors de la soumission
    if form.validate_on_submit():
        dt_debut = datetime.combine(form.date.data, form.heure_debut.data)
        dt_fin = datetime.combine(form.date.data, form.heure_fin.data)
        duree_heures = round((dt_fin - dt_debut).total_seconds() / 3600, 2)

        taux_horaire = float(form.taux_horaire.data)
        tva = form.tva_applicable.data == 'oui'
        montant_ht = round(duree_heures * taux_horaire, 2)
        montant_ttc = round(montant_ht * 1.20, 2) if tva else montant_ht

        ts = Timesheet(
            date=form.date.data,
            heure_debut=form.heure_debut.data,
            heure_fin=form.heure_fin.data,
            description=form.description.data,
            taux_horaire=taux_horaire,
            tva_applicable=tva,
            montant_ht=montant_ht,
            montant_ttc=montant_ttc,
            statut=form.statut.data,
            duree_heures=duree_heures,
            dossier_id=form.dossier_id.data,
            user_id=current_user.id  # 🎯 Lien automatique avec l'utilisateur connecté
        )
        db.session.add(ts)
        db.session.commit()
        flash('Timesheet ajouté avec succès.', 'success')
        return redirect(url_for('timesheets'))

    # ➤ Filtrage selon le rôle
    if current_user.role in ['admin', 'associé']:
        timesheets = Timesheet.query.all()
    else:
        timesheets = Timesheet.query.filter_by(user_id=current_user.id).all()

    delete_form = DeleteForm()

    return render_template('timesheets.html', form=form, timesheets=timesheets, delete_form=delete_form)


@app.route('/edit_timesheet/<int:id>', methods=['GET', 'POST'])
def edit_timesheet(id):
    timesheet = Timesheet.query.get_or_404(id)
    form = TimesheetForm(obj=timesheet)

    form.dossier_id.choices = [(d.id, d.nom) for d in Dossier.query.all()]

    if form.validate_on_submit():
        dt_debut = datetime.combine(form.date.data, form.heure_debut.data)
        dt_fin = datetime.combine(form.date.data, form.heure_fin.data)
        duree_heures = round((dt_fin - dt_debut).total_seconds() / 3600, 2)

        taux_horaire = float(form.taux_horaire.data)
        tva = form.tva_applicable.data == 'oui'
        montant_ht = round(duree_heures * taux_horaire, 2)
        montant_ttc = round(montant_ht * 1.2, 2) if tva else montant_ht

        form.populate_obj(timesheet)
        timesheet.duree_heures = duree_heures
        timesheet.taux_horaire = taux_horaire
        timesheet.montant_ht = montant_ht
        timesheet.montant_ttc = montant_ttc
        timesheet.tva_applicable = tva

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
        user = User.query.filter_by(email=form.email.data).first()
        if user and check_password_hash(user.password_hash, form.password.data):  # ou form.mot_de_passe.data
            login_user(user, remember=form.remember_me.data)
            flash('Connexion réussie', 'success')
            return redirect(url_for('dashboard'))  # ou une autre route après login
        else:
            flash('Identifiants incorrects', 'danger')
    return render_template('login.html', form=form)

# Vous aurez aussi besoin de routes pour 'forgot_password' et 'register' si vous incluez les liens.
@app.route('/forgot_password')
def forgot_password():
    flash("La page de réinitialisation de mot de passe n'est pas encore implémentée.", "info")
    return redirect(url_for('login')) # Redirige vers la page de connexion pour l'instant

@app.route('/register')
def register():
    flash("La page d'inscription n'est pas encore implémentée.", "info")
    return redirect(url_for('login')) # Redirige vers la page de connexion pour l'instant


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
    if current_user.role not in ['admin', 'associé']:
        flash("Accès interdit 🔒", "danger")
        return redirect(url_for('dashboard'))

    form = AjoutUtilisateurForm()

    if form.validate_on_submit():
        if User.query.filter_by(email=form.email.data).first():
            flash("Un utilisateur avec cet email existe déjà ❌", "danger")
        else:
            new_user = User(
                nom=form.nom.data,
                email=form.email.data,
                role=form.role.data
            )
            new_user.set_password(form.password.data)
            db.session.add(new_user)
            db.session.commit()
            flash("Nouvel utilisateur ajouté avec succès ✅", "success")
            return redirect(url_for('ajouter_utilisateur'))

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

        # Vérification qu’ils appartiennent tous au même dossier
        dossiers = set(ts.dossier_id for ts in timesheets)
        if len(dossiers) != 1:
            flash("Les timesheets doivent appartenir au même dossier pour générer une facture.", "danger")
            return redirect(url_for('generer_facture'))

        montant_ht_total = sum(ts.montant_ht for ts in timesheets)
        montant_ttc_total = sum(ts.montant_ttc for ts in timesheets)
        dossier_id = timesheets[0].dossier_id

        facture = Facture(
            date=datetime.utcnow().date(),
            montant_ht=montant_ht_total,
            montant_ttc=montant_ttc_total,
            statut="En attente",
            dossier_id=dossier_id,
        )
        db.session.add(facture)
        db.session.commit()

        # Associer les timesheets à la facture
        for ts in timesheets:
            ts.facture = facture
        db.session.commit()

        flash(f"Facture générée avec succès pour {len(timesheets)} timesheet(s).", "success")
        return redirect(url_for('factures'))

    # GET : Affichage avec filtres
    utilisateur_id = request.args.get('utilisateur_id', type=int)
    date_debut = request.args.get('date_debut')
    date_fin = request.args.get('date_fin')

    query = Timesheet.query.join(Dossier).filter(Timesheet.facture == None)

    # Seuls les associés/admins peuvent filtrer par utilisateur
    if current_user.role not in ['admin', 'associé']:
        query = query.filter(Timesheet.user_id == current_user.id)
    elif utilisateur_id:
        query = query.filter(Timesheet.user_id == utilisateur_id)

    # Filtrage par dates
    if date_debut:
        query = query.filter(Timesheet.date >= date_debut)
    if date_fin:
        query = query.filter(Timesheet.date <= date_fin)

    timesheets = query.order_by(Timesheet.date).all()
    utilisateurs = User.query.all() if current_user.role in ['admin', 'associé'] else []

    return render_template(
        'generer_facture.html',
        timesheets=timesheets,
        utilisateurs=utilisateurs,
        form=form
    )