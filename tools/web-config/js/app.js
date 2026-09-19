/**
 * Snippen SMS Gateway - Web Bluetooth Configurator Application Controller
 */

import { SnippenBLEClient, MockSnippenBLEClient, isWebBluetoothSupported } from './ble.js';

// Register Service Worker for PWA support
if ('serviceWorker' in navigator && window.location.protocol.startsWith('http')) {
  window.addEventListener('load', () => {
    navigator.serviceWorker.register('./sw.js').catch((err) => {
      console.warn('[PWA] Service worker registration failed:', err);
    });
  });
}

// State
let isSimulator = false;
let client = new SnippenBLEClient();

// DOM Elements
const simulatorToggle = document.getElementById('simulator-toggle');
const connectionPill = document.getElementById('connection-pill');
const connectionLabel = document.getElementById('connection-label');
const feedbackBanner = document.getElementById('feedback-banner');
const feedbackText = document.getElementById('feedback-text');

const btnConnect = document.getElementById('btn-connect');
const btnConnectText = document.getElementById('btn-connect-text');
const spinnerConnect = document.getElementById('spinner-connect');
const btnDisconnect = document.getElementById('btn-disconnect');
const deviceMac = document.getElementById('device-mac');

const cardWifi = document.getElementById('card-wifi');
const btnScanWifi = document.getElementById('btn-scan-wifi');
const spinnerScan = document.getElementById('spinner-scan');
const wifiSsidSelect = document.getElementById('wifi-ssid-select');
const wifiSsidManual = document.getElementById('wifi-ssid-manual');
const wifiPassword = document.getElementById('wifi-password');
const btnToggleWifiPw = document.getElementById('btn-toggle-wifi-pw');
const btnTestWifi = document.getElementById('btn-test-wifi');
const spinnerTest = document.getElementById('spinner-test');
const wifiTestFeedback = document.getElementById('wifi-test-feedback');
const wifiTestText = document.getElementById('wifi-test-text');

const cardApi = document.getElementById('card-api');
const apiBaseUrl = document.getElementById('api-base-url');
const apiToken = document.getElementById('api-token');
const btnToggleApiToken = document.getElementById('btn-toggle-api-token');
const pollInterval = document.getElementById('poll-interval');
const inboxInterval = document.getElementById('inbox-interval');

const cardTelemetry = document.getElementById('card-telemetry');
const telIp = document.getElementById('tel-ip');
const telWifiRssi = document.getElementById('tel-wifi-rssi');
const telCellular = document.getElementById('tel-cellular');
const telVersion = document.getElementById('tel-version');

const actionBar = document.getElementById('action-bar');
const btnApplyExit = document.getElementById('btn-apply-exit');
const spinnerApply = document.getElementById('spinner-apply');

// Check browser support on startup
if (!isWebBluetoothSupported()) {
  showFeedback(
    'Web Bluetooth støttes ikke direkte i denne nettleseren. Bruk Chrome på Android, eller aktiver Simulator-modus oppe til høyre for testing.',
    'info',
    10000
  );
  // Auto-enable simulator if Web Bluetooth is unavailable
  isSimulator = true;
  simulatorToggle.checked = true;
  initClient();
}

function initClient() {
  if (client && client.isConnected) {
    client.disconnect();
  }
  client = isSimulator ? new MockSnippenBLEClient() : new SnippenBLEClient();

  client.addEventListener('connected', (e) => {
    updateConnectionState('connected', e.detail.deviceName || 'Snippen Gateway');
    deviceMac.textContent = e.detail.deviceId ? `ID: ${e.detail.deviceId.slice(0, 12)}` : '';
    setCardsEnabled(true);
    showFeedback('Tilkoblet Snippen SMS Gateway via BLE!', 'success');
    loadActiveConfig();
  });

  client.addEventListener('disconnected', (e) => {
    updateConnectionState('disconnected');
    deviceMac.textContent = '';
    setCardsEnabled(false);
    showFeedback(`Koblet fra ${e.detail.deviceName || 'Gateway'}`, 'info');
  });

  client.addEventListener('status', (e) => {
    updateTelemetry(e.detail);
  });

  client.addEventListener('error', (e) => {
    console.error('[BLE Error]', e.detail);
    showFeedback(`Bluetooth-feil: ${e.detail.message || e.detail}`, 'error');
  });
}

