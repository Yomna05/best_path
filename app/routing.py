"""
Algorithmes de tournée : plus proche voisin (pondéré par urgence), 2-opt,
et assemblage final dans optimiser_tournee(). Inclut aussi
reordonner_manuellement() pour le réordonnancement manuel (UC4).
"""

from app.distance import (
    construire_df_points,
    construire_matrice_distances,
    construire_matrice_distances_osm,
)


def _construire_matrice(df_points, graphe_osm=None):
    """
    Sélectionne la source de distance à utiliser :
    - si `graphe_osm` est fourni (graphe déjà chargé via
      app.distance.charger_graphe_zone()) -> distances ROUTIÈRES RÉELLES
      (construire_matrice_distances_osm()) ;
    - sinon -> Haversine (à vol d'oiseau), comportement par défaut inchangé.

    Centralise ce choix ici pour que optimiser_tournee() et
    reordonner_manuellement() restent cohérents entre eux.
    """
    if graphe_osm is not None:
        return construire_matrice_distances_osm(df_points, graphe_osm)
    return construire_matrice_distances(df_points)


def nearest_neighbor(agent_id, patient_ids, matrice_distances):
    """
    Construit une tournée gloutonne : à chaque étape, choisit le patient
    non-visité le plus proche de la position courante.

    Retourne : liste ordonnée d'ids de patients (la tournée)
    """
    tournee = []
    position = agent_id
    restants = list(patient_ids)

    while restants:
        distances = matrice_distances.loc[position, restants]
        prochain = distances.idxmin()

        tournee.append(prochain)
        restants.remove(prochain)
        position = prochain

    return tournee


def nearest_neighbor_pondere(agent_id, patient_ids, matrice_distances, df_patients, poids_urgence=0.0):
    """
    Variante du plus proche voisin qui pondère le choix par l'urgence du patient.

    poids_urgence : 0 => équivalent au NN classique (distance pure)
                    plus grand => l'urgence prime davantage sur la distance
    """
    tournee = []
    position = agent_id
    restants = list(patient_ids)

    urgences = df_patients.set_index("id")["urgence"]

    while restants:
        distances = matrice_distances.loc[position, restants]
        couts = distances - poids_urgence * urgences.loc[restants]
        prochain = couts.idxmin()

        tournee.append(prochain)
        restants.remove(prochain)
        position = prochain

    return tournee


def nearest_neighbor_priorite(agent_id, patient_ids, matrice_distances, df_patients):
    """
    Variante du plus proche voisin à priorité stricte par urgence.

    Tous les patients d'un niveau d'urgence donné sont visités avant de passer
    au niveau d'urgence inférieur (3 -> 2 -> 1), sans compromis possible avec
    la distance. À l'intérieur d'un même niveau, le choix reste le plus proche
    voisin (distance pure) depuis la position courante.
    """
    tournee = []
    position = agent_id

    urgences = df_patients.set_index("id")["urgence"]

    # du niveau d'urgence le plus élevé au plus faible (ex. 3, puis 2, puis 1)
    niveaux = sorted(urgences.loc[patient_ids].unique(), reverse=True)

    for niveau in niveaux:
        restants_niveau = [pid for pid in patient_ids if urgences[pid] == niveau]

        while restants_niveau:
            distances = matrice_distances.loc[position, restants_niveau]
            prochain = distances.idxmin()

            tournee.append(prochain)
            restants_niveau.remove(prochain)
            position = prochain

    return tournee


def longueur_tournee(agent_id, tournee, matrice_distances):
    """Calcule la distance totale d'une tournée, en partant de l'agent."""
    position = agent_id
    total = 0.0
    for patient in tournee:
        total += matrice_distances.loc[position, patient]
        position = patient
    return total


def deux_opt(agent_id, tournee, matrice_distances):
    """
    Améliore une tournée existante par la méthode 2-opt : tente d'inverser
    des segments de la tournée et garde l'amélioration si elle réduit la
    distance totale. Répète jusqu'à stabilisation.
    """
    meilleure_tournee = tournee[:]
    amelioration = True

    while amelioration:
        amelioration = False
        n = len(meilleure_tournee)

        for i in range(n - 1):
            for j in range(i + 1, n):
                nouvelle_tournee = (
                    meilleure_tournee[:i]
                    + meilleure_tournee[i:j + 1][::-1]
                    + meilleure_tournee[j + 1:]
                )

                dist_actuelle = longueur_tournee(agent_id, meilleure_tournee, matrice_distances)
                dist_nouvelle = longueur_tournee(agent_id, nouvelle_tournee, matrice_distances)

                if dist_nouvelle < dist_actuelle:
                    meilleure_tournee = nouvelle_tournee
                    amelioration = True

    return meilleure_tournee


