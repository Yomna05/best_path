"""
Jeu de données statique pour le POC : un agent et ses patients déjà affectés
par la plateforme Med.tn (l'affectation est hors périmètre de ce microservice).

Coordonnées réalistes dans le Grand Tunis (Tunis, La Marsa, Ariana, Le Bardo,
Le Kram, Ben Arous).

Chaque point porte à la fois une 'adresse' (ce que fournirait Med.tn / l'agent
en pratique, cf. app/api.py) et des 'lat'/'lng' déjà connus (pour que les
tests et main.py restent rapides et reproductibles, sans dépendre d'un appel
réseau à Nominatim à chaque exécution — ces lat/lng correspondent au résultat
attendu du géocodage de l'adresse ; voir app/geocoding.py pour la conversion
adresse -> lat/lng réellement utilisée par l'API).
"""

import pandas as pd

# --- Agent (position de départ) --------------------------------------------
agent = {
    "id": "A1",
    "adresse": "Avenue Habib Bourguiba, Tunis, Tunisie",
    "lat": 36.8065, "lng": 10.1815,
}  # Tunis centre

# --- Patients déjà affectés à cet agent par Med.tn -------------------------
patients_data = [
    {"id": "P1", "nom": "Trabelsi", "prenom": "Amel",   "contact": "+216 20 123 456", "adresse": "Rue de Marseille, Tunis, Tunisie",   "lat": 36.8189, "lng": 10.1658, "service": "prelevement",  "urgence": 2, "duree": 20, "fenetre_horaire": None,          "statut": "en_attente"},
    {"id": "P2", "nom": "Gharbi",   "prenom": "Sami",    "contact": "+216 22 234 567", "adresse": "Avenue Mohamed V, Tunis, Tunisie",   "lat": 36.8020, "lng": 10.1900, "service": "consultation", "urgence": 1, "duree": 30, "fenetre_horaire": None,          "statut": "en_attente"},
    {"id": "P3", "nom": "Bouazizi", "prenom": "Rim",     "contact": "+216 24 345 678", "adresse": "Avenue de Paris, Tunis, Tunisie",    "lat": 36.8250, "lng": 10.1750, "service": "suivi",        "urgence": 3, "duree": 15, "fenetre_horaire": "08:00-10:00", "statut": "en_attente"},
    {"id": "P4", "nom": "Jendoubi", "prenom": "Karim",   "contact": "+216 26 456 789", "adresse": "La Marsa, Tunis, Tunisie",          "lat": 36.8663, "lng": 10.3242, "service": "consultation", "urgence": 1, "duree": 25, "fenetre_horaire": None,          "statut": "en_attente"},  # La Marsa
    {"id": "P5", "nom": "Cherif",   "prenom": "Nadia",   "contact": "+216 27 567 890", "adresse": "Ariana, Tunisie",                   "lat": 36.8622, "lng": 10.1956, "service": "prelevement",  "urgence": 2, "duree": 15, "fenetre_horaire": None,          "statut": "en_attente"},  # Ariana
    {"id": "P6", "nom": "Mabrouk",  "prenom": "Youssef", "contact": "+216 28 678 901", "adresse": "Le Bardo, Tunisie",                 "lat": 36.8093, "lng": 10.1408, "service": "suivi",        "urgence": 2, "duree": 20, "fenetre_horaire": None,          "statut": "en_attente"},  # Le Bardo
    {"id": "P7", "nom": "Ayari",    "prenom": "Salma",   "contact": "+216 29 789 012", "adresse": "Ben Arous, Tunisie",                "lat": 36.7538, "lng": 10.2270, "service": "prelevement",  "urgence": 3, "duree": 10, "fenetre_horaire": "14:00-16:00", "statut": "en_attente"},  # Ben Arous
    {"id": "P8", "nom": "Khemiri",  "prenom": "Mehdi",   "contact": "+216 21 890 123", "adresse": "Le Kram, Tunis, Tunisie",           "lat": 36.8397, "lng": 10.2350, "service": "consultation", "urgence": 1, "duree": 30, "fenetre_horaire": None,          "statut": "en_attente"},  # Le Kram
]


def charger_dataset():
    """
    Retourne (df_agent, df_patients) prêts à l'emploi.
    df_agent    : DataFrame à une seule ligne (id, adresse, lat, lng)
    df_patients : DataFrame des patients affectés à cet agent
    """
    df_agent = pd.DataFrame([agent])
    df_patients = pd.DataFrame(patients_data)
    df_patients = df_patients[[
        "id", "nom", "prenom", "contact", "adresse", "lat", "lng",
        "service", "urgence", "duree", "fenetre_horaire", "statut"
    ]]
    return df_agent, df_patients