/**
 * Snippen SMS Gateway - Web Bluetooth Configurator Application Controller
 */

import { SnippenBLEClient, MockSnippenBLEClient, isWebBluetoothSupported } from './ble.js';

export const DEFAULT_CALL_REPLY_CALLER_TEXT =
  'Dette nummeret er en automatisert SMS-sentral for Snippen Booking og tar ikke imot samtaler. Send SMS eller ring leieansvarlig på 92830575.';
export const DEFAULT_CALL_NOTIFY_ADMIN_TEXT =
  'Ubesvart anrop til Snippen SMS-gateway fra {caller}.';

// Register Service Worker for PWA support
if ('serviceWorker' in navigator && window.location.protocol.startsWith('http')) {
  window.addEventListener('load', () => {
    navigator.serviceWorker.register('./sw.js').then((reg) => {
      reg.update();
    }).catch((err) => {
      console.warn('[PWA] Service worker registration failed:', err);
    });
  });
}

// State
let isSimulator = false;
let client = new SnippenBLEClient();
let allLogs = [];
let isLiveOperationsRunning = false;
let autoScroll = true;
let filterQuery = '';

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
const otaCheckOnBoot = document.getElementById('ota-check-on-boot');

const cardCalls = document.getElementById('card-calls');
const callForwardingNumber = document.getElementById('call-forwarding-number');
const callForwardingEnabled = document.getElementById('call-forwarding-enabled');
const callRejectEnabled = document.getElementById('call-reject-enabled');
const callNotifyAdminEnabled = document.getElementById('call-notify-admin-enabled');
const callNotifyAdminText = document.getElementById('call-notify-admin-text');
const callReplyCallerEnabled = document.getElementById('call-reply-caller-enabled');
const callReplyCallerText = document.getElementById('call-reply-caller-text');

const cardTelemetry = document.getElementById('card-telemetry');
const telIp = document.getElementById('tel-ip');
const telWifiRssi = document.getElementById('tel-wifi-rssi');
const telCellular = document.getElementById('tel-cellular');
const telVersion = document.getElementById('tel-version');
const telBoardProfile = document.getElementById('tel-board-profile');
const telOta = document.getElementById('tel-ota');

const cardOta = document.getElementById('card-ota');
const btnCheckOta = document.getElementById('btn-check-ota');
const spinnerCheckOta = document.getElementById('spinner-check-ota');
const btnStartOta = document.getElementById('btn-start-ota');
const spinnerStartOta = document.getElementById('spinner-start-ota');
const otaFeedback = document.getElementById('ota-feedback');
const otaFeedbackText = document.getElementById('ota-feedback-text');
const otaBanner = document.getElementById('ota-banner');
const otaBannerVersion = document.getElementById('ota-banner-version');
const otaBannerInstalled = document.getElementById('ota-banner-installed');
const btnBannerUpgrade = document.getElementById('btn-banner-upgrade');

