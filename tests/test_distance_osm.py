"""
Tests des fonctions OSMnx de app/distance.py.

Aucun téléchargement réel de graphe OSM ici (pas d'appel à
charger_graphe_zone()) : on construit un petit graphe networkx synthétique,
au format attendu par osmnx (nœuds avec attributs x=lng, y=lat ; arêtes
avec attribut 'length' en mètres), pour valider la logique de
construire_matrice_distances_osm() et verifier_couverture_graphe() sans
dépendre du réseau — rapide et reproductible en CI.

Validation avec un vrai graphe (charger_graphe_zone("Grand Tunis, Tunisie"))
à faire manuellement en local / Colab, cf. §"Iterative cell-by-cell validation".
"""

import networkx as nx
import pandas as pd
import pytest
from unittest.mock import patch

from app.distance import (
    charger_graphe_zone,
    construire_matrice_distances_osm,
    verifier_couverture_graphe,
)


@pytest.fixture
def graphe_synthetique():
    """
    Trois nœuds alignés : A1 -- (2000 m) -- P1 -- (1500 m) -- P3
    Les coordonnées des nœuds coïncident exactement avec celles des points
    du test, pour un contrôle exact des distances attendues.
    """
    G = nx.MultiDiGraph()
    G.graph["crs"] = "epsg:4326"
    G.add_node(1, x=10.1815, y=36.8065)   # position de A1
    G.add_node(2, x=10.1658, y=36.8189)   # position de P1
    G.add_node(3, x=10.1750, y=36.8250)   # position de P3
    G.add_edge(1, 2, length=2000)
    G.add_edge(2, 1, length=2000)
    G.add_edge(2, 3, length=1500)
    G.add_edge(3, 2, length=1500)
    return G


@pytest.fixture
def df_points():
    return pd.DataFrame([
        {"id": "A1", "lat": 36.8065, "lng": 10.1815},
        {"id": "P1", "lat": 36.8189, "lng": 10.1658},
        {"id": "P3", "lat": 36.8250, "lng": 10.1750},
    ])


# --- charger_graphe_zone() : choix du mode (point robuste vs nom de lieu) --

def test_charger_graphe_zone_mode_point_est_prefere():
    """
    Si `centre` est fourni, on doit utiliser ox.graph_from_point() (mode
    robuste, ne dépend d'aucune frontière administrative) et NE JAMAIS
    appeler ox.graph_from_place().
    """
    with patch("osmnx.graph_from_point") as mock_point, patch("osmnx.graph_from_place") as mock_place:
        mock_point.return_value = "GRAPHE"

        resultat = charger_graphe_zone(centre=(36.8065, 10.1815), rayon_metres=20000)

        assert resultat == "GRAPHE"
        mock_point.assert_called_once_with((36.8065, 10.1815), dist=20000, network_type="drive")
        mock_place.assert_not_called()


def test_charger_graphe_zone_mode_lieu_si_pas_de_centre():
    """Sans `centre`, on retombe sur le mode historique par nom de lieu."""
    with patch("osmnx.graph_from_point") as mock_point, patch("osmnx.graph_from_place") as mock_place:
        mock_place.return_value = "GRAPHE"

        resultat = charger_graphe_zone(lieu="Tunis, Tunisie")

        assert resultat == "GRAPHE"
        mock_place.assert_called_once_with("Tunis, Tunisie", network_type="drive")
        mock_point.assert_not_called()


def test_construire_matrice_distances_osm_chemin_direct(graphe_synthetique, df_points):
    matrice = construire_matrice_distances_osm(df_points, graphe_synthetique)

    assert matrice.loc["A1", "P1"] == pytest.approx(2.0)
    assert matrice.loc["P1", "P3"] == pytest.approx(1.5)


def test_construire_matrice_distances_osm_chemin_indirect(graphe_synthetique, df_points):
    """A1 -> P3 n'a pas d'arête directe : doit passer par P1 (2.0 + 1.5 km)."""
    matrice = construire_matrice_distances_osm(df_points, graphe_synthetique)

    assert matrice.loc["A1", "P3"] == pytest.approx(3.5)


def test_construire_matrice_distances_osm_est_symetrique(graphe_synthetique, df_points):
    matrice = construire_matrice_distances_osm(df_points, graphe_synthetique)

    assert matrice.loc["A1", "P3"] == matrice.loc["P3", "A1"]
    assert (matrice.values.diagonal() == 0).all()


