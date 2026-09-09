"""
Tests de l'endpoint UC6 : POST /api/v1/evenements-tournee et
GET /api/v1/evenements-tournee/{agent_id}.

Aucun appel réseau (pas de géocodage impliqué ici, contrairement à
optimiser-tournee/reordonner-tournee) — ces tests valident uniquement le
stockage en mémoire et la validation Pydantic.
"""

import pytest
from fastapi.testclient import TestClient

import app.api as api
from app.api import app

client = TestClient(app)


@pytest.fixture(autouse=True)
def _vider_evenements():
    """Évite qu'un test pollue le stockage en mémoire d'un autre test."""
    api._evenements_tournee.clear()
    yield
    api._evenements_tournee.clear()


def evenement_valide(**overrides):
    base = {
        "agent_id": "A1",
        "patient_id": "P1",
        "type_evenement": "arrivee",
        "horodatage": "2026-09-08T10:15:00",
    }
    base.update(overrides)
    return base


# --- Tests nominaux -----------------------------------------------------------

def test_enregistrer_evenement_requete_valide():
    response = client.post("/api/v1/evenements-tournee", json=evenement_valide())

    assert response.status_code == 201
    data = response.json()
    assert data["nombre_evenements_agent"] == 1


def test_enregistrer_evenement_avec_position():
    payload = evenement_valide(position={"lat": 36.8189, "lng": 10.1658})

    response = client.post("/api/v1/evenements-tournee", json=payload)

    assert response.status_code == 201


def test_enregistrer_evenement_sans_position_est_optionnel():
    payload = evenement_valide()
    assert "position" not in payload  # confirme que le champ est bien absent du payload

    response = client.post("/api/v1/evenements-tournee", json=payload)

    assert response.status_code == 201


def test_compteur_evenements_par_agent_s_incremente():
    client.post("/api/v1/evenements-tournee", json=evenement_valide(type_evenement="depart"))
    client.post("/api/v1/evenements-tournee", json=evenement_valide(type_evenement="en_route"))
    response = client.post("/api/v1/evenements-tournee", json=evenement_valide(type_evenement="arrivee"))

    assert response.json()["nombre_evenements_agent"] == 3


def test_compteur_evenements_isole_par_agent():
    client.post("/api/v1/evenements-tournee", json=evenement_valide(agent_id="A1"))
    response = client.post("/api/v1/evenements-tournee", json=evenement_valide(agent_id="A2"))

    assert response.json()["nombre_evenements_agent"] == 1  # A2 n'a que son propre événement


# --- Tests de lecture (GET) ----------------------------------------------------

def test_lister_evenements_retourne_dans_l_ordre_de_reception():
    client.post("/api/v1/evenements-tournee", json=evenement_valide(type_evenement="depart", horodatage="2026-09-08T10:00:00"))
    client.post("/api/v1/evenements-tournee", json=evenement_valide(type_evenement="arrivee", horodatage="2026-09-08T10:15:00"))

    response = client.get("/api/v1/evenements-tournee/A1")

    assert response.status_code == 200
    data = response.json()
    assert len(data) == 2
    assert data[0]["type_evenement"] == "depart"
    assert data[1]["type_evenement"] == "arrivee"


def test_lister_evenements_agent_inconnu_retourne_liste_vide():
    response = client.get("/api/v1/evenements-tournee/AGENT_INEXISTANT")

    assert response.status_code == 200
    assert response.json() == []


def test_lister_evenements_ne_melange_pas_les_agents():
    client.post("/api/v1/evenements-tournee", json=evenement_valide(agent_id="A1", patient_id="P1"))
    client.post("/api/v1/evenements-tournee", json=evenement_valide(agent_id="A2", patient_id="P9"))

    response = client.get("/api/v1/evenements-tournee/A1")

    data = response.json()
    assert len(data) == 1
    assert data[0]["patient_id"] == "P1"


# --- Tests de validation (structure de la requête) ----------------------------

def test_type_evenement_invalide_retourne_422():
    payload = evenement_valide(type_evenement="pause_dejeuner")  # hors des 4 valeurs autorisées

    response = client.post("/api/v1/evenements-tournee", json=payload)

    assert response.status_code == 422


def test_horodatage_manquant_retourne_422():
    payload = evenement_valide()
    del payload["horodatage"]

    response = client.post("/api/v1/evenements-tournee", json=payload)

    assert response.status_code == 422


def test_horodatage_mal_forme_retourne_422():
    payload = evenement_valide(horodatage="pas une date")

    response = client.post("/api/v1/evenements-tournee", json=payload)

    assert response.status_code == 422


def test_agent_id_manquant_retourne_422():
    payload = evenement_valide()
    del payload["agent_id"]

    response = client.post("/api/v1/evenements-tournee", json=payload)

    assert response.status_code == 422


def test_position_incomplete_retourne_422():
    payload = evenement_valide(position={"lat": 36.8189})  # lng manquant

    response = client.post("/api/v1/evenements-tournee", json=payload)

    assert response.status_code == 422