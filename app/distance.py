"""
Calcul de distances géographiques (formule de Haversine) et construction
de la matrice de distances entre l'agent et ses patients affectés.
"""

import math
import pandas as pd


def haversine(lat1, lng1, lat2, lng2):
    """
    Calcule la distance à vol d'oiseau (en km) entre deux points GPS,
    en tenant compte de la courbure de la Terre.
    """
    R = 6371  # rayon moyen de la Terre en km

    phi1, phi2 = math.radians(lat1), math.radians(lat2)
    d_phi = math.radians(lat2 - lat1)
    d_lambda = math.radians(lng2 - lng1)

    a = (math.sin(d_phi / 2) ** 2
         + math.cos(phi1) * math.cos(phi2) * math.sin(d_lambda / 2) ** 2)
    c = 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))

    return R * c


def construire_df_points(df_agent, df_patients):
    """
    Fusionne l'agent et les patients dans un seul DataFrame de points,
    avec un id, une lat, une lng — base commune pour construire la matrice.

    df_agent : DataFrame à une seule ligne (id, lat, lng)
    """
    df_pts = pd.concat([
        df_agent,
        df_patients[["id", "lat", "lng"]]
    ], ignore_index=True)

    return df_pts


def construire_matrice_distances(df_points):
    """
    Construit une matrice de distances (DataFrame n x n) entre tous les points,
    indexée et colonnée par 'id'. matrice.loc[id1, id2] = distance en km.
    """
    ids = df_points["id"].tolist()
    n = len(ids)

    matrice = pd.DataFrame(0.0, index=ids, columns=ids)

    for i in range(n):
        for j in range(i + 1, n):
            lat1, lng1 = df_points.loc[i, "lat"], df_points.loc[i, "lng"]
            lat2, lng2 = df_points.loc[j, "lat"], df_points.loc[j, "lng"]
            d = haversine(lat1, lng1, lat2, lng2)
            matrice.loc[ids[i], ids[j]] = d
            matrice.loc[ids[j], ids[i]] = d  # symétrique

    return matrice


# ---------------------------------------------------------------------------
# Intégration OSMnx : distances routières réelles (alternative à Haversine)
# ---------------------------------------------------------------------------
#
# Import différé (à l'intérieur des fonctions) : osmnx n'est nécessaire que
# si l'appelant choisit explicitement cette option, et son import est plus
# lourd (dépendances réseau/scipy) que le reste du module.

def charger_graphe_zone(lieu="Grand Tunis, Tunisie", reseau_type="drive", centre=None, rayon_metres=20000):
    """
    Télécharge le graphe routier OpenStreetMap d'une zone donnée, via osmnx.

    Deux modes possibles :
    - Si `centre` est fourni (tuple (lat, lng)) : télécharge un disque de
      rayon `rayon_metres` autour de ce point (ox.graph_from_point). C'est
      le mode RECOMMANDÉ ET PAR DÉFAUT en pratique (cf. app/api.py) : il ne
      dépend d'aucune frontière administrative précise, contrairement au
      mode par nom ci-dessous.
    - Sinon, utilise `lieu` (ox.graph_from_place) : ne fonctionne QUE si
      `lieu` correspond à une frontière administrative exacte connue de
      Nominatim/OSM. "Grand Tunis" n'en est PAS une (c'est un nom d'usage,
      pas une entité administrative) : graph_from_place échoue alors avec
      "Found no graph nodes within the requested polygon." Préférer un nom
      officiel (ex. "Tunis, Tunisie" seul) ou, mieux, le mode par point.

    IMPORTANT : cette fonction fait un appel réseau (Overpass API) et peut
    prendre plusieurs secondes à plusieurs minutes selon la taille de la
    zone. Elle doit être appelée UNE SEULE FOIS (ex. au démarrage du
    microservice), jamais à chaque requête — le graphe obtenu doit ensuite
    être passé en paramètre aux fonctions qui en ont besoin
    (construire_matrice_distances_osm, verifier_couverture_graphe).

    lieu          : nom de zone reconnu par Nominatim (utilisé seulement si
                    `centre` est None)
    reseau_type   : "drive", "walk", "bike"... (cf. documentation osmnx)
    centre        : tuple (lat, lng) optionnel — centre du disque à couvrir
    rayon_metres  : rayon du disque en mètres (par défaut 20 km, suffisant
                    pour couvrir Tunis, La Marsa, Ariana, Le Bardo, Le Kram
                    et Ben Arous depuis le centre de Tunis)

    Retourne : graphe networkx/osmnx (à conserver en mémoire côté appelant)
    """
    import osmnx as ox

    if centre is not None:
        return ox.graph_from_point(centre, dist=rayon_metres, network_type=reseau_type)
    return ox.graph_from_place(lieu, network_type=reseau_type)


