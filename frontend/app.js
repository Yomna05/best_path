/**
 * Med.tn — Microservice Tournée Web Frontend Application
 */

const API_BASE_URL = "http://127.0.0.1:8000";

// Default dataset matching app/data.py
const DEFAULT_PATIENTS = [
  { id: "P1", nom: "Trabelsi", prenom: "Amel", contact: "+216 20 123 456", lat: 36.8189, lng: 10.1658, service: "prelevement", urgence: 2, duree: 20 },
  { id: "P2", nom: "Gharbi", prenom: "Sami", contact: "+216 22 234 567", lat: 36.8020, lng: 10.1900, service: "consultation", urgence: 1, duree: 30 },
  { id: "P3", nom: "Bouazizi", prenom: "Rim", contact: "+216 24 345 678", lat: 36.8250, lng: 10.1750, service: "suivi", urgence: 3, duree: 15 },
  { id: "P4", nom: "Jendoubi", prenom: "Karim", contact: "+216 26 456 789", lat: 36.8663, lng: 10.3242, service: "consultation", urgence: 1, duree: 25 },
  { id: "P5", nom: "Cherif", prenom: "Nadia", contact: "+216 27 567 890", lat: 36.8622, lng: 10.1956, service: "prelevement", urgence: 2, duree: 15 },
  { id: "P6", nom: "Mabrouk", prenom: "Youssef", contact: "+216 28 678 901", lat: 36.8093, lng: 10.1408, service: "suivi", urgence: 2, duree: 20 },
  { id: "P7", nom: "Ayari", prenom: "Salma", contact: "+216 29 789 012", lat: 36.7538, lng: 10.2270, service: "prelevement", urgence: 3, duree: 10 },
  { id: "P8", nom: "Khemiri", prenom: "Mehdi", contact: "+216 21 890 123", lat: 36.8397, lng: 10.2350, service: "consultation", urgence: 1, duree: 30 }
];

