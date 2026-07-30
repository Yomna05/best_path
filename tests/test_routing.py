"""
Tests unitaires (pytest) — reprennent les validations faites pas à pas
dans le notebook Colab, pour garantir la non-régression du code.

Usage : pytest tests/
"""

import pytest

from app.data import charger_dataset
from app.distance import haversine, construire_df_points, construire_matrice_distances
from app.routing import (
    nearest_neighbor,
    nearest_neighbor_priorite,
    longueur_tournee,
    deux_opt,
    deux_opt_par_groupe,
    optimiser_tournee,
    reordonner_manuellement,
)


# --- Fixtures ---------------------------------------------------------------

@pytest.fixture
def dataset():
    return charger_dataset()


# --- Étape 1 : haversine() ---------------------------------------------------

def test_haversine_meme_point():
    d = haversine(36.8065, 10.1815, 36.8065, 10.1815)
    assert abs(d - 0) < 0.001


def test_haversine_tunis_marsa():
    d = haversine(36.8065, 10.1815, 36.8782, 10.3247)
    assert 12 < d < 16


def test_haversine_tunis_ariana():
    d = haversine(36.8065, 10.1815, 36.8625, 10.1956)
    assert 6 < d < 11


def test_haversine_tunis_bardo():
    d = haversine(36.8065, 10.1815, 36.8093, 10.1408)
    assert 2 < d < 6


# --- Étape 2 : matrice de distances ------------------------------------------

def test_matrice_distances_proprietes(dataset):
    df_agent, df_patients = dataset
    df_points = construire_df_points(df_agent, df_patients)
    matrice = construire_matrice_distances(df_points)

    assert matrice.shape[0] == matrice.shape[1]
    assert matrice.shape[0] == len(df_points)
    assert (matrice.values.diagonal() == 0).all()
    assert (matrice.values == matrice.values.T).all()


# --- Étape 3 : nearest_neighbor() --------------------------------------------

def test_nearest_neighbor_couvre_tous_les_patients(dataset):
    df_agent, df_patients = dataset
    df_points = construire_df_points(df_agent, df_patients)
    matrice = construire_matrice_distances(df_points)
    patient_ids = df_patients["id"].tolist()

    tournee = nearest_neighbor("A1", patient_ids, matrice)

    assert len(tournee) == len(patient_ids)
    assert set(tournee) == set(patient_ids)
    assert len(set(tournee)) == len(tournee)


# --- Étape 4 : priorité stricte par urgence -----------------------------------

def test_nearest_neighbor_priorite_respecte_les_niveaux(dataset):
    df_agent, df_patients = dataset
    df_points = construire_df_points(df_agent, df_patients)
    matrice = construire_matrice_distances(df_points)
    patient_ids = df_patients["id"].tolist()

    tournee = nearest_neighbor_priorite("A1", patient_ids, matrice, df_patients)

    assert set(tournee) == set(patient_ids)
    assert len(set(tournee)) == len(tournee)

    urgences_ordre = df_patients.set_index("id").loc[tournee, "urgence"].tolist()
    assert urgences_ordre == sorted(urgences_ordre, reverse=True)


def test_nearest_neighbor_priorite_urgence_uniforme_equivaut_a_nn(dataset):
    df_agent, df_patients = dataset
    df_points = construire_df_points(df_agent, df_patients)
    matrice = construire_matrice_distances(df_points)
    patient_ids = df_patients["id"].tolist()

    df_urgence_egale = df_patients.copy()
    df_urgence_egale["urgence"] = 2

    tournee = nearest_neighbor("A1", patient_ids, matrice)
    tournee_priorite = nearest_neighbor_priorite("A1", patient_ids, matrice, df_urgence_egale)

    assert tournee_priorite == tournee


# --- Étape 5 : 2-opt ----------------------------------------------------------

def test_deux_opt_ne_degrade_jamais(dataset):
    df_agent, df_patients = dataset
    df_points = construire_df_points(df_agent, df_patients)
    matrice = construire_matrice_distances(df_points)
    patient_ids = df_patients["id"].tolist()

    tournee = nearest_neighbor("A1", patient_ids, matrice)
    dist_nn = longueur_tournee("A1", tournee, matrice)

    tournee_2opt = deux_opt("A1", tournee, matrice)
    dist_2opt = longueur_tournee("A1", tournee_2opt, matrice)

    assert set(tournee_2opt) == set(tournee)
    assert len(set(tournee_2opt)) == len(tournee_2opt)
    assert dist_2opt <= dist_nn + 1e-9


# --- Étape 6 : optimiser_tournee() -------------------------------------------

def test_optimiser_tournee_contrat_de_sortie(dataset):
    df_agent, df_patients = dataset
    resultat = optimiser_tournee(df_agent, df_patients)

    assert resultat["agent_id"] == df_agent["id"].iloc[0]
    assert set(resultat["tournee"]) == set(df_patients["id"].tolist())
    assert resultat["distance_totale"] >= 0
    assert resultat["duree_totale_min"] >= 0

    urgences_ordre = df_patients.set_index("id").loc[resultat["tournee"], "urgence"].tolist()
    assert urgences_ordre == sorted(urgences_ordre, reverse=True), (
        "Le 2-opt par groupe ne doit jamais casser la priorité stricte"
    )


def test_optimiser_tournee_cas_limite_zero_patient(dataset):
    df_agent, df_patients = dataset
    df_vide = df_patients.iloc[0:0]

    resultat = optimiser_tournee(df_agent, df_vide)

    assert resultat["tournee"] == []
    assert resultat["distance_totale"] == 0.0


def test_optimiser_tournee_cas_limite_un_patient(dataset):
    df_agent, df_patients = dataset
    df_un = df_patients.iloc[[0]]

    resultat = optimiser_tournee(df_agent, df_un)

    assert resultat["tournee"] == ["P1"]
    assert resultat["distance_totale"] > 0


def test_optimiser_tournee_urgence_uniforme_deterministe(dataset):
    df_agent, df_patients = dataset
    df_urgence_egale = df_patients.copy()
    df_urgence_egale["urgence"] = 2

    r1 = optimiser_tournee(df_agent, df_urgence_egale)
    r2 = optimiser_tournee(df_agent, df_urgence_egale)

    assert r1["tournee"] == r2["tournee"]


def test_optimiser_tournee_patients_extremes_grande_distance(dataset):
    df_agent, df_patients = dataset
    df_extremes = df_patients[df_patients["id"].isin(["P4", "P7"])]

    resultat = optimiser_tournee(df_agent, df_extremes)

    assert resultat["distance_totale"] > 10


# --- Étape 7 : reordonner_manuellement() (UC4) -------------------------------

def test_reordonner_manuellement_applique_le_nouvel_ordre(dataset):
    df_agent, df_patients = dataset
    resultat = optimiser_tournee(df_agent, df_patients)

    nouvel_ordre = resultat["tournee"][:-2] + resultat["tournee"][-2:][::-1]
    resultat_modifie = reordonner_manuellement(resultat, nouvel_ordre, df_agent, df_patients)

    assert resultat_modifie["tournee"] == nouvel_ordre
    assert resultat_modifie["tournee_initiale_proposee"] == resultat["tournee"]
    assert resultat_modifie["modifiee_manuellement"] is True


def test_reordonner_manuellement_refuse_suppression_patient(dataset):
    df_agent, df_patients = dataset
    resultat = optimiser_tournee(df_agent, df_patients)

    ordre_invalide = resultat["tournee"][:-1]  # un patient manquant

    with pytest.raises(ValueError):
        reordonner_manuellement(resultat, ordre_invalide, df_agent, df_patients)
