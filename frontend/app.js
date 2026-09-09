/**
 * Med.tn — Microservice Tournée Web Frontend Application
 *
 * Note de conception (UC3) : l'agent CONSULTE la liste de patients qui lui a
 * été affectée par Med.tn et peut uniquement en RÉORDONNER l'ordre de visite
 * (UC4). Il ne peut ni ajouter ni supprimer un patient depuis cette
 * interface — cette décision relève de l'affectation, gérée exclusivement
 * par la plateforme Med.tn (hors périmètre de ce microservice).
 *
 * Note de conception (UC6) : le suivi temps réel (statut "à venir" / "en
 * route" / "arrivé" / "terminé" de chaque étape) est piloté par l'agent via
 * les boutons d'action de chaque carte patient. Chaque changement de statut
 * envoie un événement horodaté à POST /api/v1/evenements-tournee — c'est ce
 * flux d'événements qui fait à la fois office de UC5 ("marquer comme
 * terminé") et de UC6 (traçabilité temps réel), sans duplication de logique.
 */

const API_BASE_URL = window.location.origin;

// Durée fixe de visite par patient (minutes), remplace l'ancien champ variable
const VISIT_DURATION_MIN = 10;

// Vitesse moyenne urbaine utilisée pour convertir distance -> temps de trajet
// (doit rester cohérente avec app/routing.py : distance_km / 30 * 60)
const VITESSE_MOYENNE_KMH = 30;

// Jeu de patients affectés par Med.tn à cet agent (correspond à app/data.py,
// durée désormais fixée à 10 min pour tous)
const DEFAULT_PATIENTS = [
  { id: "P1", nom: "Trabelsi", prenom: "Amel", contact: "+216 20 123 456", adresse: "Rue de Marseille, Tunis, Tunisie", lat: 36.8189, lng: 10.1658, service: "prelevement", urgence: 2, duree: VISIT_DURATION_MIN },
  { id: "P2", nom: "Gharbi", prenom: "Sami", contact: "+216 22 234 567", adresse: "Avenue Mohamed V, Tunis, Tunisie", lat: 36.8020, lng: 10.1900, service: "consultation", urgence: 1, duree: VISIT_DURATION_MIN },
  { id: "P3", nom: "Bouazizi", prenom: "Rim", contact: "+216 24 345 678", adresse: "Avenue de Paris, Tunis, Tunisie", lat: 36.8250, lng: 10.1750, service: "suivi", urgence: 3, duree: VISIT_DURATION_MIN },
  { id: "P4", nom: "Jendoubi", prenom: "Karim", contact: "+216 26 456 789", adresse: "La Marsa, Tunis, Tunisie", lat: 36.8663, lng: 10.3242, service: "consultation", urgence: 1, duree: VISIT_DURATION_MIN },
  { id: "P5", nom: "Cherif", prenom: "Nadia", contact: "+216 27 567 890", adresse: "Ariana, Tunisie", lat: 36.8622, lng: 10.1956, service: "prelevement", urgence: 2, duree: VISIT_DURATION_MIN },
  { id: "P6", nom: "Mabrouk", prenom: "Youssef", contact: "+216 28 678 901", adresse: "Le Bardo, Tunisie", lat: 36.8093, lng: 10.1408, service: "suivi", urgence: 2, duree: VISIT_DURATION_MIN },
  { id: "P7", nom: "Ayari", prenom: "Salma", contact: "+216 29 789 012", adresse: "Ben Arous, Tunisie", lat: 36.7538, lng: 10.2270, service: "prelevement", urgence: 3, duree: VISIT_DURATION_MIN },
  { id: "P8", nom: "Khemiri", prenom: "Mehdi", contact: "+216 21 890 123", adresse: "Le Kram, Tunis, Tunisie", lat: 36.8397, lng: 10.2350, service: "consultation", urgence: 1, duree: VISIT_DURATION_MIN }
];

/**
 * Trie un tableau de patients par urgence décroissante (3→2→1),
 * puis alphabétiquement par nom pour un ordre stable et prévisible.
 * Utilisé à l'initialisation et au reset pour que la liste reflète les
 * priorités avant même le lancement de l'optimisation.
 */
