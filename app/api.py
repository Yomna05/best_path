"""
Couche microservice (API REST) — expose optimiser_tournee() via HTTP.

Contrat d'interface conforme à l'étude (§5, §7.1) :

    POST /api/v1/optimiser-tournee
    Body: {"agent": {...}, "patients": [...]}
    Response: {"agent_id": ..., "tournee": [...], "distance_totale": ..., ...}

Lancer le serveur :
    uvicorn app.api:app --reload

Puis ouvrir http://127.0.0.1:8000/docs pour la documentation interactive.
"""

import os
from contextlib import asynccontextmanager
from typing import List

import pandas as pd
from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
from pydantic import BaseModel, Field, field_validator

from app.routing import optimiser_tournee, reordonner_manuellement
from app.geocoding import geocoder_adresse
from app.distance import charger_graphe_zone


# --- Modèles Pydantic : forme exacte des données attendues/renvoyées --------
#
# L'agent et les patients sont décrits par une ADRESSE PHYSIQUE (ex. "12 Rue
# de Marseille, La Marsa"), jamais par lat/lng directement — la conversion en
# coordonnées GPS est un détail d'implémentation interne (cf. app/geocoding.py),
# transparent pour l'appelant (Med.tn).

class AgentIn(BaseModel):
    id: str
    adresse: str

    @field_validator("adresse")
    @classmethod
    def _adresse_non_vide(cls, valeur):
        if not valeur.strip():
            raise ValueError("'adresse' ne peut pas être vide.")
        return valeur


class PatientIn(BaseModel):
    id: str
    adresse: str
    service: str
    urgence: int = Field(ge=1, le=3, description="1 = faible, 3 = urgent")
    duree: int = Field(ge=0, description="Durée du service en minutes")

    @field_validator("adresse")
    @classmethod
    def _adresse_non_vide(cls, valeur):
        if not valeur.strip():
            raise ValueError("'adresse' ne peut pas être vide.")
        return valeur


def _resoudre_coordonnees(item):
    """
    Géocode l'adresse d'un AgentIn/PatientIn en (lat, lng) (cf. app/geocoding.py).

    Lève une HTTPException 400 si l'adresse n'a pas pu être géocodée (ex.
    adresse introuvable, service de géocodage indisponible) — plutôt qu'une
    422, car ce n'est pas un problème de forme de la requête mais un échec
    du traitement métier.
    """
    try:
        return geocoder_adresse(item.adresse)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


class OptimiserTourneeRequest(BaseModel):
    agent: AgentIn
    patients: List[PatientIn]


class PositionFinale(BaseModel):
    lat: float
    lng: float


class OptimiserTourneeResponse(BaseModel):
    agent_id: str
    tournee: List[str]
    distance_totale: float
    duree_totale_min: int
    position_finale: PositionFinale


# --- Application FastAPI ------------------------------------------------------
#
# Distance routière réelle (OSMnx) : DÉSACTIVÉE par défaut (Haversine utilisé
# partout, comportement historique inchangé). Pour l'activer :
#
#   $env:UTILISER_OSM="true"; uvicorn app.api:app --reload      (PowerShell)
#   UTILISER_OSM=true uvicorn app.api:app --reload               (bash)
#
# Le graphe est téléchargé UNE SEULE FOIS au démarrage du serveur (jamais par
# requête, cf. app/distance.py) et conservé en mémoire dans app.state.graphe_osm.
# Si le téléchargement échoue (pas de réseau, zone introuvable...), le service
# démarre quand même et se rabat automatiquement sur Haversine.
#
# Par défaut, la zone est un disque de rayon OSM_RAYON_M autour du point
# (OSM_CENTRE_LAT, OSM_CENTRE_LNG) — mode robuste qui ne dépend d'aucune
# frontière administrative précise (contrairement à un nom de zone comme
# "Grand Tunis", qui n'existe pas en tant qu'entité officielle dans OSM et
# fait échouer ox.graph_from_place() avec "Found no graph nodes..."). Ce
# choix reste modifiable via variables d'environnement si besoin.

UTILISER_OSM = os.getenv("UTILISER_OSM", "false").strip().lower() in ("1", "true", "yes")
OSM_CENTRE_LAT = float(os.getenv("OSM_CENTRE_LAT", "36.8065"))   # Tunis centre
OSM_CENTRE_LNG = float(os.getenv("OSM_CENTRE_LNG", "10.1815"))
OSM_RAYON_M = int(os.getenv("OSM_RAYON_M", "20000"))             # 20 km


@asynccontextmanager
async def lifespan(app: FastAPI):
    # --- Startup ---
    app.state.graphe_osm = None
    if UTILISER_OSM:
        print(
            f"[OSMnx] Chargement du graphe routier (centre={OSM_CENTRE_LAT},{OSM_CENTRE_LNG}, "
            f"rayon={OSM_RAYON_M}m)... (peut prendre plusieurs minutes)"
        )
        try:
            app.state.graphe_osm = charger_graphe_zone(
                centre=(OSM_CENTRE_LAT, OSM_CENTRE_LNG),
                rayon_metres=OSM_RAYON_M,
            )
            print("[OSMnx] Graphe chargé avec succès — distances routières réelles activées.")
        except Exception as e:
            print(f"[OSMnx] Échec du chargement du graphe ({e}) — repli sur Haversine.")
    yield
    # --- Shutdown --- (rien à nettoyer : pas de connexion persistante)


