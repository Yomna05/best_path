"""
Point d'entrée / démonstration standalone du microservice de tournée.

Exécute le flux complet : chargement des données -> optimisation ->
exemple de réordonnancement manuel (UC4).

Usage : python main.py
"""

import json

from app.data import charger_dataset
from app.routing import optimiser_tournee, reordonner_manuellement



def main():
    df_agent, df_patients = charger_dataset()

    print("=== Données chargées ===")
    print(df_agent.to_string(index=False))
    print()
    print(df_patients.to_string(index=False))
    print()

    # --- Optimisation de la tournée (priorité stricte par urgence) ---
    resultat = optimiser_tournee(df_agent, df_patients)
    print("=== Tournée optimisée ===")
    print(json.dumps(resultat, indent=2, ensure_ascii=False))
    print()

    # --- Exemple de réordonnancement manuel (UC4) ---
    nouvel_ordre = resultat["tournee"][:-2] + resultat["tournee"][-2:][::-1]
    resultat_modifie = reordonner_manuellement(resultat, nouvel_ordre, df_agent, df_patients)
    print("=== Réordonnancement manuel (UC4) ===")
    print(json.dumps(resultat_modifie, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
