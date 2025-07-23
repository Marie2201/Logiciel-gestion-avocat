from app import app, db
from app.models import Client, Dossier, Utilisateur
from datetime import date

with app.app_context():
    # Ajouter un client fictif
    client = Client(
        nom="Dupont",
        prenom="Marie",
        email="marie.dupont@example.com",
        telephone="0600000000"
    )
    db.session.add(client)
    db.session.commit()

    # Ajouter un dossier fictif
    dossier = Dossier(
        titre="Affaire X vs Y",
        type="Contentieux civil",
        date_ouverture=date.today(),
        statut="En cours",
        client_id=client.id
    )
    db.session.add(dossier)
    db.session.commit()

    # Ajouter un utilisateur fictif
    utilisateur = Utilisateur(
        nom="Maître Jean Martin",
        role="Avocat",
        email="jean.martin@cabinet.com",
        mot_de_passe="secret123"
    )
    db.session.add(utilisateur)
    db.session.commit()

    print("Client, dossier et utilisateur fictifs ajoutés avec succès ✅")
