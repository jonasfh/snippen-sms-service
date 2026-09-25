/**
 * Web Bluetooth (BLE) client for Snippen SMS Gateway (Lilygo ESP32).
 *
 * Implements GATT client communication for provisioning and telemetry
 * matching the GATT server defined in firmware/ble_config.py.
 */

// 128-bit UUID constants matching firmware/ble_config.py
export const SERVICE_UUID = '6e400001-b5a3-f393-e0a9-e50e24dcca9e';
export const CHAR_CONFIG_UUID = '6e400002-b5a3-f393-e0a9-e50e24dcca9e';
export const CHAR_STATUS_UUID = '6e400003-b5a3-f393-e0a9-e50e24dcca9e';
export const CHAR_COMMAND_UUID = '6e400004-b5a3-f393-e0a9-e50e24dcca9e';
export const CHAR_LOGS_UUID = '6e400005-b5a3-f393-e0a9-e50e24dcca9e';
export const DEVICE_NAME_PREFIX = 'Snippen-SMS';

/**
 * Check if the current browser environment supports the Web Bluetooth API.
 * @returns {boolean}
 */
export function isWebBluetoothSupported() {
  return typeof navigator !== 'undefined' && 'bluetooth' in navigator && typeof navigator.bluetooth.requestDevice === 'function';
}

/**
 * Mask an authentication token for safe display.
 * @param {string} token
 * @returns {string}
 */
export function maskToken(token) {
  if (!token) return '';
  if (token.length <= 6) return '******';
  return `${token.slice(0, 2)}****${token.slice(-2)}`;
}

/**
 * Encode an object to UTF-8 JSON Uint8Array bytes.
 * @param {object} obj
 * @returns {Uint8Array}
 */
export function encodeJson(obj) {
  const jsonStr = JSON.stringify(obj);
  return new TextEncoder().encode(jsonStr);
}

/**
 * Decode a DataView or ArrayBuffer to a parsed JSON object.
 * @param {DataView|ArrayBuffer} buffer
 * @returns {any}
 */
export function decodeJson(buffer) {
  const dataView = buffer instanceof DataView ? buffer : new DataView(buffer);
  const text = new TextDecoder('utf-8').decode(dataView);
  return JSON.parse(text);
}

/**
 * Snippen Web Bluetooth GATT Client.
 * Emits standard EventTarget events:
 *  - 'connected': { detail: { deviceName, deviceId } }
 *  - 'disconnected': { detail: { deviceName } }
 *  - 'status': { detail: statusObject }
 *  - 'config': { detail: configObject }
 *  - 'error': { detail: Error }
 */
export class SnippenBLEClient extends EventTarget {
  constructor() {
    super();
    this.device = null;
    this.server = null;
    this.service = null;
    this.charConfig = null;
    this.charStatus = null;
    this.charCommand = null;
    this.charLogs = null;
    this.isConnected = false;
    this._pendingCommands = new Map(); // cmdName -> { resolve, reject, timeoutId }

    this._onDisconnectedBound = this._handleDisconnected.bind(this);
    this._onStatusNotificationBound = this._handleStatusNotification.bind(this);
    this._onCommandNotificationBound = this._handleCommandNotification.bind(this);
    this._onLogNotificationBound = this._handleLogNotification.bind(this);
  }