function trierPatients(patients) {
  return [...patients].sort((a, b) => {
    if (b.urgence !== a.urgence) return b.urgence - a.urgence; // 3 en premier
    return (a.nom || '').localeCompare(b.nom || '', 'fr');     // alpha par nom
  });
}

// App State
let state = {
  agent: {
    id: "A1",
    adresse: "Avenue Habib Bourguiba, Tunis, Tunisie",
    lat: 36.8065,
    lng: 10.1815
  },
  patients: trierPatients(DEFAULT_PATIENTS), // tri initial par urgence
  lastOptimization: null,   // dernière réponse API (contient "tournee" courante)
  tourneeInitialeProposee: null, // tournée proposée par optimiser-tournee, conservée pour comparaison (UC7)
  suiviStatuts: {},         // { patientId: "a_venir" | "en_route" | "arrivee" | "termine" }, cf. UC6
  draggedIndex: null
};

// Map & Layer references
let map = null;
let markersGroup = null;
let routePolyline = null;

// Initialize on DOM ready
document.addEventListener("DOMContentLoaded", () => {
  initMap();
  bindEvents();
  renderPatients();
  checkApiHealth();
});

/* --------------------------------------------------------------------------
   Event Listeners Binding
   -------------------------------------------------------------------------- */
function bindEvents() {
  // 1. Button Optimiser
  const btnOptimiser = document.getElementById("btn-optimiser");
  if (btnOptimiser) {
    btnOptimiser.addEventListener("click", runOptimization);
  }

  // 2. Button Par defaut (Reset ordre patients — ne modifie jamais la
  //    composition de la liste, uniquement son tri/état d'optimisation et
  //    de suivi)
  const btnReset = document.getElementById("btn-reset-patients");
  if (btnReset) {
    btnReset.addEventListener("click", () => {
      state.patients = trierPatients(DEFAULT_PATIENTS); // reset + retri
      state.suiviStatuts = {};
      state.lastOptimization = null;
      state.tourneeInitialeProposee = null;
      renderPatients();
      if (routePolyline) {
        map.removeLayer(routePolyline);
        routePolyline = null;
      }
      const dureeElem = document.getElementById("res-duree");
      if (dureeElem) dureeElem.textContent = "--";
      const heureFinElem = document.getElementById("res-heure-fin");
      if (heureFinElem) heureFinElem.textContent = "--:--";
      const reorderHint = document.getElementById("reorder-hint");
      if (reorderHint) reorderHint.style.display = "none";
      const suiviHint = document.getElementById("suivi-hint");
      if (suiviHint) suiviHint.style.display = "none";
    });
  }

  // 3. Heure debut change handler
  const heureDebutInput = document.getElementById("heure-debut");
  if (heureDebutInput) {
    heureDebutInput.addEventListener("change", () => {
      if (state.lastOptimization) {
        displayOptimizationResults(state.lastOptimization);
      }
    });
  }
}


/* --------------------------------------------------------------------------
   Calcul des horaires (distance haversine + vitesse moyenne + visite fixe)
   -------------------------------------------------------------------------- */
function haversineKm(lat1, lng1, lat2, lng2) {
  const R = 6371;
  const toRad = (deg) => (deg * Math.PI) / 180;
  const phi1 = toRad(lat1);
  const phi2 = toRad(lat2);
  const dPhi = toRad(lat2 - lat1);
  const dLambda = toRad(lng2 - lng1);

  const a = Math.sin(dPhi / 2) ** 2 + Math.cos(phi1) * Math.cos(phi2) * Math.sin(dLambda / 2) ** 2;
  const c = 2 * Math.atan2(Math.sqrt(a), Math.sqrt(1 - a));
  return R * c;
}

function parseHeureDebutEnMinutes() {
  const val = document.getElementById("heure-debut").value || "10:00";
  const [h, m] = val.split(":").map(Number);
  return h * 60 + m;
}

