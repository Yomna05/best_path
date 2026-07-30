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
from typing import List

import pandas as pd
from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
from pydantic import BaseModel, Field

from app.routing import optimiser_tournee, reordonner_manuellement


# --- Modèles Pydantic : forme exacte des données attendues/renvoyées --------

class AgentIn(BaseModel):
    id: str
    lat: float
    lng: float


class PatientIn(BaseModel):
    id: str
    lat: float
    lng: float
    service: str
    urgence: int = Field(ge=1, le=3, description="1 = faible, 3 = urgent")
    duree: int = Field(ge=0, description="Durée du service en minutes")


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

app = FastAPI(
    title="Microservice de tournée — Med.tn",
    description="Optimise l'ordre de visite d'un agent à partir de sa liste de patients déjà affectés.",
    version="1.0.0",
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
def route_optimiser_tournee(requete: OptimiserTourneeRequest):
    """
    Reçoit un agent et sa liste de patients affectés, retourne la tournée optimisée.
    """
    df_agent = pd.DataFrame([requete.agent.model_dump()])

    if requete.patients:
        df_patients = pd.DataFrame([p.model_dump() for p in requete.patients])
    else:
        # DataFrame vide mais avec les bonnes colonnes, pour rester cohérent
        # avec le cas limite déjà géré par optimiser_tournee()
        df_patients = pd.DataFrame(columns=["id", "lat", "lng", "service", "urgence", "duree"])

    try:
        resultat = optimiser_tournee(df_agent, df_patients)
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
def route_reordonner_tournee(requete: ReordonnerTourneeRequest):
    """
    Applique un réordonnancement manuel (UC4) sur une tournée déjà proposée.
    Le microservice étant stateless, la tournée initiale doit être fournie
    par l'appelant (Med.tn), pas retrouvée depuis un état interne.
    """
    df_agent = pd.DataFrame([requete.agent.model_dump()])
    df_patients = pd.DataFrame([p.model_dump() for p in requete.patients])

    resultat_optimisation_simule = {"tournee": requete.tournee_initiale}

    try:
        resultat = reordonner_manuellement(
            resultat_optimisation_simule,
            requete.nouvel_ordre,
            df_agent,
            df_patients,
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))

    return resultat