function updateConnectionState(state, deviceName = '') {
  connectionPill.className = `status-pill ${state}`;
  if (state === 'connected') {
    connectionLabel.textContent = `Tilkoblet: ${deviceName}`;
    btnConnect.style.display = 'none';
    btnDisconnect.style.display = 'inline-flex';
  } else if (state === 'connecting') {
    connectionLabel.textContent = 'Kobler til...';
    btnConnect.disabled = true;
    spinnerConnect.classList.add('active');
    btnConnectText.textContent = 'Søker etter enhet...';
  } else {
    connectionLabel.textContent = isSimulator ? 'Frakoblet (Simulator)' : 'Frakoblet';
    btnConnect.style.display = 'inline-flex';
    btnConnect.disabled = false;
    spinnerConnect.classList.remove('active');
    btnConnectText.textContent = isSimulator ? 'Start Simulator Tilkobling' : 'Koble til Gateway';
    btnDisconnect.style.display = 'none';
  }
}

function setCardsEnabled(enabled) {
  const cards = [cardWifi, cardApi, cardTelemetry, actionBar];
  cards.forEach((el) => {
    el.style.opacity = enabled ? '1' : '0.5';
    el.style.pointerEvents = enabled ? 'auto' : 'none';
  });
}

function showFeedback(msg, type = 'info', duration = 5000) {
  feedbackBanner.className = `feedback-box show ${type}`;
  feedbackText.textContent = msg;
  if (duration > 0) {
    setTimeout(() => {
      feedbackBanner.classList.remove('show');
    }, duration);
  }
}

async function loadActiveConfig() {
  try {
    const cfg = await client.readConfig();
    if (cfg.wifi_ssid) {
      wifiSsidManual.value = cfg.wifi_ssid;
    }
    if (cfg.snippen_api_base_url) {
      apiBaseUrl.value = cfg.snippen_api_base_url;
    }
    if (cfg.snippen_api_token) {
      apiToken.value = cfg.snippen_api_token;
    }
    if (cfg.outbox_poll_interval_sec) {
      pollInterval.value = cfg.outbox_poll_interval_sec;
    }
    if (cfg.inbox_check_interval_sec) {
      inboxInterval.value = cfg.inbox_check_interval_sec;
    }
  } catch (err) {
    console.warn('[Config] Kunne ikke lese config automatisk:', err);
  }
}

function updateTelemetry(stat) {
  if (!stat) return;
  if (stat.ip) {
    telIp.textContent = stat.ip;
  }
  if (stat.wifi_rssi !== undefined) {
    telWifiRssi.textContent = `${stat.wifi_rssi} dBm`;
  }
  if (stat.cellular_csq !== undefined) {
    const dbm = stat.cellular_rssi_dbm ? ` (${stat.cellular_rssi_dbm} dBm)` : '';
    telCellular.textContent = `CSQ ${stat.cellular_csq}${dbm}`;
  }
  if (stat.firmware_version) {
    telVersion.textContent = `v${stat.firmware_version}`;
  }
}

// Event Listeners

simulatorToggle.addEventListener('change', (e) => {
  isSimulator = e.target.checked;
  initClient();
  updateConnectionState('disconnected');
  showFeedback(
    isSimulator ? 'Simulator-modus aktivert' : 'Ekte Web Bluetooth aktivert',
    'info'
  );
});

btnConnect.addEventListener('click', async () => {
  try {
    updateConnectionState('connecting');
    await client.connect();
  } catch (err) {
    updateConnectionState('disconnected');
    if (err.name !== 'NotFoundError') {
      showFeedback(`Tilkobling avbrutt eller feilet: ${err.message}`, 'error');
    }
  }
});

btnDisconnect.addEventListener('click', async () => {
  try {
    await client.disconnect();
  } catch (err) {
    console.error(err);
  }
});