function minutesEnHeure(totalMinutes) {
  const jour = 24 * 60;
  let m = ((totalMinutes % jour) + jour) % jour;
  const h = Math.floor(m / 60);
  const min = Math.round(m % 60);
  return `${String(h).padStart(2, "0")}:${String(min).padStart(2, "0")}`;
}

/**
 * Calcule, pour un ordre de tournée donné, l'heure d'arrivée et l'heure de
 * fin (départ) chez chaque patient, à partir de l'heure de départ de
 * l'agent. Chaque visite dure VISIT_DURATION_MIN minutes.
 *
 * Ce sont des horaires ESTIMÉS (calcul haversine côté client) — à distinguer
 * du statut RÉEL de la tournée (state.suiviStatuts), alimenté par les
 * événements UC6 envoyés au fil de l'eau. Le rapprochement entre les deux
 * est justement la matière du futur rapport "estimé vs. réalisé" (UC7).
 */
function calculerHoraires(tourneeOrder) {
  const agentLat = state.agent.lat;
  const agentLng = state.agent.lng;

  let position = { lat: agentLat, lng: agentLng };
  let curseurMinutes = parseHeureDebutEnMinutes();

  const horaires = [];

  tourneeOrder.forEach((pid) => {
    const patient = state.patients.find((p) => p.id === pid);
    if (!patient) return;

    const distanceKm = haversineKm(position.lat, position.lng, patient.lat, patient.lng);
    const trajetMin = (distanceKm / VITESSE_MOYENNE_KMH) * 60;

    const heureArrivee = curseurMinutes + trajetMin;
    const heureFin = heureArrivee + VISIT_DURATION_MIN;

    horaires.push({
      id: pid,
      arrivee: minutesEnHeure(heureArrivee),
      fin: minutesEnHeure(heureFin),
      arriveeMinutes: heureArrivee,
      finMinutes: heureFin
    });

    curseurMinutes = heureFin;
    position = { lat: patient.lat, lng: patient.lng };
  });

  return { horaires, heureFinTotale: curseurMinutes };
}

/* --------------------------------------------------------------------------
   Map Initialization & Render
   -------------------------------------------------------------------------- */
function initMap() {
  map = L.map("map").setView([state.agent.lat, state.agent.lng], 12);

  L.tileLayer("https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png", {
    attribution: '&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a> contributors',
    maxZoom: 18
  }).addTo(map);

  markersGroup = L.layerGroup().addTo(map);
  updateMapMarkers();
}

function updateMapMarkers(tourneeOrder = []) {
  markersGroup.clearLayers();

  const agentLat = state.agent.lat;
  const agentLng = state.agent.lng;

  const agentMarker = L.circleMarker([agentLat, agentLng], {
    radius: 10,
    fillColor: "#2563eb",
    color: "#ffffff",
    weight: 3,
    opacity: 1,
    fillOpacity: 0.9
  }).bindPopup(`<b>Agent ${state.agent.id}</b><br>Adresse: ${state.agent.adresse || 'Tunis Centre'}<br>Lat: ${agentLat}, Lng: ${agentLng}`);

  markersGroup.addLayer(agentMarker);

  state.patients.forEach(patient => {
    let color = "#059669";
    if (patient.urgence === 2) color = "#d97706";
    if (patient.urgence === 3) color = "#dc2626";

    let orderIndex = tourneeOrder.indexOf(patient.id);
    let popupContent = `
      <b>[${patient.id}] ${patient.nom} ${patient.prenom}</b><br>
      Urgence: <strong>${patient.urgence}</strong> | Service: ${patient.service}<br>
      Durée de visite: ${VISIT_DURATION_MIN} min<br>
      ${orderIndex >= 0 ? `<span style="color:#2563eb; font-weight:bold;">Ordre de visite: Step ${orderIndex + 1}</span>` : ''}
    `;

    const marker = L.circleMarker([patient.lat, patient.lng], {
      radius: 8,
      fillColor: color,
      color: "#ffffff",
      weight: 2,
      opacity: 1,
      fillOpacity: 0.85
    }).bindPopup(popupContent);

    markersGroup.addLayer(marker);
  });
}

