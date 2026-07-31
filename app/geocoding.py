"""
Géocodage d'adresses physiques en coordonnées GPS (lat, lng), via Nominatim
(OpenStreetMap) — cohérent avec le choix "gratuit, écosystème OSM" déjà fait
pour app/distance.py (osmnx), sans dépendre d'une clé API payante (Google
Maps Geocoding).

Permet à l'agent et aux patients d'être décrits par une adresse physique
(ex. "12 Rue de Marseille, La Marsa") plutôt que directement par lat/lng ;
la conversion se fait ici, une seule fois par adresse (cache mémoire).
"""

import time

import pandas as pd
from geopy.geocoders import Nominatim
from geopy.exc import GeocoderServiceError, GeocoderTimedOut

_geolocator = Nominatim(user_agent="microservice_tournee_medtn_poc")
_cache_adresses = {}  # adresse (str, normalisée) -> (lat, lng)
_dernier_appel = 0.0
_DELAI_MIN_SECONDES = 1.0  # politique d'usage de Nominatim (max ~1 req/s)


def _variantes_simplifiees(adresse):
    """
    Génère des versions progressivement simplifiées d'une adresse, en
    retirant le segment le plus précis (typiquement "numéro + rue") à
    chaque étape, pour ne garder à la fin que la ville/le pays.

    Ex. "5 Rue Zaouiet El Bey, Le Bardo, Tunisie" ->
        ["5 Rue Zaouiet El Bey, Le Bardo, Tunisie",
         "Le Bardo, Tunisie",
         "Tunisie"]

    Utile car de nombreuses petites rues, notamment en Tunisie, ne sont pas
    encore cartographiées avec précision dans OpenStreetMap : mieux vaut
    localiser approximativement (au niveau du quartier/de la ville) que ne
    pas localiser du tout.
    """
    segments = [s.strip() for s in adresse.split(",") if s.strip()]

    variantes = []
    for i in range(len(segments)):
        variante = ", ".join(segments[i:])
        if variante and variante not in variantes:
            variantes.append(variante)

    return variantes or [adresse.strip()]


def geocoder_adresse(adresse):
    """
    Convertit une adresse physique (ex. "12 Rue de Marseille, La Marsa,
    Tunisie") en coordonnées (lat, lng).

    - Cache mémoire : une même adresse n'est géocodée qu'une seule fois par
      exécution du service (les appels suivants sont instantanés).
    - Respecte un délai minimal entre deux appels réseau successifs, pour
      rester conforme à la politique d'usage de Nominatim.
    - Repli progressif : si l'adresse complète (rue + numéro) n'est pas
      trouvée, on retente avec des versions simplifiées (quartier/ville,
      puis pays) — cf. _variantes_simplifiees(). Le résultat le plus précis
      obtenu est retourné ; le cache est indexé sur l'adresse ORIGINALE, pas
      sur la variante qui a fini par fonctionner.

    Lève une ValueError si même la variante la plus générale (le pays) n'a
    pas pu être géocodée.
    """
    global _dernier_appel

    adresse_normalisee = adresse.strip()

    if adresse_normalisee in _cache_adresses:
        return _cache_adresses[adresse_normalisee]

    derniere_erreur = None

    for variante in _variantes_simplifiees(adresse_normalisee):
        attente = _DELAI_MIN_SECONDES - (time.time() - _dernier_appel)
        if attente > 0:
            time.sleep(attente)

        try:
            resultat = _geolocator.geocode(variante, timeout=10)
        except (GeocoderServiceError, GeocoderTimedOut) as e:
            derniere_erreur = e
            resultat = None
        finally:
            _dernier_appel = time.time()

        if resultat is not None:
            coords = (resultat.latitude, resultat.longitude)
            _cache_adresses[adresse_normalisee] = coords
            return coords

    if derniere_erreur is not None:
        raise ValueError(f"Échec du géocodage de l'adresse '{adresse}' : {derniere_erreur}")
    raise ValueError(f"Adresse introuvable, même après simplification : '{adresse}'")


def geocoder_adresses_df(df, colonne_adresse="adresse"):
    """
    Géocode chaque adresse d'un DataFrame (colonne `colonne_adresse`) et
    renseigne/complète les colonnes 'lat' et 'lng'.

    Ne géocode que les lignes où 'lat'/'lng' sont absents ou manquants —
    permet de mixer, dans un même DataFrame, des points déjà en lat/lng
    (ex. jeu de données historique) et des points fournis par adresse
    uniquement (ex. nouvelle saisie agent).

    df              : DataFrame pandas, doit contenir `colonne_adresse`
    colonne_adresse  : nom de la colonne contenant l'adresse (str)

    Retourne : une COPIE de df, avec 'lat' et 'lng' renseignés pour
    toutes les lignes.
    """
    df = df.copy()

    if "lat" not in df.columns:
        df["lat"] = None
    if "lng" not in df.columns:
        df["lng"] = None

    for idx, row in df.iterrows():
        if pd.isna(row["lat"]) or pd.isna(row["lng"]):
            lat, lng = geocoder_adresse(row[colonne_adresse])
            df.at[idx, "lat"] = lat
            df.at[idx, "lng"] = lng

    df["lat"] = df["lat"].astype(float)
    df["lng"] = df["lng"].astype(float)

    return df