def test_construire_matrice_distances_osm_repli_haversine_si_pas_de_chemin(df_points):
    """
    Si le graphe n'a aucune arête (points non connectés), la fonction doit
    se rabattre sur haversine() pour chaque paire plutôt que planter.
    """
    G_isole = nx.MultiDiGraph()
    G_isole.graph["crs"] = "epsg:4326"
    G_isole.add_node(1, x=10.1815, y=36.8065)
    G_isole.add_node(2, x=10.1658, y=36.8189)
    G_isole.add_node(3, x=10.1750, y=36.8250)
    # Aucune arête : pas de chemin possible entre les nœuds

    df_deux_points = df_points.iloc[[0, 1]].reset_index(drop=True)
    matrice = construire_matrice_distances_osm(df_deux_points, G_isole)

    # Doit être > 0 (repli sur haversine), pas une exception
    assert matrice.loc["A1", "P1"] > 0


def test_verifier_couverture_graphe_points_sur_le_graphe(graphe_synthetique, df_points):
    """Les points coïncident exactement avec les nœuds -> aucun hors couverture."""
    hors_couverture = verifier_couverture_graphe(df_points, graphe_synthetique, seuil_metres=500)

    assert hors_couverture == []


def test_verifier_couverture_graphe_detecte_point_eloigne(graphe_synthetique):
    """Un point très éloigné de tous les nœuds du graphe doit être signalé."""
    df_avec_point_eloigne = pd.DataFrame([
        {"id": "A1", "lat": 36.8065, "lng": 10.1815},
        {"id": "P_LOIN", "lat": 10.0000, "lng": 10.0000},  # très loin du Grand Tunis
    ])

    hors_couverture = verifier_couverture_graphe(df_avec_point_eloigne, graphe_synthetique, seuil_metres=500)

    assert "P_LOIN" in hors_couverture
    assert "A1" not in hors_couverture


# --- Intégration : optimiser_tournee() utilise bien le graphe si fourni -----

def test_optimiser_tournee_utilise_le_graphe_osm_si_fourni(graphe_synthetique):
    """
    optimiser_tournee() doit utiliser construire_matrice_distances_osm()
    (et non Haversine) quand un graphe est passé en paramètre — vérifié en
    comparant la distance obtenue à la distance attendue via le graphe
    synthétique (2.0 + 1.5 = 3.5 km), différente de la distance Haversine
    à vol d'oiseau entre les mêmes points.
    """
    from app.routing import optimiser_tournee

    df_agent = pd.DataFrame([{"id": "A1", "lat": 36.8065, "lng": 10.1815}])
    df_patients = pd.DataFrame([
        {"id": "P1", "lat": 36.8189, "lng": 10.1658, "service": "consultation", "urgence": 1, "duree": 20},
        {"id": "P3", "lat": 36.8250, "lng": 10.1750, "service": "suivi", "urgence": 1, "duree": 15},
    ])

    resultat_sans_graphe = optimiser_tournee(df_agent, df_patients)  # Haversine (défaut)
    resultat_avec_graphe = optimiser_tournee(df_agent, df_patients, graphe_osm=graphe_synthetique)

    # Le graphe synthétique force un chemin A1->P1->P3 de 3.5 km pile
    assert resultat_avec_graphe["distance_totale"] == pytest.approx(3.5)
    # Cette valeur diffère de la distance Haversine par défaut (non nulle)
    assert resultat_sans_graphe["distance_totale"] != resultat_avec_graphe["distance_totale"]


def test_optimiser_tournee_sans_graphe_reste_inchange(graphe_synthetique):
    """Ne pas fournir graphe_osm doit donner exactement le même résultat qu'avant (non-régression)."""
    from app.routing import optimiser_tournee

    df_agent = pd.DataFrame([{"id": "A1", "lat": 36.8065, "lng": 10.1815}])
    df_patients = pd.DataFrame([
        {"id": "P1", "lat": 36.8189, "lng": 10.1658, "service": "consultation", "urgence": 1, "duree": 20},
    ])

    resultat_implicite = optimiser_tournee(df_agent, df_patients)
    resultat_explicite = optimiser_tournee(df_agent, df_patients, graphe_osm=None)

    assert resultat_implicite == resultat_explicite