function drawRouteOnMap(tourneeOrder) {
  if (routePolyline) {
    map.removeLayer(routePolyline);
  }

  if (!tourneeOrder || tourneeOrder.length === 0) return;

  const coords = [];
  coords.push([state.agent.lat, state.agent.lng]);

  tourneeOrder.forEach(pid => {
    const patient = state.patients.find(p => p.id === pid);
    if (patient) {
      coords.push([patient.lat, patient.lng]);
    }
  });

  routePolyline = L.polyline(coords, {
    color: "#2563eb",
    weight: 4,
    opacity: 0.8,
    dashArray: "6, 8"
  }).addTo(map);

  map.fitBounds(routePolyline.getBounds(), { padding: [40, 40] });
}

/* --------------------------------------------------------------------------
   Suivi temps réel (UC6) — statuts, événements, actions de l'agent
   -------------------------------------------------------------------------- */

/**
 * Envoie un événement de suivi au microservice (POST /api/v1/evenements-tournee).
 * Retourne true/false selon le succès de l'envoi.
 *
 * Ne bloque jamais l'interface en cas d'échec réseau (le statut affiché
 * reste tel quel côté client) — l'agent doit pouvoir continuer sa tournée
 * même si la connectivité est mauvaise sur le terrain ; un avertissement est
 * simplement loggé en console.
 */
async function envoyerEvenementSuivi(patientId, typeEvenement) {
  const payload = {
    agent_id: state.agent.id,
    patient_id: patientId,
    type_evenement: typeEvenement,
    horodatage: new Date().toISOString(),
    position: { lat: state.agent.lat, lng: state.agent.lng }
  };

  try {
    const response = await fetch(`${API_BASE_URL}/api/v1/evenements-tournee`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload)
    });

    if (!response.ok) {
      const errData = await response.json();
      console.warn("Événement de suivi refusé par le serveur:", formatErreurAPI(errData));
      return false;
    }
    return true;
  } catch (err) {
    console.error("Erreur réseau lors de l'envoi de l'événement de suivi:", err);
    return false;
  }
}

/**
 * Étape 1 du workflow : l'agent quitte sa position actuelle vers ce patient.
 * Envoie "depart" pour la toute première étape de la tournée (départ de la
 * base), "en_route" pour les étapes suivantes (départ du patient précédent).
 */
async function marquerDepart(patientId, idx) {
  state.suiviStatuts[patientId] = "en_route";
  renderPatients();
  await envoyerEvenementSuivi(patientId, idx === 0 ? "depart" : "en_route");
}

/** Étape 2 : l'agent arrive chez le patient. */
async function marquerArrivee(patientId) {
  state.suiviStatuts[patientId] = "arrivee";
  renderPatients();
  await envoyerEvenementSuivi(patientId, "arrivee");
}

/** Étape 3 : l'agent termine la prestation chez ce patient (= UC5 + UC6). */
async function marquerFinService(patientId) {
  state.suiviStatuts[patientId] = "termine";
  renderPatients();
  await envoyerEvenementSuivi(patientId, "fin_service");
}

/**
 * Réinitialise l'affichage local d'une étape déjà marquée "terminé" (en cas
 * de clic accidentel). Ne supprime PAS les événements déjà envoyés au
 * serveur : le journal UC6 est un journal en ajout seul (append-only),
 * comme un vrai journal d'audit — on ne réécrit pas l'historique, on
 * recommence juste l'étape côté agent.
 */
function annulerStatutPatient(patientId) {
  state.suiviStatuts[patientId] = "a_venir";
  renderPatients();
}

/**
 * Construit le bloc HTML d'action/statut pour une étape de la tournée.
 * idx           : position de ce patient dans la tournée (0 = premier)
 * statut        : "a_venir" | "en_route" | "arrivee" | "termine"
 * estEtapeActive: true seulement pour la première étape non terminée —
 *                 seule l'étape active affiche un bouton d'action, les
 *                 étapes futures affichent un badge passif "À venir".
 */
