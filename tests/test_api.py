"""
Tests de l'API (FastAPI) — utilise TestClient, qui simule des requêtes HTTP
sans avoir besoin de lancer réellement le serveur uvicorn.

Le géocodage (Nominatim) est simulé (mock) : ces tests ne font aucun appel
réseau réel, pour rester rapides et reproductibles en CI. La validation
avec le vrai service Nominatim se fait manuellement (Colab/local), comme
pour les autres modules du projet.
"""

from unittest.mock import MagicMock

import pytest
from fastapi.testclient import TestClient

import app.api as api
from app.api import app

client = TestClient(app)


# --- Simulation du géocodage : adresse -> (lat, lng) connues -----------------
# Mêmes coordonnées que l'ancien jeu de test (lat/lng directs), pour garder
# des résultats de distance/priorité comparables.

_ADRESSES_CONNUES = {
    "12 Avenue Habib Bourguiba, Tunis": (36.8065, 10.1815),        # A1 (agent)
    "5 Rue de la Kasbah, Tunis": (36.8189, 10.1658),               # P1
    "8 Rue Ibn Khaldoun, Tunis": (36.8020, 10.1900),               # P2
    "3 Rue Sidi Bou Said, Tunis": (36.8250, 10.1750),              # P3
}


def _fausse_geocoder_adresse(adresse):
    if adresse in _ADRESSES_CONNUES:
        return _ADRESSES_CONNUES[adresse]
    raise ValueError(f"Adresse introuvable : '{adresse}'")


@pytest.fixture(autouse=True)
def _mock_geocodage(monkeypatch):
    """Remplace le géocodage réel par la table ci-dessus, pour tous les tests de ce fichier."""
    monkeypatch.setattr(api, "geocoder_adresse", MagicMock(side_effect=_fausse_geocoder_adresse))


# --- Payload de référence, réutilisé dans plusieurs tests --------------------

def payload_valide():
    return {
        "agent": {"id": "A1", "adresse": "12 Avenue Habib Bourguiba, Tunis"},
        "patients": [
            {"id": "P1", "adresse": "5 Rue de la Kasbah, Tunis", "service": "prelevement", "urgence": 2, "duree": 20},
            {"id": "P2", "adresse": "8 Rue Ibn Khaldoun, Tunis", "service": "consultation", "urgence": 1, "duree": 30},
            {"id": "P3", "adresse": "3 Rue Sidi Bou Said, Tunis", "service": "suivi", "urgence": 3, "duree": 15},
        ],
    }


# --- Tests nominaux -----------------------------------------------------------

def test_optimiser_tournee_requete_valide():
    response = client.post("/api/v1/optimiser-tournee", json=payload_valide())

    assert response.status_code == 200
    data = response.json()
    assert data["agent_id"] == "A1"
    assert set(data["tournee"]) == {"P1", "P2", "P3"}
    assert data["distance_totale"] >= 0
    assert data["duree_totale_min"] >= 0


def test_optimiser_tournee_sans_patients():
    payload = payload_valide()
    payload["patients"] = []

    response = client.post("/api/v1/optimiser-tournee", json=payload)

    assert response.status_code == 200
    data = response.json()
    assert data["tournee"] == []
    assert data["distance_totale"] == 0.0


def test_optimiser_tournee_priorite_stricte():
    payload = payload_valide()
    urgence_par_id = {p["id"]: p["urgence"] for p in payload["patients"]}

    response = client.post("/api/v1/optimiser-tournee", json=payload)

    assert response.status_code == 200
    data = response.json()
    urgences_ordre = [urgence_par_id[pid] for pid in data["tournee"]]
    assert urgences_ordre == sorted(urgences_ordre, reverse=True)


# --- Tests de validation (données invalides) ----------------------------------

def test_champ_manquant_retourne_422():
    payload = payload_valide()
    del payload["patients"][0]["adresse"]  # on retire le champ obligatoire

    response = client.post("/api/v1/optimiser-tournee", json=payload)

    assert response.status_code == 422


def test_adresse_vide_retourne_422():
    payload = payload_valide()
    payload["patients"][0]["adresse"] = "   "  # adresse vide/blanche

    response = client.post("/api/v1/optimiser-tournee", json=payload)

    assert response.status_code == 422


def test_urgence_hors_plage_retourne_422():
    payload = payload_valide()
    payload["patients"][0]["urgence"] = 5  # doit être entre 1 et 3

    response = client.post("/api/v1/optimiser-tournee", json=payload)

    assert response.status_code == 422


def test_urgence_type_invalide_retourne_422():
    payload = payload_valide()
    payload["patients"][0]["urgence"] = "urgent"  # doit être un entier

    response = client.post("/api/v1/optimiser-tournee", json=payload)

    assert response.status_code == 422


def test_agent_manquant_retourne_422():
    payload = payload_valide()
    del payload["agent"]

    response = client.post("/api/v1/optimiser-tournee", json=payload)

    assert response.status_code == 422


def test_adresse_introuvable_retourne_400():
    """Une adresse syntaxiquement valide mais que le géocodeur ne trouve pas
    doit être un 400 (échec métier), pas un 422 (forme de la requête)."""
    payload = payload_valide()
    payload["patients"][0]["adresse"] = "Adresse qui n'existe nulle part"

    response = client.post("/api/v1/optimiser-tournee", json=payload)

    assert response.status_code == 400


# --- Test du point de contrôle racine -----------------------------------------

def test_racine_repond():
    response = client.get("/")

    assert response.status_code == 200
    assert "message" in response.json()