// App State
let state = {
  agent: {
    id: "A1",
    lat: 36.8065,
    lng: 10.1815
  },
  patients: JSON.parse(JSON.stringify(DEFAULT_PATIENTS)),
  lastOptimization: null
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
   Map Initialization & Render
   -------------------------------------------------------------------------- */
function initMap() {
  map = L.map("map").setView([state.agent.lat, state.agent.lng], 12);

  // Light tiles
  L.tileLayer("https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png", {
    attribution: '&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a> contributors',
    maxZoom: 18
  }).addTo(map);

  markersGroup = L.layerGroup().addTo(map);
  updateMapMarkers();
}

function updateMapMarkers(tourneeOrder = []) {
  markersGroup.clearLayers();

  // Agent Marker
  const agentLat = parseFloat(document.getElementById("agent-lat").value) || state.agent.lat;
  const agentLng = parseFloat(document.getElementById("agent-lng").value) || state.agent.lng;
  state.agent.lat = agentLat;
  state.agent.lng = agentLng;

  const agentMarker = L.circleMarker([agentLat, agentLng], {
    radius: 10,
    fillColor: "#2563eb",
    color: "#ffffff",
    weight: 3,
    opacity: 1,
    fillOpacity: 0.9
  }).bindPopup(`<b>Agent ${state.agent.id}</b><br>Départ: Tunis Centre<br>Lat: ${agentLat}, Lng: ${agentLng}`);

  markersGroup.addLayer(agentMarker);

  // Patient Markers
  state.patients.forEach(patient => {
    let color = "#059669"; // Urgence 1
    if (patient.urgence === 2) color = "#d97706";
    if (patient.urgence === 3) color = "#dc2626";

    // Order index if tournee is available
    let orderIndex = tourneeOrder.indexOf(patient.id);
    let popupContent = `
      <b>[${patient.id}] ${patient.nom} ${patient.prenom}</b><br>
      Urgence: <strong>${patient.urgence}</strong> | Service: ${patient.service}<br>
      Durée: ${patient.duree} min<br>
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
  // Start at Agent
  coords.push([state.agent.lat, state.agent.lng]);

  // Add each patient in optimized order
  tourneeOrder.forEach(pid => {
    const patient = state.patients.find(p => p.id === pid);
    if (patient) {
      coords.push([patient.lat, patient.lng]);
    }
  });

  // Draw smooth polyline
  routePolyline = L.polyline(coords, {
    color: "#2563eb",
    weight: 4,
    opacity: 0.8,
    dashArray: "6, 8"
  }).addTo(map);

  // Fit map bounds to show full route
  map.fitBounds(routePolyline.getBounds(), { padding: [40, 40] });
}

/* --------------------------------------------------------------------------
   Patient List Rendering & Actions
   -------------------------------------------------------------------------- */
function renderPatients() {
  const container = document.getElementById("patients-list");
  document.getElementById("patients-count").textContent = state.patients.length;
  document.getElementById("agent-id-display").textContent = `Agent: ${state.agent.id}`;

  if (state.patients.length === 0) {
    container.innerHTML = `
      <div class="empty-timeline-text">
        Aucun patient attribué pour le moment. Cliquez sur <strong>"+ Ajouter Patient"</strong> pour commencer.
      </div>`;
    updateMapMarkers();
    return;
  }

  container.innerHTML = state.patients.map(p => {
    let badgeClass = "badge-u1";
    let urgenceLabel = "Urgence 1 (Faible)";
    if (p.urgence === 2) { badgeClass = "badge-u2"; urgenceLabel = "Urgence 2 (Moyenne)"; }
    if (p.urgence === 3) { badgeClass = "badge-u3"; urgenceLabel = "Urgence 3 (Élevée)"; }

    return `
      <div class="patient-card-item">
        <div class="patient-item-header">
          <div class="patient-name-box">
            <span class="patient-id-tag">${p.id}</span>
            <span class="patient-name">${p.nom} ${p.prenom}</span>
          </div>
          <div style="display:flex; align-items:center; gap:8px;">
            <span class="badge ${badgeClass}">${urgenceLabel}</span>
            <button class="btn-icon-delete" onclick="deletePatient('${p.id}')" title="Supprimer ce patient">
              <i class="fa-solid fa-trash-can"></i>
            </button>
          </div>
        </div>

        <div class="patient-meta-row">
          <span class="patient-meta-item"><i class="fa-solid fa-briefcase-medical"></i> ${p.service}</span>
          <span class="patient-meta-item"><i class="fa-solid fa-clock"></i> ${p.duree} min</span>
          <span class="patient-meta-item"><i class="fa-solid fa-phone"></i> ${p.contact || 'N/A'}</span>
        </div>

        <div class="patient-coords-row">
          <i class="fa-solid fa-location-crosshairs"></i> Lat: ${p.lat}, Lng: ${p.lng}
        </div>
      </div>
    `;
  }).join("");

  updateMapMarkers();
}

function deletePatient(patientId) {
  state.patients = state.patients.filter(p => p.id !== patientId);
  renderPatients();
  // Clear polyline if list changed
  if (routePolyline) {
    map.removeLayer(routePolyline);
    routePolyline = null;
  }
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

async function runOptimization() {
  // Update agent from input fields
  state.agent.id = document.getElementById("agent-id").value.trim() || "A1";
  state.agent.lat = parseFloat(document.getElementById("agent-lat").value) || 36.8065;
  state.agent.lng = parseFloat(document.getElementById("agent-lng").value) || 10.1815;

  const btnOpt = document.getElementById("btn-optimiser");
  btnOpt.disabled = true;
  btnOpt.innerHTML = `<i class="fa-solid fa-spinner fa-spin"></i> Calcul en cours...`;

  const payload = {
    agent: {
      id: state.agent.id,
      lat: state.agent.lat,
      lng: state.agent.lng
    },
    patients: state.patients.map(p => ({
      id: p.id,
      lat: p.lat,
      lng: p.lng,
      service: p.service,
      urgence: parseInt(p.urgence, 10),
      duree: parseInt(p.duree, 10)
    }))
  };

  try {
    const response = await fetch(`${API_BASE_URL}/api/v1/optimiser-tournee`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload)
    });

    if (!response.ok) {
      const errData = await response.json();
      throw new Error(errData.detail || "Erreur lors de l'optimisation");
    }

    const data = await response.json();
    state.lastOptimization = data;
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

function displayOptimizationResults(data) {
  document.getElementById("res-distance").textContent = `${data.distance_totale} km`;
  document.getElementById("res-duree").textContent = `${data.duree_totale_min} min`;
  document.getElementById("res-pos-finale").textContent = `Lat: ${data.position_finale.lat.toFixed(4)}, Lng: ${data.position_finale.lng.toFixed(4)}`;
  
  const timelineContainer = document.getElementById("timeline-list");
  
  if (!data.tournee || data.tournee.length === 0) {
    timelineContainer.innerHTML = `<p class="empty-timeline-text">La tournée est vide.</p>`;
    return;
  }

  timelineContainer.innerHTML = data.tournee.map((pid, idx) => {
    const p = state.patients.find(item => item.id === pid);
    if (!p) return '';

    let badgeClass = "badge-u1";
    if (p.urgence === 2) badgeClass = "badge-u2";
    if (p.urgence === 3) badgeClass = "badge-u3";

    return `
      <div class="timeline-step">
        <div class="step-num">${idx + 1}</div>
        <div class="step-info">
          <span class="patient-id-tag">${p.id}</span>
          <span class="step-patient-name">${p.nom} ${p.prenom}</span>
          <span class="badge ${badgeClass}" style="margin-left:auto;">Urgence ${p.urgence}</span>
          <span style="font-size:0.82rem; color:var(--text-muted);"><i class="fa-solid fa-clock"></i> ${p.duree} min</span>
        </div>
      </div>
    `;
  }).join("");
}

/* --------------------------------------------------------------------------
   Modal & Event Bindings
   -------------------------------------------------------------------------- */
function bindEvents() {
  // Optimization click
  document.getElementById("btn-optimiser").addEventListener("click", runOptimization);

  // Reset default patients
  document.getElementById("btn-reset-patients").addEventListener("click", () => {
    state.patients = JSON.parse(JSON.stringify(DEFAULT_PATIENTS));
    renderPatients();
    if (routePolyline) { map.removeLayer(routePolyline); routePolyline = null; }
  });

  // Modal open & close
  const modal = document.getElementById("modal-add-patient");
  document.getElementById("btn-open-add-modal").addEventListener("click", () => {
    // Generate next ID
    const nextIdNum = state.patients.length + 1;
    document.getElementById("p-id").value = `P${nextIdNum}`;
    modal.classList.add("show");
  });

  const closeModal = () => modal.classList.remove("show");
  document.getElementById("btn-close-modal").addEventListener("click", closeModal);
  document.getElementById("btn-cancel-modal").addEventListener("click", closeModal);

  // Preset location buttons in modal
  document.querySelectorAll(".preset-btn").forEach(btn => {
    btn.addEventListener("click", (e) => {
      document.getElementById("p-lat").value = e.target.dataset.lat;
      document.getElementById("p-lng").value = e.target.dataset.lng;
    });
  });

  // Form submit
  document.getElementById("form-add-patient").addEventListener("submit", (e) => {
    e.preventDefault();

    const newPatient = {
      id: document.getElementById("p-id").value.trim(),
      nom: document.getElementById("p-nom").value.trim(),
      prenom: document.getElementById("p-prenom").value.trim(),
      contact: document.getElementById("p-contact").value.trim() || "+216 20 000 000",
      service: document.getElementById("p-service").value,
      urgence: parseInt(document.getElementById("p-urgence").value, 10),
      duree: parseInt(document.getElementById("p-duree").value, 10),
      lat: parseFloat(document.getElementById("p-lat").value),
      lng: parseFloat(document.getElementById("p-lng").value)
    };

    // Check duplicate ID
    if (state.patients.some(p => p.id === newPatient.id)) {
      alert(`Un patient avec l'ID ${newPatient.id} existe déjà.`);
      return;
    }

    state.patients.push(newPatient);
    renderPatients();
    closeModal();
    document.getElementById("form-add-patient").reset();
  });
}