function renderActionSuivi(patientId, idx, statut, estEtapeActive) {
  if (statut === "termine") {
    return `
      <span class="badge badge-suivi-termine"><i class="fa-solid fa-check"></i> Terminé</span>
      <button class="btn-icon-move" onclick="annulerStatutPatient('${patientId}')" title="Annuler (n'efface pas l'historique déjà envoyé)">
        <i class="fa-solid fa-rotate-left"></i>
      </button>
    `;
  }

  if (!estEtapeActive) {
    return `<span class="badge badge-suivi-a-venir">À venir</span>`;
  }

  if (statut === "a_venir") {
    const estPremiereEtape = idx === 0;
    return `
      <button class="btn-suivi btn-suivi-en-route" onclick="marquerDepart('${patientId}', ${idx})">
        <i class="fa-solid ${estPremiereEtape ? 'fa-door-open' : 'fa-car'}"></i> ${estPremiereEtape ? 'Départ' : 'En route'}
      </button>`;
  }

  if (statut === "en_route") {
    return `
      <span class="badge badge-suivi-en-route"><i class="fa-solid fa-car"></i> En route</span>
      <button class="btn-suivi btn-suivi-arrivee" onclick="marquerArrivee('${patientId}')">
        <i class="fa-solid fa-location-dot"></i> Arrivé
      </button>`;
  }

  if (statut === "arrivee") {
    return `
      <span class="badge badge-suivi-arrivee"><i class="fa-solid fa-location-dot"></i> Chez le patient</span>
      <button class="btn-suivi btn-suivi-termine" onclick="marquerFinService('${patientId}')">
        <i class="fa-solid fa-check"></i> Terminer la visite
      </button>`;
  }

  return "";
}

/* --------------------------------------------------------------------------
   Patient List & Tour Sequence Rendering & Actions
   -------------------------------------------------------------------------- */