def deux_opt_par_groupe(agent_id, tournee, matrice_distances, df_patients):
    """
    Applique le 2-opt indépendamment à l'intérieur de chaque groupe d'urgence,
    sans jamais réorganiser un patient d'un groupe vers un autre. Préserve
    ainsi la priorité stricte tout en améliorant la distance à l'intérieur
    de chaque niveau d'urgence.

    tournee : liste déjà groupée par urgence décroissante (ex. sortie de
              nearest_neighbor_priorite())
    """
    urgences = df_patients.set_index("id")["urgence"]

    # Reconstituer les groupes contigus (la tournée est déjà triée par urgence décroissante)
    groupes = []
    groupe_courant = []
    urgence_courante = None
    for pid in tournee:
        u = urgences[pid]
        if u != urgence_courante:
            if groupe_courant:
                groupes.append(groupe_courant)
            groupe_courant = [pid]
            urgence_courante = u
        else:
            groupe_courant.append(pid)
    if groupe_courant:
        groupes.append(groupe_courant)

    tournee_finale = []
    position = agent_id
    for groupe in groupes:
        groupe_optimise = deux_opt(position, groupe, matrice_distances)
        tournee_finale.extend(groupe_optimise)
        position = groupe_optimise[-1]  # point de départ du groupe suivant

    return tournee_finale


def optimiser_tournee(df_agent, df_patients, graphe_osm=None):
    """
    Fonction principale : assemble matrice de distances, plus proche voisin
    à priorité stricte par urgence, puis 2-opt (par groupe d'urgence) pour
    produire la tournée optimisée d'un agent.

    df_agent       : DataFrame d'un seul agent avec 'id', 'lat', 'lng'
    df_patients    : DataFrame des patients affectés à cet agent
    graphe_osm     : graphe OSMnx optionnel (cf. app.distance.charger_graphe_zone()).
                      Si fourni, les distances routières réelles sont utilisées
                      à la place de Haversine — sans aucun autre changement de
                      comportement (algorithmes, contrat de sortie identiques).

    Retourne : dict conforme au contrat API (§5 de l'étude)
    """
    agent_id = df_agent.iloc[0]["id"]
    agent_lat = df_agent.iloc[0]["lat"]
    agent_lng = df_agent.iloc[0]["lng"]

    patient_ids = df_patients["id"].tolist()

    if not patient_ids:
        return {
            "agent_id": agent_id,
            "tournee": [],
            "distance_totale": 0.0,
            "duree_totale_min": 0,
            "position_finale": {"lat": agent_lat, "lng": agent_lng}
        }

    df_points = construire_df_points(df_agent, df_patients)
    matrice_distances = _construire_matrice(df_points, graphe_osm)

    tournee_initiale = nearest_neighbor_priorite(
        agent_id, patient_ids, matrice_distances, df_patients
    )
    tournee_finale = deux_opt_par_groupe(agent_id, tournee_initiale, matrice_distances, df_patients)

    distance_totale = longueur_tournee(agent_id, tournee_finale, matrice_distances)

    duree_service = df_patients.set_index("id").loc[tournee_finale, "duree"].sum()
    duree_trajet_min = (distance_totale / 30) * 60  # vitesse moyenne urbaine 30 km/h
    duree_totale_min = round(duree_service + duree_trajet_min)

    dernier_patient = df_patients.set_index("id").loc[tournee_finale[-1]]

    return {
        "agent_id": agent_id,
        "tournee": tournee_finale,
        "distance_totale": round(distance_totale, 2),
        "duree_totale_min": duree_totale_min,
        "position_finale": {"lat": dernier_patient["lat"], "lng": dernier_patient["lng"]}
    }


def reordonner_manuellement(resultat_optimisation, nouvel_ordre, df_agent, df_patients, graphe_osm=None):
    """
    Applique un réordonnancement manuel décidé par l'agent sur une tournée
    déjà proposée par optimiser_tournee() (UC4). Conserve la proposition
    initiale pour comparaison ultérieure (UC7).

    Limite stricte : réordonner uniquement, jamais ajouter/retirer un patient.

    graphe_osm : cf. optimiser_tournee() — même source de distance que celle
                 utilisée pour calculer la tournée initiale, pour que la
                 comparaison "proposé vs. réalisé" (UC7) reste cohérente.
    """
    tournee_initiale = resultat_optimisation["tournee"]

    if set(nouvel_ordre) != set(tournee_initiale):
        raise ValueError(
            "reordonner_manuellement() ne permet que de réordonner la tournée existante : "
            "impossible d'ajouter ou de retirer un patient. "
            f"Attendu : {set(tournee_initiale)}, reçu : {set(nouvel_ordre)}"
        )
    if len(nouvel_ordre) != len(set(nouvel_ordre)):
        raise ValueError("La nouvelle tournée contient un doublon.")

    agent_id = df_agent.iloc[0]["id"]
    df_points = construire_df_points(df_agent, df_patients)
    matrice_distances = _construire_matrice(df_points, graphe_osm)

    distance_totale = longueur_tournee(agent_id, nouvel_ordre, matrice_distances)
    duree_service = df_patients.set_index("id").loc[nouvel_ordre, "duree"].sum()
    duree_trajet_min = (distance_totale / 30) * 60
    duree_totale_min = round(duree_service + duree_trajet_min)
    dernier_patient = df_patients.set_index("id").loc[nouvel_ordre[-1]]

    return {
        "agent_id": agent_id,
        "tournee_initiale_proposee": tournee_initiale,
        "tournee": nouvel_ordre,
        "distance_totale": round(distance_totale, 2),
        "duree_totale_min": duree_totale_min,
        "position_finale": {"lat": dernier_patient["lat"], "lng": dernier_patient["lng"]},
        "modifiee_manuellement": True
    }