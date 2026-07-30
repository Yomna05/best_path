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