def construire_matrice_distances_osm(df_points, G):
    """
    Construit une matrice de distances (DataFrame n x n, en km) entre tous
    les points, en utilisant les distances ROUTIÈRES RÉELLES du graphe OSM
    `G` (plus court chemin), au lieu de la distance Haversine à vol d'oiseau.

    df_points : DataFrame avec 'id', 'lat', 'lng' (cf. construire_df_points())
    G         : graphe déjà chargé via charger_graphe_zone() — jamais
                téléchargé ici, pour éviter un appel réseau par requête.

    Retourne : DataFrame indexé/colonné par 'id', matrice.loc[id1, id2] =
               distance routière en km (mêmes forme et unité que
               construire_matrice_distances(), donc compatible avec
               nearest_neighbor_priorite(), deux_opt_par_groupe(), etc.
               sans aucune modification de app/routing.py).

    Repli (fallback) : si aucun chemin routier n'existe entre deux points
    dans le graphe (zones mal connectées), on se rabat sur haversine()
    pour cette seule paire plutôt que de faire échouer tout le calcul.
    """
    import networkx as nx
    import osmnx as ox

    ids = df_points["id"].tolist()
    n = len(ids)

    # Nœud du graphe le plus proche de chaque point, calculé une seule fois
    noeuds = {}
    for i in range(n):
        lat, lng = df_points.loc[i, "lat"], df_points.loc[i, "lng"]
        noeuds[ids[i]] = ox.distance.nearest_nodes(G, X=lng, Y=lat)

    matrice = pd.DataFrame(0.0, index=ids, columns=ids)

    for i in range(n):
        for j in range(i + 1, n):
            id1, id2 = ids[i], ids[j]
            try:
                longueur_m = nx.shortest_path_length(
                    G, noeuds[id1], noeuds[id2], weight="length"
                )
                d = longueur_m / 1000  # mètres -> km
            except nx.NetworkXNoPath:
                lat1, lng1 = df_points.loc[i, "lat"], df_points.loc[i, "lng"]
                lat2, lng2 = df_points.loc[j, "lat"], df_points.loc[j, "lng"]
                d = haversine(lat1, lng1, lat2, lng2)

            matrice.loc[id1, id2] = d
            matrice.loc[id2, id1] = d

    return matrice


def verifier_couverture_graphe(df_points, G, seuil_metres=500):
    """
    Vérifie que chaque point (agent/patient) est raisonnablement proche
    d'une rue du graphe OSM `G` (par défaut, moins de 500 m) — utile pour
    détecter un point hors de la zone couverte par charger_graphe_zone()
    AVANT de lancer l'optimisation avec construire_matrice_distances_osm().

    Retourne : liste des ids dont le point est plus éloigné que
    `seuil_metres` du nœud le plus proche du graphe (liste vide = tout
    est couvert).

    Attention à l'unité : nearest_nodes() renvoie un nœud, pas une
    distance ; on recalcule ici la distance via haversine(), qui renvoie
    des km — d'où la conversion explicite `* 1000` pour comparer à
    `seuil_metres` (un bug d'unité silencieux a été repéré ici lors des
    tests, cf. notes de conception du projet).
    """
    import osmnx as ox

    hors_couverture = []
    for _, row in df_points.iterrows():
        noeud_id = ox.distance.nearest_nodes(G, X=row["lng"], Y=row["lat"])
        noeud_lat = G.nodes[noeud_id]["y"]
        noeud_lng = G.nodes[noeud_id]["x"]

        distance_km = haversine(row["lat"], row["lng"], noeud_lat, noeud_lng)
        distance_m = distance_km * 1000  # km -> m

        if distance_m > seuil_metres:
            hors_couverture.append(row["id"])

    return hors_couverture