"""
Tests de l'endpoint POST /api/v1/reordonner-tournee (UC4 exposé via API).

Le géocodage (Nominatim) est simulé (mock), comme dans test_api.py.
"""

from unittest.mock import MagicMock

import pytest
from fastapi.testclient import TestClient

import app.api as api
from app.api import app

client = TestClient(app)


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
    monkeypatch.setattr(api, "geocoder_adresse", MagicMock(side_effect=_fausse_geocoder_adresse))


def payload_valide():
    return {
        "agent": {"id": "A1", "adresse": "12 Avenue Habib Bourguiba, Tunis"},
        "patients": [
            {"id": "P1", "adresse": "5 Rue de la Kasbah, Tunis", "service": "prelevement", "urgence": 2, "duree": 20},
            {"id": "P2", "adresse": "8 Rue Ibn Khaldoun, Tunis", "service": "consultation", "urgence": 1, "duree": 30},
            {"id": "P3", "adresse": "3 Rue Sidi Bou Said, Tunis", "service": "suivi", "urgence": 3, "duree": 15},
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