function renderPatients() {
  const container = document.getElementById("patients-list");
  document.getElementById("patients-count").textContent = state.patients.length;

  const statusBadge = document.getElementById("tournee-status-badge");
  const reorderHint = document.getElementById("reorder-hint");
  const suiviHint = document.getElementById("suivi-hint");

  if (state.patients.length === 0) {
    container.innerHTML = `
      <div class="empty-timeline-text">
        Aucun patient affecté pour le moment par Med.tn.
      </div>`;
    if (statusBadge) {
      statusBadge.textContent = "Vide";
      statusBadge.className = "badge badge-neutral";
    }
    if (reorderHint) reorderHint.style.display = "none";
    if (suiviHint) suiviHint.style.display = "none";
    updateMapMarkers();
    return;
  }

  const isOptimized = state.lastOptimization && state.lastOptimization.tournee && state.lastOptimization.tournee.length > 0;

  if (statusBadge) {
    if (!isOptimized) {
      statusBadge.textContent = "Non optimisée";
      statusBadge.className = "badge badge-neutral";
    } else if (state.lastOptimization.modifiee_manuellement) {
      statusBadge.textContent = "Modifiée manuellement";
      statusBadge.className = "badge badge-warning";
    } else {
      statusBadge.textContent = "Tournée Optimisée";
      statusBadge.className = "badge badge-success";
    }
  }

  if (reorderHint) {
    reorderHint.style.display = isOptimized && state.lastOptimization.tournee.length > 1 ? "flex" : "none";
  }
  if (suiviHint) {
    suiviHint.style.display = isOptimized ? "flex" : "none";
  }

  let patientsToRender = [];
  let horairesMap = new Map();

  // Position (index dans la tournée) de la première étape pas encore
  // terminée — seule celle-ci affiche un bouton d'action (cf. renderActionSuivi)
  let indexEtapeActive = -1;
  if (isOptimized) {
    indexEtapeActive = state.lastOptimization.tournee.findIndex(
      pid => (state.suiviStatuts[pid] || "a_venir") !== "termine"
    );
  }

  if (isOptimized) {
    const { horaires } = calculerHoraires(state.lastOptimization.tournee);
    horaires.forEach(h => horairesMap.set(h.id, h));

    state.lastOptimization.tournee.forEach(pid => {
      const p = state.patients.find(item => item.id === pid);
      if (p) patientsToRender.push({ patient: p, inTour: true });
    });

    state.patients.forEach(p => {
      if (!state.lastOptimization.tournee.includes(p.id)) {
        patientsToRender.push({ patient: p, inTour: false });
      }
    });
  } else {
    state.patients.forEach(p => {
      patientsToRender.push({ patient: p, inTour: false });
    });
  }

  const tourneeOrderForMarkers = isOptimized ? state.lastOptimization.tournee : [];
  const totalTourSteps = isOptimized ? state.lastOptimization.tournee.length : 0;

  container.innerHTML = patientsToRender.map((item, idx) => {
    const p = item.patient;
    const inTour = item.inTour;
    const h = inTour ? horairesMap.get(p.id) : null;
    const statutSuivi = state.suiviStatuts[p.id] || "a_venir";
    const estTermine = statutSuivi === "termine";
    const estEtapeActive = inTour && idx === indexEtapeActive;

    let badgeClass = "badge-u1";
    let urgenceLabel = "Urgence 1 (Faible)";
    if (p.urgence === 2) { badgeClass = "badge-u2"; urgenceLabel = "Urgence 2 (Moyenne)"; }
    if (p.urgence === 3) { badgeClass = "badge-u3"; urgenceLabel = "Urgence 3 (Élevée)"; }

    return `
      <div class="patient-card-item ${inTour ? 'is-tour-step' : ''} ${estTermine ? 'timeline-step-done' : ''}"
           ${inTour ? `draggable="true"
           ondragstart="onDragStart(event, ${idx})"
           ondragover="onDragOver(event)"
           ondragend="onDragEnd(event)"
           ondrop="onDrop(event, ${idx})"` : ''}>

        <div class="patient-item-header">
          <div class="patient-name-box">
            ${inTour ? `<i class="fa-solid fa-grip-vertical drag-handle" title="Glisser pour réordonner"></i>` : ''}
            ${inTour ? `<span class="step-badge">Étape ${idx + 1}</span>` : ''}
            <span class="patient-id-tag">${p.id}</span>
            <span class="patient-name ${estTermine ? 'strike' : ''}">${p.nom} ${p.prenom}</span>
          </div>

          <div class="patient-header-actions">
            <span class="badge ${badgeClass}">${urgenceLabel}</span>
            ${inTour ? `
              <button class="btn-icon-move" onclick="deplacerPatient(${idx}, -1)" title="Monter" ${idx === 0 ? "disabled" : ""}>
                <i class="fa-solid fa-chevron-up"></i>
              </button>
              <button class="btn-icon-move" onclick="deplacerPatient(${idx}, 1)" title="Descendre" ${idx === totalTourSteps - 1 ? "disabled" : ""}>
                <i class="fa-solid fa-chevron-down"></i>
              </button>
              ${renderActionSuivi(p.id, idx, statutSuivi, estEtapeActive)}
            ` : ''}
          </div>
        </div>

        ${inTour && h ? `
          <div class="patient-schedule-bar">
            <span class="time-badge">
              <i class="fa-solid fa-right-to-bracket"></i> Arrivée ${h.arrivee}
              &nbsp;→&nbsp;
              <i class="fa-solid fa-right-from-bracket"></i> Fin ${h.fin}
              <span class="time-badge-note">(estimé)</span>
            </span>
            <span style="font-size: 0.78rem; color: var(--text-muted);"><i class="fa-solid fa-clock"></i> Visite ${VISIT_DURATION_MIN} min</span>
          </div>
        ` : ''}

        <div class="patient-meta-row">
          <span class="patient-meta-item"><i class="fa-solid fa-briefcase-medical"></i> ${p.service}</span>
          <span class="patient-meta-item"><i class="fa-solid fa-phone"></i> ${p.contact || 'N/A'}</span>
        </div>

        <div class="patient-coords-row">
          <div><i class="fa-solid fa-location-dot"></i> ${p.adresse || 'Adresse inconnue'}</div>
        </div>
      </div>
    `;
  }).join("");

  updateMapMarkers(tourneeOrderForMarkers);
}