btnScanWifi.addEventListener('click', async () => {
  btnScanWifi.disabled = true;
  spinnerScan.classList.add('active');
  wifiSsidSelect.innerHTML = '<option>Søker etter 2.4 GHz nettverk...</option>';

  try {
    const networks = await client.scanWifi();
    wifiSsidSelect.innerHTML = '<option value="">-- Velg et skannet nettverk --</option>';

    if (!networks || networks.length === 0) {
      wifiSsidSelect.innerHTML = '<option value="">Ingen nettverk funnet</option>';
      showFeedback('Ingen 2.4 GHz WiFi-nettverk funnet.', 'info');
      return;
    }

    networks.forEach((net) => {
      const opt = document.createElement('option');
      opt.value = net.ssid;
      const rssiStr = net.rssi ? ` (${net.rssi} dBm)` : '';
      const lockStr = net.auth && net.auth > 0 ? ' 🔒' : '';
      opt.textContent = `${net.ssid}${rssiStr}${lockStr}`;
      wifiSsidSelect.appendChild(opt);
    });

    showFeedback(`Fant ${networks.length} trådløse nettverk!`, 'success');
  } catch (err) {
    wifiSsidSelect.innerHTML = '<option value="">Kunne ikke skanne nettverk</option>';
    showFeedback(`WiFi-skann feilet: ${err.message}`, 'error');
  } finally {
    btnScanWifi.disabled = false;
    spinnerScan.classList.remove('active');
  }
});

wifiSsidSelect.addEventListener('change', (e) => {
  if (e.target.value) {
    wifiSsidManual.value = e.target.value;
  }
});

btnTestWifi.addEventListener('click', async () => {
  const ssid = wifiSsidManual.value.trim();
  const pw = wifiPassword.value;

  if (!ssid) {
    showFeedback('Vennligst oppgi et nettverksnavn (SSID) først.', 'error');
    return;
  }

  btnTestWifi.disabled = true;
  spinnerTest.classList.add('active');
  wifiTestFeedback.className = 'feedback-box show info';
  wifiTestText.textContent = `Tester oppkobling til '${ssid}'...`;

  try {
    const res = await client.testWifi(ssid, pw);
    if (res.connected) {
      wifiTestFeedback.className = 'feedback-box show success';
      wifiTestText.textContent = `✅ Tilkoblet! Tildelt IP: ${res.ip || 'OK'}`;
      if (res.ip) telIp.textContent = res.ip;
    } else {
      wifiTestFeedback.className = 'feedback-box show error';
      wifiTestText.textContent = `❌ Tilkobling feilet: ${res.message || 'Ukjent feil'}`;
    }
  } catch (err) {
    wifiTestFeedback.className = 'feedback-box show error';
    wifiTestText.textContent = `Feil ved testing: ${err.message}`;
  } finally {
    btnTestWifi.disabled = false;
    spinnerTest.classList.remove('active');
  }
});

btnToggleWifiPw.addEventListener('click', () => {
  wifiPassword.type = wifiPassword.type === 'password' ? 'text' : 'password';
});

btnToggleApiToken.addEventListener('click', () => {
  apiToken.type = apiToken.type === 'password' ? 'text' : 'password';
});

btnApplyExit.addEventListener('click', async () => {
  const ssid = wifiSsidManual.value.trim();
  const password = wifiPassword.value;
  const url = apiBaseUrl.value.trim();
  const token = apiToken.value.trim();
  const outboxSec = parseInt(pollInterval.value, 10) || 5;
  const inboxSec = parseInt(inboxInterval.value, 10) || 5;

  const payload = {
    wifi_ssid: ssid,
    snippen_api_base_url: url,
    outbox_poll_interval_sec: outboxSec,
    inbox_check_interval_sec: inboxSec,
  };

  // Only send password if entered
  if (password) {
    payload.wifi_password = password;
  }
  // Only send token if not the masked placeholder
  if (token && !token.includes('****')) {
    payload.snippen_api_token = token;
  }

  btnApplyExit.disabled = true;
  spinnerApply.classList.add('active');
  showFeedback('Lagrer konfigurasjon og starter gateway...', 'info', 0);

  try {
    await client.writeConfig(payload);
    await client.applyAndExit();
    showFeedback('✅ Konfigurasjon lagret! Lilygo starter nå normal gateway-drift.', 'success', 10000);
  } catch (err) {
    showFeedback(`Feil under lagring: ${err.message}`, 'error');
  } finally {
    btnApplyExit.disabled = false;
    spinnerApply.classList.remove('active');
  }
});

// Initialise
initClient();