app = FastAPI(
    title="Microservice de tournée — Med.tn",
    description="Optimise l'ordre de visite d'un agent à partir de sa liste de patients déjà affectés.",
    version="1.0.0",
    lifespan=lifespan,
)

# Configuration CORS pour autoriser l'interface web
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

frontend_dir = os.path.join(os.path.dirname(os.path.dirname(__file__)), "frontend")
if os.path.exists(frontend_dir):
    app.mount("/static", StaticFiles(directory=frontend_dir), name="static")
    app.mount("/app", StaticFiles(directory=frontend_dir, html=True), name="frontend")


@app.post("/api/v1/optimiser-tournee", response_model=OptimiserTourneeResponse)
def route_optimiser_tournee(requete: OptimiserTourneeRequest, request: Request):
    """
    Reçoit un agent et sa liste de patients affectés (décrits par ADRESSE
    PHYSIQUE), retourne la tournée optimisée.

    Chaque adresse est géocodée en (lat, lng) via _resoudre_coordonnees()
    (app/geocoding.py) avant de construire les DataFrames — app/routing.py
    continue de recevoir uniquement des lat/lng, sans aucune modification
    de sa part.

    Si UTILISER_OSM=true au démarrage, les distances routières réelles
    (app.state.graphe_osm) sont utilisées à la place de Haversine.
    """
    agent_lat, agent_lng = _resoudre_coordonnees(requete.agent)
    df_agent = pd.DataFrame([{"id": requete.agent.id, "lat": agent_lat, "lng": agent_lng}])

    if requete.patients:
        lignes_patients = []
        for p in requete.patients:
            lat, lng = _resoudre_coordonnees(p)
            ligne = p.model_dump(exclude={"adresse"})
            ligne["lat"], ligne["lng"] = lat, lng
            lignes_patients.append(ligne)
        df_patients = pd.DataFrame(lignes_patients)
    else:
        # DataFrame vide mais avec les bonnes colonnes, pour rester cohérent
        # avec le cas limite déjà géré par optimiser_tournee()
        df_patients = pd.DataFrame(columns=["id", "lat", "lng", "service", "urgence", "duree"])

    graphe_osm = getattr(request.app.state, "graphe_osm", None)
    try:
        resultat = optimiser_tournee(df_agent, df_patients, graphe_osm=graphe_osm)
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))

    return resultat


@app.get("/")
def racine(request: Request):
    """Point d'entrée principal : sert l'interface web si demandée en HTML, sinon un JSON de statut."""
    accept = request.headers.get("accept", "")
    index_file = os.path.join(frontend_dir, "index.html")
    if "text/html" in accept and os.path.exists(index_file):
        return FileResponse(index_file)
    return {"message": "Microservice de tournée opérationnel. Voir /docs pour la documentation."}



class ReordonnerTourneeRequest(BaseModel):
    agent: AgentIn
    patients: List[PatientIn]
    tournee_initiale: List[str]
    nouvel_ordre: List[str]


class ReordonnerTourneeResponse(BaseModel):
    agent_id: str
    tournee_initiale_proposee: List[str]
    tournee: List[str]
    distance_totale: float
    duree_totale_min: int
    position_finale: PositionFinale
    modifiee_manuellement: bool


@app.post("/api/v1/reordonner-tournee", response_model=ReordonnerTourneeResponse)
def route_reordonner_tournee(requete: ReordonnerTourneeRequest, request: Request):
    """
    Applique un réordonnancement manuel (UC4) sur une tournée déjà proposée.
    Le microservice étant stateless, la tournée initiale doit être fournie
    par l'appelant (Med.tn), pas retrouvée depuis un état interne.

    Utilise la même source de distance (Haversine ou OSMnx selon
    UTILISER_OSM) que route_optimiser_tournee(), pour rester cohérent avec
    la tournée initialement proposée.
    """
    agent_lat, agent_lng = _resoudre_coordonnees(requete.agent)
    df_agent = pd.DataFrame([{"id": requete.agent.id, "lat": agent_lat, "lng": agent_lng}])

    lignes_patients = []
    for p in requete.patients:
        lat, lng = _resoudre_coordonnees(p)
        ligne = p.model_dump(exclude={"adresse"})
        ligne["lat"], ligne["lng"] = lat, lng
        lignes_patients.append(ligne)
    df_patients = pd.DataFrame(lignes_patients)

    resultat_optimisation_simule = {"tournee": requete.tournee_initiale}

    graphe_osm = getattr(request.app.state, "graphe_osm", None)
    try:
        resultat = reordonner_manuellement(
            resultat_optimisation_simule,
            requete.nouvel_ordre,
            df_agent,
            df_patients,
            graphe_osm=graphe_osm,
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))

    return resultat