/* --------------------------------------------------------------------------
   API Calls: Optimization & Reordering
   -------------------------------------------------------------------------- */
async function checkApiHealth() {
  const statusElem = document.getElementById("api-status-text");
  try {
    const res = await fetch(`${API_BASE_URL}/`);
    if (res.ok) {
      statusElem.textContent = "Microservice actif (127.0.0.1:8000)";
      statusElem.parentElement.querySelector(".status-indicator").classList.add("active");
    } else {
      throw new Error("HTTP Status " + res.status);
    }
  } catch (err) {
    statusElem.textContent = "Serveur API non détecté (Lancez uvicorn app.api:app)";
    statusElem.parentElement.querySelector(".status-indicator").classList.remove("active");
  }
}

function formatErreurAPI(errData) {
  const detail = errData && errData.detail;

  if (!detail) return "Erreur inconnue.";
  if (typeof detail === "string") return detail;

  if (Array.isArray(detail)) {
    return detail
      .map(err => {
        if (typeof err === "string") return err;
        const champ = Array.isArray(err.loc) ? err.loc.filter(x => x !== "body").join(" → ") : "";
        return champ ? `${champ} : ${err.msg}` : err.msg;
      })
      .join("\n");
  }

  return JSON.stringify(detail);
}

function buildPatientsPayload() {
  return state.patients.map(p => ({
    id: p.id,
    adresse: p.adresse || 'Tunis Centre, Tunisie',
    service: p.service,
    urgence: parseInt(p.urgence, 10),
    duree: VISIT_DURATION_MIN
  }));
}

async function runOptimization() {
  state.agent.adresse = document.getElementById("agent-adresse").value.trim() || "Avenue Habib Bourguiba, Tunis, Tunisie";

  const btnOpt = document.getElementById("btn-optimiser");
  btnOpt.disabled = true;
  btnOpt.innerHTML = `<i class="fa-solid fa-spinner fa-spin"></i> Calcul en cours...`;

  const payload = {
    agent: { id: state.agent.id, adresse: state.agent.adresse },
    patients: buildPatientsPayload()
  };

  try {
    const response = await fetch(`${API_BASE_URL}/api/v1/optimiser-tournee`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload)
    });

    if (!response.ok) {
      const errData = await response.json();
      throw new Error(formatErreurAPI(errData) || "Erreur lors de l'optimisation");
    }

    const data = await response.json();
    state.lastOptimization = data;
    state.tourneeInitialeProposee = [...data.tournee];
    // Nouvelle tournée = nouveau suivi temps réel, on repart de "à venir" pour chacun
    state.suiviStatuts = {};
    data.tournee.forEach(pid => { state.suiviStatuts[pid] = "a_venir"; });

    displayOptimizationResults(data);
    drawRouteOnMap(data.tournee);
    updateMapMarkers(data.tournee);

  } catch (error) {
    alert(`Échec de l'optimisation: ${error.message}`);
  } finally {
    btnOpt.disabled = false;
    btnOpt.innerHTML = `<i class="fa-solid fa-route"></i> Optimiser la Tournée`;
  }
}