const cardConsole = document.getElementById('card-console');
const operationsStatusPill = document.getElementById('operations-status-pill');
const operationsStatusLabel = document.getElementById('operations-status-label');
const btnToggleOperations = document.getElementById('btn-toggle-operations');
const btnOperationsIcon = document.getElementById('btn-operations-icon');
const btnOperationsText = document.getElementById('btn-operations-text');
const btnClearLogs = document.getElementById('btn-clear-logs');
const btnCopyLogs = document.getElementById('btn-copy-logs');
const autoscrollToggle = document.getElementById('autoscroll-toggle');
const logFilterInput = document.getElementById('log-filter-input');
const terminalContainer = document.getElementById('terminal-container');
const terminalLogOutput = document.getElementById('terminal-log-output');
const logCounter = document.getElementById('log-counter');
const logLastActivity = document.getElementById('log-last-activity');

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

  client.addEventListener('connected', async (e) => {
    updateConnectionState('connected', e.detail.deviceName || 'Snippen Gateway');
    deviceMac.textContent = e.detail.deviceId ? `ID: ${e.detail.deviceId.slice(0, 12)}` : '';
    setCardsEnabled(true);
    showFeedback('Tilkoblet Snippen SMS Gateway via BLE!', 'success');
    try {
      await loadActiveConfig();
      await fetchInitialLogs();
    } catch (err) {
      console.warn('[BLE] Feil under lasting etter tilkobling:', err);
    }
  });

  client.addEventListener('disconnected', (e) => {
    updateConnectionState('disconnected');
    deviceMac.textContent = '';
    setCardsEnabled(false);
    updateOperationsState(false);
    appendLogLine(`[ble] Koblet fra ${e.detail.deviceName || 'Gateway'}`);
    showFeedback(`Koblet fra ${e.detail.deviceName || 'Gateway'}`, 'info');
  });

  client.addEventListener('status', (e) => {
    updateTelemetry(e.detail);
  });

  client.addEventListener('log', (e) => {
    appendLogLine(e.detail.line, e.detail.timestamp);
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
  const cards = [cardWifi, cardApi, cardCalls, cardTelemetry, cardOta, cardConsole, actionBar];
  cards.forEach((el) => {
    if (el) {
      el.style.opacity = enabled ? '1' : '0.5';
      el.style.pointerEvents = enabled ? 'auto' : 'none';
    }
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
    if (cfg.inbox_check_interval_sec && inboxInterval) {
      inboxInterval.value = cfg.inbox_check_interval_sec;
    }
    if (cfg.ota_check_on_boot !== undefined && otaCheckOnBoot) {
      otaCheckOnBoot.checked = Boolean(cfg.ota_check_on_boot);
    }
    if (cfg.call_forwarding_number !== undefined) {
      callForwardingNumber.value = cfg.call_forwarding_number;
    }
    if (cfg.call_forwarding_enabled !== undefined) {
      callForwardingEnabled.checked = Boolean(cfg.call_forwarding_enabled);
    }
    if (cfg.call_reject_enabled !== undefined) {
      callRejectEnabled.checked = Boolean(cfg.call_reject_enabled);
    }
    if (cfg.call_notify_admin_enabled !== undefined) {
      callNotifyAdminEnabled.checked = Boolean(cfg.call_notify_admin_enabled);
    }
    if (cfg.call_notify_admin_text) {
      callNotifyAdminText.value = cfg.call_notify_admin_text;
    }
    if (cfg.call_reply_caller_enabled !== undefined) {
      callReplyCallerEnabled.checked = Boolean(cfg.call_reply_caller_enabled);
    }
    if (cfg.call_reply_caller_text) {
      callReplyCallerText.value = cfg.call_reply_caller_text;
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
    checkGitHubRelease(stat.firmware_version);
  }
  if (stat.board_profile && telBoardProfile) {
    telBoardProfile.textContent = stat.board_profile;
  }
  if (stat.ota_pending !== undefined && telOta) {
    if (stat.ota_pending) {
      telOta.textContent = 'Venter på bekreftelse (Pending)';
      telOta.className = 'metric-val highlight';
    } else {
      telOta.textContent = 'Ingen ventende';
      telOta.className = 'metric-val';
    }
  }
  if (stat.live_operations !== undefined && stat.live_operations !== isLiveOperationsRunning) {
    updateOperationsState(Boolean(stat.live_operations));
  }
}

function formatLogLine(rawText) {
  const div = document.createElement('div');
  div.textContent = rawText;
  let text = div.innerHTML;

  text = text.replace(/\[main\]/gi, '<span class="log-tag log-tag-main">[main]</span>');
  text = text.replace(/\[wifi\]/gi, '<span class="log-tag log-tag-wifi">[wifi]</span>');
  text = text.replace(/\[modem\]/gi, '<span class="log-tag log-tag-modem">[modem]</span>');
  text = text.replace(/\[api\]/gi, '<span class="log-tag log-tag-api">[api]</span>');
  text = text.replace(/\[sms\]/gi, '<span class="log-tag log-tag-sms">[sms]</span>');
  text = text.replace(/\[ble\]/gi, '<span class="log-tag log-tag-ble">[ble]</span>');
  text = text.replace(/\[heartbeat\]/gi, '<span class="log-tag log-tag-heartbeat">[heartbeat]</span>');
  text = text.replace(/\b(error|failed|failure|exception)\b/gi, '<span class="log-tag log-tag-error">$&</span>');
  text = text.replace(/\b(warning|warn)\b/gi, '<span class="log-tag log-tag-warn">$&</span>');

  return `<span class="log-line">${text}</span>`;
}

function appendLogLine(lineText, timestamp = Date.now()) {
  const lineObj = { text: lineText, timestamp };
  allLogs.push(lineObj);
  if (allLogs.length > 500) {
    allLogs.shift();
  }

  logCounter.textContent = `${allLogs.length} linjer`;
  const timeStr = new Date(timestamp).toLocaleTimeString();
  logLastActivity.textContent = `Sist: ${timeStr}`;

  const matches = !filterQuery || lineText.toLowerCase().includes(filterQuery);
  if (matches) {
    if (terminalLogOutput.querySelector('.log-dim')) {
      terminalLogOutput.innerHTML = '';
    }
    const html = formatLogLine(lineText);
    terminalLogOutput.insertAdjacentHTML('beforeend', html);
    if (autoScroll) {
      terminalContainer.scrollTop = terminalContainer.scrollHeight;
    }
  }
}

function renderFilteredLogs() {
  terminalLogOutput.innerHTML = '';
  const filtered = allLogs.filter((l) => !filterQuery || l.text.toLowerCase().includes(filterQuery));
  if (filtered.length === 0) {
    terminalLogOutput.innerHTML = '<span class="log-line log-dim">Ingen linjer matcher filteret...</span>';
    return;
  }
  const frag = filtered.map((l) => formatLogLine(l.text)).join('');
  terminalLogOutput.innerHTML = frag;
  if (autoScroll) {
    terminalContainer.scrollTop = terminalContainer.scrollHeight;
  }
}

async function fetchInitialLogs() {
  try {
    const lines = await client.getLogs(50);
    if (lines && lines.length > 0) {
      terminalLogOutput.innerHTML = '';
      lines.forEach((l) => appendLogLine(l));
    }
  } catch (err) {
    console.warn('[Log] Kunne ikke hente historiske logger automatisk:', err);
  }
}

function updateOperationsState(running) {
  isLiveOperationsRunning = running;
  if (running) {
    operationsStatusPill.className = 'console-status-pill running';
    operationsStatusLabel.textContent = 'Kjører (Live)';
    btnOperationsIcon.textContent = '⏸';
    btnOperationsText.textContent = 'Pause drift';
  } else {
    operationsStatusPill.className = 'console-status-pill';
    operationsStatusLabel.textContent = 'Pauset';
    btnOperationsIcon.textContent = '▶';
    btnOperationsText.textContent = 'Start drift (Live)';
  }
}

async function toggleLiveOperations() {
  btnToggleOperations.disabled = true;
  try {
    if (isLiveOperationsRunning) {
      await client.stopOperations();
      updateOperationsState(false);
      showFeedback('Gateway-drift pauset.', 'info');
    } else {
      await client.startOperations();
      updateOperationsState(true);
      showFeedback('Live gateway-drift startet!', 'success');
    }
  } catch (err) {
    showFeedback(`Feil ved veksling av drift: ${err.message}`, 'error');
  } finally {
    btnToggleOperations.disabled = false;
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

  const payload = {
    wifi_ssid: ssid,
    snippen_api_base_url: url,
    outbox_poll_interval_sec: outboxSec,
    call_forwarding_number: callForwardingNumber.value.trim(),
    call_forwarding_enabled: callForwardingEnabled.checked,
    call_reject_enabled: callRejectEnabled.checked,
    call_notify_admin_enabled: callNotifyAdminEnabled.checked,
    call_reply_caller_enabled: callReplyCallerEnabled.checked,
  };

  const adminText = callNotifyAdminText.value.trim();
  if (adminText && adminText !== DEFAULT_CALL_NOTIFY_ADMIN_TEXT) {
    payload.call_notify_admin_text = adminText;
  }

  const callerText = callReplyCallerText.value.trim();
  if (callerText && callerText !== DEFAULT_CALL_REPLY_CALLER_TEXT) {
    payload.call_reply_caller_text = callerText;
  }

  if (inboxInterval) {
    payload.inbox_check_interval_sec = parseInt(inboxInterval.value, 10) || 30;
  }
  if (otaCheckOnBoot) {
    payload.ota_check_on_boot = otaCheckOnBoot.checked;
  }

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

btnToggleOperations.addEventListener('click', toggleLiveOperations);

btnClearLogs.addEventListener('click', async () => {
  allLogs = [];
  terminalLogOutput.innerHTML = '<span class="log-line log-dim">[logg tømt]</span>';
  logCounter.textContent = '0 linjer';
  try {
    if (client && client.isConnected) {
      await client.clearLogs();
    }
  } catch {
    // Ignore optional clearLogs error
  }
});

btnCopyLogs.addEventListener('click', async () => {
  if (allLogs.length === 0) {
    showFeedback('Ingen logger å kopiere.', 'info');
    return;
  }
  const fullText = allLogs.map((l) => l.text).join('\n');
  try {
    await navigator.clipboard.writeText(fullText);
    showFeedback(`Kopierte ${allLogs.length} logglinjer til utklippstavlen!`, 'success');
  } catch (err) {
    showFeedback(`Kunne ikke kopiere: ${err.message}`, 'error');
  }
});

autoscrollToggle.addEventListener('change', (e) => {
  autoScroll = e.target.checked;
  if (autoScroll) {
    terminalContainer.scrollTop = terminalContainer.scrollHeight;
  }
});

logFilterInput.addEventListener('input', (e) => {
  filterQuery = e.target.value.trim().toLowerCase();
  renderFilteredLogs();
});

function showOtaFeedback(msg, type = 'info') {
  if (!otaFeedback || !otaFeedbackText) return;
  otaFeedback.className = `feedback-box show ${type}`;
  otaFeedbackText.textContent = msg;
}

if (btnCheckOta) {
  btnCheckOta.addEventListener('click', async () => {
    try {
      spinnerCheckOta.classList.add('show');
      showOtaFeedback('Sjekker etter oppdateringer...', 'info');
      const customUrl = document.getElementById('input-ota-url')?.value.trim();
      const payload = {};
      if (customUrl) payload.url = customUrl;
      const res = await client.checkOta(payload);
      spinnerCheckOta.classList.remove('show');
      if (res && res.update_available) {
        showOtaFeedback(`Ny versjon tilgjengelig: v${res.version}! (${res.message || 'Klar til oppdatering'})`, 'success');
        if (btnStartOta) btnStartOta.style.display = 'inline-flex';
        if (otaBanner) {
          if (otaBannerVersion) otaBannerVersion.textContent = `v${res.version}`;
          const installedVer = (telVersion?.textContent || '').trim().replace(/^v/i, '') || '';
          if (otaBannerInstalled && installedVer) otaBannerInstalled.textContent = `v${installedVer}`;
          otaBanner.style.display = 'flex';
        }
      } else {
        showOtaFeedback(res?.message || 'Ingen ny firmware-oppdatering tilgjengelig.', 'info');
        if (btnStartOta) btnStartOta.style.display = 'none';
      }
    } catch (err) {
      spinnerCheckOta.classList.remove('show');
      showOtaFeedback(`Feil under sjekk av oppdatering: ${err.message}`, 'error');
    }
  });
}

if (btnStartOta) {
  btnStartOta.addEventListener('click', async () => {
    if (!confirm('Er du sikker på at du vil starte OTA-oppdatering? Gatewayen vil laste ned, verifisere og starte på nytt.')) {
      return;
    }
    try {
      spinnerStartOta.classList.add('show');
      showOtaFeedback('OTA-oppdatering startet... Gateway laster ned og installerer.', 'info');
      const customUrl = document.getElementById('input-ota-url')?.value.trim();
      const payload = {};
      if (customUrl) payload.url = customUrl;
      await client.startOta(payload);
      showOtaFeedback('Oppdatering igangsatt! Gateway restarter...', 'success');
    } catch (err) {
      spinnerStartOta.classList.remove('show');
      showOtaFeedback(`Feil under OTA-oppdatering: ${err.message}`, 'error');
    }
  });
}

function parseSemver(v) {
  return (v || '0.0.0').replace(/^v/i, '').split('.').map((n) => parseInt(n, 10) || 0);
}

function isNewerVersion(latest, current) {
  const [lMaj = 0, lMin = 0, lPat = 0] = parseSemver(latest);
  const [cMaj = 0, cMin = 0, cPat = 0] = parseSemver(current);
  if (lMaj !== cMaj) return lMaj > cMaj;
  if (lMin !== cMin) return lMin > cMin;
  return lPat > cPat;
}

let hasCheckedGitHub = false;

async function checkGitHubRelease(installedVersion) {
  if (!installedVersion || hasCheckedGitHub) return;
  hasCheckedGitHub = true;
  try {
    const resp = await fetch('https://api.github.com/repos/jonasfh/snippen-sms-service/releases/latest');
    if (!resp.ok) return;
    const release = await resp.json();
    const tagName = (release.tag_name || release.name || '').trim();
    const latestVer = tagName.replace(/^v/i, '');
    const cleanInstalled = installedVersion.trim().replace(/^v/i, '');

    if (isNewerVersion(latestVer, cleanInstalled)) {
      if (otaBanner) {
        if (otaBannerVersion) otaBannerVersion.textContent = `v${latestVer}`;
        if (otaBannerInstalled) otaBannerInstalled.textContent = `v${cleanInstalled}`;
        otaBanner.style.display = 'flex';
      }
      if (btnStartOta) btnStartOta.style.display = 'inline-flex';
    }
  } catch (err) {
    console.warn('[OTA] Kunne ikke hente nyeste release fra GitHub:', err);
  }
}

if (btnBannerUpgrade) {
  btnBannerUpgrade.addEventListener('click', () => {
    if (cardOta) {
      cardOta.scrollIntoView({ behavior: 'smooth' });
    }
    if (btnStartOta) {
      btnStartOta.click();
    }
  });
}

// Initialise
initClient();
