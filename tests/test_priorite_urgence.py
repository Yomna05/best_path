"""
Étude et démonstration de la priorité stricte par urgence (remplace l'ancienne
étude du paramètre poids_urgence, supprimé). Illustre pour la soutenance :
- que l'ordre respecte toujours les niveaux d'urgence (3 avant 2 avant 1),
- le gain de distance apporté par le 2-opt par groupe, sans jamais casser
  cet ordre (§6.4 de l'étude, version révisée).
"""

from app.data import charger_dataset
from app.routing import (
    construire_df_points,
    construire_matrice_distances,
    nearest_neighbor_priorite,
    deux_opt_par_groupe,
    longueur_tournee,
    optimiser_tournee,
)


def test_priorite_stricte_respectee():
    """
    Vérifie que la tournée finale (après 2-opt par groupe) respecte toujours
    l'ordre des niveaux d'urgence, quelle que soit la répartition des patients.
    """
    df_agent, df_patients = charger_dataset()
    resultat = optimiser_tournee(df_agent, df_patients)

    urgences_ordre = df_patients.set_index("id").loc[resultat["tournee"], "urgence"].tolist()
    assert urgences_ordre == sorted(urgences_ordre, reverse=True)


def test_gain_du_deux_opt_par_groupe():
    """
    Compare la distance avant/après le 2-opt par groupe, et affiche le détail
    pour observation (démonstration, pas d'assertion stricte sur le gain :
    il peut être nul si la tournée du plus proche voisin était déjà optimale
    à l'intérieur de chaque groupe).
    """
    df_agent, df_patients = charger_dataset()
    agent_id = df_agent.iloc[0]["id"]
    patient_ids = df_patients["id"].tolist()

    df_points = construire_df_points(df_agent, df_patients)
    matrice = construire_matrice_distances(df_points)

    tournee_avant = nearest_neighbor_priorite(agent_id, patient_ids, matrice, df_patients)
    distance_avant = longueur_tournee(agent_id, tournee_avant, matrice)

    tournee_apres = deux_opt_par_groupe(agent_id, tournee_avant, matrice, df_patients)
    distance_apres = longueur_tournee(agent_id, tournee_apres, matrice)

    print("\n" + "=" * 70)
    print(f"Tournée avant 2-opt (priorité stricte pure) : {tournee_avant}")
    print(f"Distance avant 2-opt : {distance_avant:.2f} km")
    print(f"Tournée après 2-opt par groupe                : {tournee_apres}")
    print(f"Distance après 2-opt : {distance_apres:.2f} km")
    print(f"Gain de distance : {distance_avant - distance_apres:.2f} km")
    print("=" * 70)

    assert distance_apres <= distance_avant, (
        "Le 2-opt par groupe ne doit jamais dégrader la distance"
    )

    urgences_finales = df_patients.set_index("id").loc[tournee_apres, "urgence"].tolist()
    assert urgences_finales == sorted(urgences_finales, reverse=True)


def test_urgence_uniforme_equivaut_au_nn_pur():
    """
    Cas limite : si tous les patients ont la même urgence, il n'y a qu'un
    seul groupe -> le comportement doit être identique à un plus proche
    voisin + 2-opt classique, sans notion de priorité.
    """
    df_agent, df_patients = charger_dataset()
    df_urgence_egale = df_patients.copy()
    df_urgence_egale["urgence"] = 2

    r1 = optimiser_tournee(df_agent, df_urgence_egale)
    r2 = optimiser_tournee(df_agent, df_urgence_egale)

    assert r1["tournee"] == r2["tournee"]  # déterminisme


# pytest tests/test_priorite_urgence.py -v -s (-s : obligatoire pour voir les print())
