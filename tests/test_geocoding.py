"""
Tests du module de géocodage (app/geocoding.py).

Nominatim est simulé (mock) : ces tests ne font aucun appel réseau réel,
pour rester rapides et reproductibles en CI. La validation avec le vrai
service Nominatim se fait manuellement (cf. §"Iterative cell-by-cell
validation" — comme pour les autres modules, d'abord en Colab).
"""

from unittest.mock import MagicMock, patch

import pandas as pd
import pytest

import app.geocoding as geocoding


@pytest.fixture(autouse=True)
def _vider_cache():
    """Évite qu'un test pollue le cache mémoire d'un autre test."""
    geocoding._cache_adresses.clear()
    yield
    geocoding._cache_adresses.clear()


def _mock_geocode(reponses):
    def _fake(adresse, timeout=10):
        return reponses.get(adresse)
    return _fake


def test_geocoder_adresse_retourne_lat_lng():
    reponses = {
        "Avenue Habib Bourguiba, Tunis": MagicMock(latitude=36.8000, longitude=10.1800)
    }
    with patch.object(geocoding._geolocator, "geocode", side_effect=_mock_geocode(reponses)):
        lat, lng = geocoding.geocoder_adresse("Avenue Habib Bourguiba, Tunis")

    assert lat == 36.8000
    assert lng == 10.1800


def test_geocoder_adresse_utilise_le_cache():
    """Le deuxième appel à la même adresse ne doit PAS retoucher Nominatim."""
    reponses = {
        "Rue de Marseille, La Marsa": MagicMock(latitude=36.8782, longitude=10.3247)
    }
    mock_geocode = MagicMock(side_effect=_mock_geocode(reponses))
    with patch.object(geocoding._geolocator, "geocode", mock_geocode):
        geocoding.geocoder_adresse("Rue de Marseille, La Marsa")
        geocoding.geocoder_adresse("Rue de Marseille, La Marsa")

    assert mock_geocode.call_count == 1


def test_geocoder_adresse_introuvable_leve_value_error():
    with patch.object(geocoding._geolocator, "geocode", side_effect=_mock_geocode({})):
        with pytest.raises(ValueError):
            geocoding.geocoder_adresse("Adresse qui n'existe pas du tout")


def test_geocoder_adresse_replie_sur_version_simplifiee():
    """
    Si l'adresse complète (rue + numéro) échoue mais qu'une version
    simplifiée (quartier/ville) est connue, geocoder_adresse() doit s'y
    replier plutôt que d'échouer.
    """
    reponses = {
        "Le Bardo, Tunisie": MagicMock(latitude=36.8093, longitude=10.1408)
        # Note : "5 Rue Zaouiet El Bey, Le Bardo, Tunisie" n'est PAS dans la table
    }
    with patch.object(geocoding._geolocator, "geocode", side_effect=_mock_geocode(reponses)):
        lat, lng = geocoding.geocoder_adresse("5 Rue Zaouiet El Bey, Le Bardo, Tunisie")

    assert lat == 36.8093
    assert lng == 10.1408
    # Le cache doit être indexé sur l'adresse ORIGINALE, pas la variante
    assert "5 Rue Zaouiet El Bey, Le Bardo, Tunisie" in geocoding._cache_adresses


def test_geocoder_adresse_echoue_meme_apres_simplification():
    with patch.object(geocoding._geolocator, "geocode", side_effect=_mock_geocode({})):
        with pytest.raises(ValueError):
            geocoding.geocoder_adresse("Rue Bidon, Ville Bidon, Planète Bidon")


def test_geocoder_adresses_df_ne_recalcule_pas_les_coordonnees_connues():
    reponses = {
        "Avenue Habib Bourguiba, Tunis": MagicMock(latitude=36.8000, longitude=10.1800)
    }
    df = pd.DataFrame([
        {"id": "A1", "adresse": "Avenue Habib Bourguiba, Tunis"},
        {"id": "P1", "adresse": "Adresse jamais appelée", "lat": 1.23, "lng": 4.56},
    ])

    with patch.object(geocoding._geolocator, "geocode", side_effect=_mock_geocode(reponses)):
        df_resultat = geocoding.geocoder_adresses_df(df)

    assert df_resultat.loc[df_resultat["id"] == "A1", "lat"].iloc[0] == 36.8000
    assert df_resultat.loc[df_resultat["id"] == "P1", "lat"].iloc[0] == 1.23  # inchangé
    assert df_resultat.loc[df_resultat["id"] == "P1", "lng"].iloc[0] == 4.56  # inchangé