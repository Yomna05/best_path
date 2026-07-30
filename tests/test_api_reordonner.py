"""
Tests de l'endpoint POST /api/v1/reordonner-tournee (UC4 exposé via API).
"""

import pytest
from fastapi.testclient import TestClient

from app.api import app

client = TestClient(app)


def payload_valide():
    return {
        "agent": {"id": "A1", "lat": 36.8065, "lng": 10.1815},
        "patients": [
            {"id": "P1", "lat": 36.8189, "lng": 10.1658, "service": "prelevement", "urgence": 2, "duree": 20},
            {"id": "P2", "lat": 36.8020, "lng": 10.1900, "service": "consultation", "urgence": 1, "duree": 30},
            {"id": "P3", "lat": 36.8250, "lng": 10.1750, "service": "suivi", "urgence": 3, "duree": 15},
        ],
        "tournee_initiale": ["P2", "P1", "P3"],
        "nouvel_ordre": ["P2", "P3", "P1"],
    }


# --- Tests nominaux -----------------------------------------------------------

def test_reordonner_tournee_requete_valide():
    response = client.post("/api/v1/reordonner-tournee", json=payload_valide())

    assert response.status_code == 200
    data = response.json()
    assert data["agent_id"] == "A1"
    assert data["tournee"] == ["P2", "P3", "P1"]
    assert data["tournee_initiale_proposee"] == ["P2", "P1", "P3"]
    assert data["modifiee_manuellement"] is True
    assert data["distance_totale"] >= 0


def test_reordonner_tournee_meme_ordre_est_valide():
    """Réordonner vers l'identique doit fonctionner (cas limite acceptable)."""
    payload = payload_valide()
    payload["nouvel_ordre"] = payload["tournee_initiale"][:]

    response = client.post("/api/v1/reordonner-tournee", json=payload)

    assert response.status_code == 200
    assert response.json()["tournee"] == payload["tournee_initiale"]


# --- Tests des garde-fous (UC4 : réordonner uniquement) -----------------------

def test_reordonner_tournee_refuse_suppression_patient():
    payload = payload_valide()
    payload["nouvel_ordre"] = ["P2", "P1"]  # P3 manquant

    response = client.post("/api/v1/reordonner-tournee", json=payload)

    assert response.status_code == 400
    assert "réordonner" in response.json()["detail"].lower() or "detail" in response.json()


def test_reordonner_tournee_refuse_ajout_patient():
    payload = payload_valide()
    payload["nouvel_ordre"] = ["P2", "P1", "P3", "P4"]  # P4 n'existe pas dans la tournée initiale

    response = client.post("/api/v1/reordonner-tournee", json=payload)

    assert response.status_code == 400


def test_reordonner_tournee_refuse_doublon():
    payload = payload_valide()
    payload["nouvel_ordre"] = ["P2", "P1", "P1"]  # P1 en double, P3 absent

    response = client.post("/api/v1/reordonner-tournee", json=payload)

    assert response.status_code == 400


# --- Tests de validation (structure de la requête) ----------------------------

def test_reordonner_tournee_champ_manquant_retourne_422():
    payload = payload_valide()
    del payload["tournee_initiale"]

    response = client.post("/api/v1/reordonner-tournee", json=payload)

    assert response.status_code == 422