  /**
   * Request device discovery and connect to GATT server.
   * @param {object} [options]
   * @returns {Promise<{ deviceName: string, deviceId: string }>}
   */
  async connect(options = {}) {
    if (!isWebBluetoothSupported()) {
      throw new Error(
        'Web Bluetooth is not supported in this browser. Please use Chrome on Android, Chrome/Edge on Desktop, or a WebBLE browser on iOS.'
      );
    }

    if (this.isConnected) {
      return { deviceName: this.device.name, deviceId: this.device.id };
    }

    const filters = options.filters || [
      { namePrefix: DEVICE_NAME_PREFIX },
      { services: [SERVICE_UUID] },
    ];

    try {
      this.device = await navigator.bluetooth.requestDevice({
        filters,
        optionalServices: [SERVICE_UUID],
      });

      this.device.addEventListener('gattserverdisconnected', this._onDisconnectedBound);

      this.server = await this.device.gatt.connect();
      this.service = await this.server.getPrimaryService(SERVICE_UUID);

      // Discover characteristics
      this.charConfig = await this.service.getCharacteristic(CHAR_CONFIG_UUID);
      this.charStatus = await this.service.getCharacteristic(CHAR_STATUS_UUID);
      this.charCommand = await this.service.getCharacteristic(CHAR_COMMAND_UUID);
      try {
        this.charLogs = await this.service.getCharacteristic(CHAR_LOGS_UUID);
      } catch {
        this.charLogs = null;
      }

      // Subscribe to status notifications
      await this.charStatus.startNotifications();
      this.charStatus.addEventListener('characteristicvaluechanged', this._onStatusNotificationBound);

      // Subscribe to command notifications
      await this.charCommand.startNotifications();
      this.charCommand.addEventListener('characteristicvaluechanged', this._onCommandNotificationBound);

      // Subscribe to log notifications if available
      if (this.charLogs) {
        await this.charLogs.startNotifications();
        this.charLogs.addEventListener('characteristicvaluechanged', this._onLogNotificationBound);
      }

      this.isConnected = true;

      const deviceDetails = {
        deviceName: this.device.name || DEVICE_NAME_PREFIX,
        deviceId: this.device.id,
      };

      this.dispatchEvent(new CustomEvent('connected', { detail: deviceDetails }));
      return deviceDetails;
    } catch (err) {
      this._cleanup();
      this.dispatchEvent(new CustomEvent('error', { detail: err }));
      throw err;
    }
  }

  /**
   * Disconnect from GATT server.
   */
  async disconnect() {
    if (this.device && this.device.gatt && this.device.gatt.connected) {
      this.device.gatt.disconnect();
    }
    this._cleanup();
  }

  /**
   * Read active configuration from the Config characteristic.
   * @returns {Promise<object>}
   */
  async readConfig() {
    this._ensureConnected();
    try {
      const dataView = await this.charConfig.readValue();
      const config = decodeJson(dataView);
      this.dispatchEvent(new CustomEvent('config', { detail: config }));
      return config;
    } catch (err) {
      this.dispatchEvent(new CustomEvent('error', { detail: err }));
      throw err;
    }
  }

  /**
   * Write updated configuration to the Config characteristic.
   * @param {object} configObj
   * @returns {Promise<boolean>}
   */
  async writeConfig(configObj) {
    this._ensureConnected();
    try {
      const payload = encodeJson(configObj);
      if (typeof this.charConfig.writeValueWithResponse === 'function') {
        await this.charConfig.writeValueWithResponse(payload);
      } else {
        await this.charConfig.writeValue(payload);
      }
      return true;
    } catch (err) {
      this.dispatchEvent(new CustomEvent('error', { detail: err }));
      throw err;
    }
  }

  /**
   * Send a JSON command and await matching notification response.
   * @param {object} cmdPayload - Must include { cmd: "..." }
   * @param {number} [timeoutMs=20000]
   * @returns {Promise<object>}
   */
  async sendCommand(cmdPayload, timeoutMs = 20000) {
    this._ensureConnected();
    const cmdName = cmdPayload.cmd;
    if (!cmdName) {
      throw new Error('Command payload must specify a "cmd" field');
    }

    return new Promise((resolve, reject) => {
      const timeoutId = setTimeout(() => {
        this._pendingCommands.delete(cmdName);
        reject(new Error(`Command '${cmdName}' timed out after ${timeoutMs}ms`));
      }, timeoutMs);

      this._pendingCommands.set(cmdName, { resolve, reject, timeoutId });

      const payload = encodeJson(cmdPayload);
      const writePromise = typeof this.charCommand.writeValueWithResponse === 'function'
        ? this.charCommand.writeValueWithResponse(payload)
        : this.charCommand.writeValue(payload);

      writePromise.catch((err) => {
        clearTimeout(timeoutId);
        this._pendingCommands.delete(cmdName);
        reject(err);
      });
    });
  }

  /**
   * Trigger WiFi scan and await list of networks.
   * @param {number} [timeoutMs=15000]
   * @returns {Promise<Array<{ ssid: string, rssi: number, auth: number }>>}
   */
  async scanWifi(timeoutMs = 15000) {
    const res = await this.sendCommand({ cmd: 'SCAN_WIFI' }, timeoutMs);
    return res.networks || [];
  }

