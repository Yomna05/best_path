# Microservice d'optimisation de tournées d'agents médicaux à domicile

Complément à la plateforme **Med.tn** : reçoit un agent et sa liste de
patients déjà affectés, et retourne la tournée optimisée (TSP pondéré par
urgence, heuristiques Nearest Neighbor + 2-opt).

## Architecture

```
microservice_tournee/
│
├── app/
│   ├── __init__.py
│   ├── data.py         # dataset statique (agent, patients) pour le POC
│   ├── distance.py     # haversine() + construction de la matrice de distances
│   ├── routing.py      # NN, NN pondéré, 2-opt, optimiser_tournee(), reordonner_manuellement()
│
├── main.py             # script de démonstration standalone (exécute tout le flux)
│
├── tests/
│   ├── __init__.py
│   └── test_routing.py # tests pytest (reprennent les validations du notebook)
│
├── requirements.txt
└── README.md
```

*(À venir : `api.py` pour l'exposition FastAPI, `visualization.py` pour les
cartes matplotlib/folium — étapes suivantes du projet.)*

## Installation

```bash
python -m venv venv
source venv/bin/activate        # Windows : venv\Scripts\activate
pip install -r requirements.txt
```

## Utilisation

### Lancer la démonstration complète

```bash
python main.py
```

Affiche : les données, la tournée optimisée (JSON), l'export CSV, et un
exemple de réordonnancement manuel (UC4).

### Lancer les tests

```bash
pytest tests/
```

ou, avec plus de détails :

```bash
pytest tests/ -v
```

## Notes de conception

- **Périmètre** : l'affectation patients→agent est hors périmètre (gérée par
  Med.tn). Ce microservice reçoit toujours *un agent + sa liste de patients
  déjà affectés*.
- **Stateless** : aucune persistance, chaque appel est autonome.
- **Distance** : formule de Haversine (à vol d'oiseau), pas de dépendance à
  une API externe pour ce POC.
- **Vitesse moyenne** utilisée pour convertir distance → durée de trajet :
  30 km/h (zone urbaine), codée en dur dans `optimiser_tournee()` — à rendre
  paramétrable si besoin.
