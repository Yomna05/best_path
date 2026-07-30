"""
Tests de l'API (FastAPI) — utilise TestClient, qui simule des requêtes HTTP
sans avoir besoin de lancer réellement le serveur uvicorn.
"""

import pytest
from fastapi.testclient import TestClient

from app.api import app

client = TestClient(app)


# --- Payload de référence, réutilisé dans plusieurs tests --------------------

def payload_valide():
    return {
        "agent": {"id": "A1", "lat": 36.8065, "lng": 10.1815},
        "patients": [
            {"id": "P1", "lat": 36.8189, "lng": 10.1658, "service": "prelevement", "urgence": 2, "duree": 20},
            {"id": "P2", "lat": 36.8020, "lng": 10.1900, "service": "consultation", "urgence": 1, "duree": 30},
            {"id": "P3", "lat": 36.8250, "lng": 10.1750, "service": "suivi", "urgence": 3, "duree": 15},
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
    del payload["patients"][0]["lat"]  # on retire un champ obligatoire

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


# --- Test du point de contrôle racine -----------------------------------------

def test_racine_repond():
    response = client.get("/")

    assert response.status_code == 200
    assert "message" in response.json()