  /**
   * Test WiFi credentials and await connection status.
   * @param {string} ssid
   * @param {string} password
   * @param {number} [timeoutMs=20000]
   * @returns {Promise<{ connected: boolean, ip?: string, status: string, message?: string }>}
   */
  async testWifi(ssid, password, timeoutMs = 20000) {
    return await this.sendCommand(
      {
        cmd: 'TEST_WIFI',
        wifi_ssid: ssid,
        wifi_password: password,
      },
      timeoutMs
    );
  }

  /**
   * Apply settings and tell ESP32 to exit provisioning mode.
   * @param {number} [timeoutMs=5000]
   * @returns {Promise<object>}
   */
  async applyAndExit(timeoutMs = 5000) {
    let res;
    try {
      res = await this.sendCommand({ cmd: 'APPLY_AND_EXIT' }, timeoutMs);
    } catch {
      // In some firmware versions the device may cut BLE immediately upon reboot
      res = { cmd: 'APPLY_AND_EXIT', status: 'ok' };
    }
    await this.disconnect();
    return res;
  }

  /**
   * Start normal gateway operations while keeping BLE connected for live logging.
   * @param {number} [timeoutMs=20000]
   * @returns {Promise<object>}
   */
  async startOperations(timeoutMs = 20000) {
    return await this.sendCommand({ cmd: 'START_OPERATIONS' }, timeoutMs);
  }

  /**
   * Pause normal gateway operations while keeping BLE connected for configuration.
   * @param {number} [timeoutMs=20000]
   * @returns {Promise<object>}
   */
  async stopOperations(timeoutMs = 20000) {
    return await this.sendCommand({ cmd: 'STOP_OPERATIONS' }, timeoutMs);
  }

  /**
   * Fetch historical log lines from gateway in-memory buffer.
   * @param {number} [count=20]
   * @param {number} [timeoutMs=15000]
   * @returns {Promise<string[]>}
   */
  async getLogs(count = 20, timeoutMs = 15000) {
    const res = await this.sendCommand({ cmd: 'GET_LOGS', count }, timeoutMs);
    return res.lines || [];
  }

  /**
   * Clear historical log lines on gateway in-memory buffer.
   * @param {number} [timeoutMs=5000]
   * @returns {Promise<object>}
   */
  async clearLogs(timeoutMs = 5000) {
    return await this.sendCommand({ cmd: 'CLEAR_LOGS' }, timeoutMs);
  }

  _handleStatusNotification(event) {
    let rawText = '';
    try {
      const dataView = event.target.value instanceof DataView ? event.target.value : new DataView(event.target.value);
      rawText = new TextDecoder('utf-8').decode(dataView);
      const status = JSON.parse(rawText);
      this.dispatchEvent(new CustomEvent('status', { detail: status }));
    } catch (err) {
      console.warn('[SnippenBLE] Failed to parse status notification:', err, 'Raw length:', rawText.length, 'Text:', rawText);
    }
  }

  _handleCommandNotification(event) {
    let rawText = '';
    try {
      const dataView = event.target.value instanceof DataView ? event.target.value : new DataView(event.target.value);
      rawText = new TextDecoder('utf-8').decode(dataView);
      const res = JSON.parse(rawText);
      const cmdName = res.cmd;
      if (cmdName && this._pendingCommands.has(cmdName)) {
        const { resolve, timeoutId } = this._pendingCommands.get(cmdName);
        clearTimeout(timeoutId);
        this._pendingCommands.delete(cmdName);
        resolve(res);
      }
    } catch (err) {
      console.warn('[SnippenBLE] Failed to parse command response:', err, 'Raw length:', rawText.length, 'Text:', rawText);
    }
  }

  _handleLogNotification(event) {
    try {
      const dataView = event.target.value instanceof DataView ? event.target.value : new DataView(event.target.value);
      const line = new TextDecoder('utf-8').decode(dataView);
      this.dispatchEvent(new CustomEvent('log', { detail: { line, timestamp: Date.now() } }));
    } catch (err) {
      console.warn('[SnippenBLE] Failed to parse log notification:', err);
    }
  }

  _handleDisconnected() {
    const deviceName = this.device ? this.device.name : 'Unknown';
    this._cleanup();
    this.dispatchEvent(new CustomEvent('disconnected', { detail: { deviceName } }));
  }

  _ensureConnected() {
    if (!this.isConnected || !this.server || !this.server.connected) {
      throw new Error('Not connected to Snippen SMS Gateway');
    }
  }