async function appliquerReordonnancement(nouvelOrdre) {
  if (!state.lastOptimization) return;

  state.lastOptimization.tournee = [...nouvelOrdre];
  state.lastOptimization.modifiee_manuellement = true;
  displayOptimizationResults(state.lastOptimization);
  drawRouteOnMap(nouvelOrdre);
  updateMapMarkers(nouvelOrdre);

  state.agent.adresse = document.getElementById("agent-adresse").value.trim() || "Avenue Habib Bourguiba, Tunis, Tunisie";

  const payload = {
    agent: { id: state.agent.id, adresse: state.agent.adresse },
    patients: buildPatientsPayload(),
    tournee_initiale: state.tourneeInitialeProposee || [...nouvelOrdre],
    nouvel_ordre: nouvelOrdre
  };

  try {
    const response = await fetch(`${API_BASE_URL}/api/v1/reordonner-tournee`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload)
    });

    if (!response.ok) {
      const errData = await response.json();
      console.warn("API reordonner warning:", formatErreurAPI(errData));
      return;
    }

    const data = await response.json();
    state.lastOptimization = {
      agent_id: data.agent_id,
      tournee: data.tournee,
      distance_totale: data.distance_totale,
      duree_totale_min: data.duree_totale_min,
      position_finale: data.position_finale,
      modifiee_manuellement: true
    };

    displayOptimizationResults(state.lastOptimization);
    drawRouteOnMap(data.tournee);
    updateMapMarkers(data.tournee);

  } catch (error) {
    console.error("Réordonnancement API error:", error);
  }
}

function deplacerPatient(index, direction) {
  if (!state.lastOptimization || !state.lastOptimization.tournee) return;
  const tournee = [...state.lastOptimization.tournee];
  const nouvelIndex = index + direction;

  if (nouvelIndex < 0 || nouvelIndex >= tournee.length) return;

  [tournee[index], tournee[nouvelIndex]] = [tournee[nouvelIndex], tournee[index]];
  appliquerReordonnancement(tournee);
}

function onDragStart(e, index) {
  state.draggedIndex = index;
  e.dataTransfer.effectAllowed = "move";
  try {
    e.dataTransfer.setData("text/plain", String(index));
  } catch (err) {}
  e.currentTarget.classList.add("dragging");
}

function onDragOver(e) {
  e.preventDefault();
  e.dataTransfer.dropEffect = "move";
}

function onDragEnd(e) {
  e.currentTarget.classList.remove("dragging");
}

function onDrop(e, index) {
  e.preventDefault();
  if (state.draggedIndex === null || state.draggedIndex === index || !state.lastOptimization || !state.lastOptimization.tournee) return;

  const tournee = [...state.lastOptimization.tournee];
  const [deplace] = tournee.splice(state.draggedIndex, 1);
  tournee.splice(index, 0, deplace);
  state.draggedIndex = null;

  appliquerReordonnancement(tournee);
}

/* --------------------------------------------------------------------------
   Affichage des résultats (stats + recalculs)
   -------------------------------------------------------------------------- */
function formatDureeHM(minutes) {
  const h = Math.floor(minutes / 60);
  const m = Math.round(minutes % 60);
  if (h > 0 && m > 0) return `${h}h ${m}min`;
  if (h > 0) return `${h}h`;
  return `${m}min`;
}

function displayOptimizationResults(data) {
  const dureeElem = document.getElementById("res-duree");
  if (dureeElem) dureeElem.textContent = formatDureeHM(data.duree_totale_min);

  const { heureFinTotale } = data.tournee && data.tournee.length > 0 ? calculerHoraires(data.tournee) : { heureFinTotale: parseHeureDebutEnMinutes() };
  const heureFinElem = document.getElementById("res-heure-fin");
  if (heureFinElem) heureFinElem.textContent = minutesEnHeure(heureFinTotale);

  const statusElem = document.getElementById("optimization-status");
  if (statusElem) {
    if (data.modifiee_manuellement) {
      statusElem.innerHTML = `<i class="fa-solid fa-pen"></i> Modifiée manuellement`;
      statusElem.className = "badge badge-warning";
    } else {
      statusElem.innerHTML = `<i class="fa-solid fa-check"></i> Optimisée`;
      statusElem.className = "badge badge-success";
    }
  }

  const noteContainer = document.getElementById("reorder-note-container");
  if (noteContainer) {
    if (data.modifiee_manuellement && state.tourneeInitialeProposee) {
      noteContainer.innerHTML = `<p class="reorder-note"><i class="fa-solid fa-pen"></i> Tournée modifiée manuellement par l'agent.<br>Proposition initiale : ${state.tourneeInitialeProposee.join(" → ")}</p>`;
    } else {
      noteContainer.innerHTML = "";
    }
  }

  renderPatients();
}