  _cleanup() {
    this.isConnected = false;
    for (const [, { reject, timeoutId }] of this._pendingCommands) {
      clearTimeout(timeoutId);
      reject(new Error('Connection closed while command was pending'));
    }
    this._pendingCommands.clear();

    if (this.charStatus) {
      this.charStatus.removeEventListener('characteristicvaluechanged', this._onStatusNotificationBound);
    }
    if (this.charCommand) {
      this.charCommand.removeEventListener('characteristicvaluechanged', this._onCommandNotificationBound);
    }
    if (this.charLogs) {
      this.charLogs.removeEventListener('characteristicvaluechanged', this._onLogNotificationBound);
    }
    if (this.device) {
      this.device.removeEventListener('gattserverdisconnected', this._onDisconnectedBound);
    }

    this.server = null;
    this.service = null;
    this.charConfig = null;
    this.charStatus = null;
    this.charCommand = null;
    this.charLogs = null;
  }
}

/**
 * Mock BLE Client for offline preview and automated browser/unit testing.
 */
export class MockSnippenBLEClient extends EventTarget {
  constructor() {
    super();
    this.isConnected = false;
    this.mockConfig = {
      wifi_ssid: 'Snippen-Local',
      snippen_api_base_url: 'https://snippen.example.com/api',
      snippen_api_token: 'se****99',
      outbox_poll_interval_sec: 5,
      inbox_check_interval_sec: 5,
      call_forwarding_number: '+4792830575',
      call_forwarding_enabled: true,
      call_reject_enabled: true,
      call_notify_admin_enabled: true,
      call_reply_caller_enabled: true,
      call_reply_caller_text: 'Dette nummeret er en automatisert SMS-sentral for Snippen Booking og tar ikke imot samtaler. Send SMS eller ring leieansvarlig på 92830575.',
      call_notify_admin_text: 'Ubesvart anrop til Snippen SMS-gateway fra {caller}.',
    };
    this.mockNetworks = [
      { ssid: 'Snippen-Local', rssi: -54, auth: 3 },
      { ssid: 'Snippen-Guest', rssi: -68, auth: 2 },
      { ssid: 'Neighbor-WiFi', rssi: -82, auth: 4 },
    ];
    this.statusInterval = null;
    this.liveInterval = null;
    this.mockLogs = [
      '[main] Initializing Snippen SMS Gateway application...',
      '[boot] Configuring UART1 at 115200 baud (TX: Pin 26, RX: Pin 25)...',
      '[main] Modem UART connection verified.',
      '[modem] SIM7670E online, signal CSQ: 22 (-69 dBm)',
      '[wifi] Connected to Snippen-Local (IP: 192.168.1.142)',
      '[ble] Advertising as \'Snippen-SMS-BA5E\' on UUID 6e400001-b5a3-f393-e0a9-e50e24dcca9e',
      '[ble] Central connected (handle: 1)',
    ];
  }

  _emitMockLog(line) {
    this.mockLogs.push(line);
    if (this.mockLogs.length > 100) {
      this.mockLogs.shift();
    }
    this.dispatchEvent(new CustomEvent('log', { detail: { line, timestamp: Date.now() } }));
  }

  async connect() {
    await new Promise((r) => setTimeout(r, 400));
    this.isConnected = true;
    const details = { deviceName: 'Snippen-SMS-BA5E (Mock)', deviceId: 'mock-device-id' };
    this.dispatchEvent(new CustomEvent('connected', { detail: details }));

    // Emit initial status
    this.dispatchEvent(
      new CustomEvent('status', {
        detail: {
          status: 'ready',
          device: 'Snippen-SMS-BA5E',
          wifi_connected: true,
          live_operations: false,
          ip: '192.168.1.142',
          wifi_rssi: -58,
          cellular_csq: 22,
          cellular_rssi_dbm: -69,
          firmware_version: '1.2.0',
        },
      })
    );

    // Emit startup logs to listener
    setTimeout(() => {
      this.mockLogs.forEach((line) => {
        this.dispatchEvent(new CustomEvent('log', { detail: { line, timestamp: Date.now() } }));
      });
    }, 100);

    return details;
  }

  async disconnect() {
    if (this.statusInterval) clearInterval(this.statusInterval);
    if (this.liveInterval) clearInterval(this.liveInterval);
    this.isConnected = false;
    this.dispatchEvent(new CustomEvent('disconnected', { detail: { deviceName: 'Snippen-SMS-BA5E (Mock)' } }));
  }

  async readConfig() {
    if (!this.isConnected) throw new Error('Not connected');
    await new Promise((r) => setTimeout(r, 200));
    const cfg = { ...this.mockConfig };
    this.dispatchEvent(new CustomEvent('config', { detail: cfg }));
    return cfg;
  }

  async writeConfig(cfg) {
    if (!this.isConnected) throw new Error('Not connected');
    await new Promise((r) => setTimeout(r, 300));
    this.mockConfig = { ...this.mockConfig, ...cfg };
    if (cfg.snippen_api_token) {
      this.mockConfig.snippen_api_token = maskToken(cfg.snippen_api_token);
    }
    return true;
  }

  async sendCommand(cmdPayload) {
    if (!this.isConnected) throw new Error('Not connected');
    await new Promise((r) => setTimeout(r, 250));
    const cmd = cmdPayload.cmd;

    if (cmd === 'SCAN_WIFI') {
      return { cmd: 'SCAN_WIFI', status: 'ok', networks: this.mockNetworks };
    }
    if (cmd === 'TEST_WIFI') {
      return {
        cmd: 'TEST_WIFI',
        status: 'ok',
        connected: true,
        ssid: cmdPayload.wifi_ssid,
        ip: '192.168.1.142',
      };
    }
    if (cmd === 'START_OPERATIONS') {
      if (this.liveInterval) clearInterval(this.liveInterval);
      this._emitMockLog('[main] Live gateway operations started over BLE.');
      let tick = 0;
      this.liveInterval = setInterval(() => {
        tick++;
        const samples = [
          '[api] Polling outbox from https://snippen.example.com/api/sms/outbox',
          '[api] Outbox check complete: 0 pending messages',
          '[modem] Checking SMS inbox (AT+CMGL="REC UNREAD")...',
          '[modem] Inbox check complete: 0 unread messages',
          '[heartbeat] Gateway healthy (WiFi RSSI: -54 dBm, 4G: CSQ 22)',
          tick % 3 === 0
            ? '[sms] Outbound SMS delivered to recipient +4791234567 (ref #142)'
            : '[main] Gateway tick cycle complete (heap 145KB free)',
        ];
        const line = samples[Math.floor(Math.random() * samples.length)];
        this._emitMockLog(line);
      }, 2500);
      return { cmd: 'START_OPERATIONS', status: 'ok', live_operations: true };
    }
    if (cmd === 'STOP_OPERATIONS') {
      if (this.liveInterval) {
        clearInterval(this.liveInterval);
        this.liveInterval = null;
      }
      this._emitMockLog('[main] Live gateway operations paused over BLE.');
      return { cmd: 'STOP_OPERATIONS', status: 'ok', live_operations: false };
    }
    if (cmd === 'GET_LOGS') {
      const count = cmdPayload.count || 50;
      return { cmd: 'GET_LOGS', status: 'ok', lines: this.mockLogs.slice(-count) };
    }
    if (cmd === 'CLEAR_LOGS') {
      this.mockLogs = [];
      return { cmd: 'CLEAR_LOGS', status: 'ok' };
    }
    if (cmd === 'APPLY_AND_EXIT') {
      setTimeout(() => this.disconnect(), 100);
      return { cmd: 'APPLY_AND_EXIT', status: 'ok' };
    }
    return { cmd, status: 'unknown_command' };
  }

  async scanWifi() {
    const res = await this.sendCommand({ cmd: 'SCAN_WIFI' });
    return res.networks;
  }

  async testWifi(ssid, password) {
    return await this.sendCommand({ cmd: 'TEST_WIFI', wifi_ssid: ssid, wifi_password: password });
  }

  async applyAndExit() {
    return await this.sendCommand({ cmd: 'APPLY_AND_EXIT' });
  }

  async startOperations() {
    return await this.sendCommand({ cmd: 'START_OPERATIONS' });
  }

  async stopOperations() {
    return await this.sendCommand({ cmd: 'STOP_OPERATIONS' });
  }

  async getLogs(count = 50) {
    const res = await this.sendCommand({ cmd: 'GET_LOGS', count });
    return res.lines || [];
  }

  async clearLogs() {
    return await this.sendCommand({ cmd: 'CLEAR_LOGS' });
  }
}
