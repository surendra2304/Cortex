export interface NexusInitConfig {
  siteId: string;
  publicKey: string;
  endpoint?: string;
  autoCapture?: boolean;
  debug?: boolean;
  batchSize?: number;
  flushIntervalMs?: number;
  maxQueueSize?: number;
  tenantId?: string;
}

export interface WireEventPayload {
  event_id: string;
  tenant_id: string;
  site_id: string;
  type: string;
  occurred_at: string;
  actor: { type: 'visitor' | 'user' | 'agent' | 'system'; id: string };
  session_id: string;
  source: string;
  data: Record<string, any>;
  consent: Record<string, any>;
  trace_id: string;
}

const SESSION_TIMEOUT_MS = 30 * 60 * 1000; // 30 minutes
const STORAGE_VID = 'nexus_vid';
const STORAGE_SID = 'nexus_sid';
const STORAGE_LAST_ACTIVE = 'nexus_last_active';
const STORAGE_CONSENT = 'nexus_consent';
const STORAGE_UID = 'nexus_uid';

function genId(prefix: string): string {
  return prefix + '_' + Math.random().toString(36).slice(2, 11) + Date.now().toString(36);
}

function parseUtm(search: string): Record<string, string> {
  if (!search) return {};
  const params = new URLSearchParams(search);
  const result: Record<string, string> = {};
  for (const key of ['utm_source', 'utm_medium', 'utm_campaign', 'utm_content', 'utm_term']) {
    const val = params.get(key);
    if (val) result[key] = val;
  }
  return result;
}

function getDeviceType(): string {
  if (typeof navigator === 'undefined') return 'unknown';
  return /Mobi|Android/i.test(navigator.userAgent) ? 'mobile' : 'desktop';
}

export class NexusSDK {
  private config: Required<NexusInitConfig> | null = null;
  private visitorId = '';
  private sessionId = '';
  private userId: string | null = null;
  private consentGranted = true;
  private queue: WireEventPayload[] = [];
  private isFlushing = false;
  private flushTimer: any = null;

  constructor() {
    this._initIds();
    this._loadConsent();
  }

  public init(config: NexusInitConfig): void {
    this.config = {
      endpoint: 'http://localhost:8000',
      autoCapture: true,
      debug: false,
      batchSize: 20,
      flushIntervalMs: 3000,
      maxQueueSize: 100,
      tenantId: 'default',
      ...config,
    };

    this._log('Initialized', { siteId: this.config.siteId, consentGranted: this.consentGranted });

    if (this.flushTimer) clearInterval(this.flushTimer);
    this.flushTimer = setInterval(() => this.flush(), this.config.flushIntervalMs);

    if (this.config.autoCapture && typeof window !== 'undefined') {
      this._attachAutoCapture();
    }

    this.flush();
  }

  public consent(granted: boolean): void {
    this.consentGranted = granted;
    try {
      localStorage.setItem(STORAGE_CONSENT, granted ? 'true' : 'false');
    } catch {}
    this._log('Consent updated', { granted });
    if (!granted) {
      this.queue = [];
      this._log('Queue cleared due to consent revocation');
    }
  }

  public track(
    eventType: string,
    properties: Record<string, any> = {},
    actorOverride?: { type: 'visitor' | 'user'; id: string }
  ): void {
    if (!this.consentGranted) {
      this._log('track() blocked — consent not granted', { eventType });
      return;
    }

    this._refreshSession();

    const actorType = this.userId ? 'user' : 'visitor';
    const actorId = this.userId || this.visitorId;

    const payload: WireEventPayload = {
      event_id: genId('evt'),
      tenant_id: this.config?.tenantId || 'default',
      site_id: this.config?.siteId || 'unknown',
      type: eventType,
      occurred_at: new Date().toISOString(),
      actor: actorOverride || { type: actorType, id: actorId },
      session_id: this.sessionId,
      source: 'web-sdk',
      data: {
        ...properties,
        url: typeof window !== 'undefined' ? window.location.href : undefined,
        referrer: typeof document !== 'undefined' ? document.referrer : undefined,
      },
      consent: { analytics: this.consentGranted },
      trace_id: genId('trc'),
    };

    if (this.queue.length >= (this.config?.maxQueueSize || 100)) {
      this.queue.shift();
      this._log('Max queue size reached — dropping oldest event');
    }

    this.queue.push(payload);
    this._log('Event queued', { type: eventType, queueSize: this.queue.length });

    if (this.config && this.queue.length >= this.config.batchSize) {
      this.flush();
    }
  }

  public identify(userId: string, traits: Record<string, any> = {}): void {
    if (!this.consentGranted) {
      this._log('identify() blocked — consent not granted');
      return;
    }
    this.userId = userId;
    try { localStorage.setItem(STORAGE_UID, userId); } catch {}
    this.track('identify', { traits, userId }, { type: 'user', id: userId });
    this._log('Identity set', { userId });
  }

  public async flush(): Promise<void> {
    if (!this.config || this.queue.length === 0 || this.isFlushing) return;
    if (!this.consentGranted) {
      this.queue = [];
      return;
    }

    this.isFlushing = true;
    const batch = this.queue.splice(0, this.config.batchSize);
    this._log('Flushing batch', { size: batch.length });

    const success = await this._sendBatch(batch);
    if (!success) {
      const combined = [...batch, ...this.queue].slice(0, this.config.maxQueueSize);
      this.queue = combined;
      this._log('Batch failed — events re-enqueued', { queueSize: this.queue.length });
    } else {
      this._log('Batch flushed successfully', { size: batch.length });
    }
    this.isFlushing = false;
  }

  public getVisitorId(): string { return this.visitorId; }
  public getSessionId(): string { return this.sessionId; }
  public getQueueSize(): number { return this.queue.length; }
  public isConsentGranted(): boolean { return this.consentGranted; }

  private async _sendBatch(events: WireEventPayload[]): Promise<boolean> {
    if (!this.config) return false;
    const endpoint = this.config.endpoint.replace(/\/$/, '');

    for (let attempt = 0; attempt <= 3; attempt++) {
      try {
        if (attempt > 0) {
          await new Promise(r => setTimeout(r, Math.pow(2, attempt - 1) * 1000));
        }
        const res = await fetch(`${endpoint}/v1/events/batch`, {
          method: 'POST',
          headers: {
            'Content-Type': 'application/json',
            'X-Nexus-Public-Key': this.config.publicKey,
          },
          body: JSON.stringify(events),
        });
        if (res.ok) return true;
        if (res.status === 404) break;
        if (res.status >= 500 && attempt < 3) continue;
        this._log('Batch endpoint error', { status: res.status });
        break;
      } catch (err) {
        if (attempt < 3) continue;
        this._log('Network error sending batch', { err });
      }
    }

    let allOk = true;
    for (const evt of events) {
      try {
        const res = await fetch(`${endpoint}/v1/events`, {
          method: 'POST',
          headers: {
            'Content-Type': 'application/json',
            'X-Nexus-Public-Key': this.config.publicKey,
          },
          body: JSON.stringify(evt),
        });
        if (!res.ok) allOk = false;
      } catch {
        allOk = false;
      }
    }
    return allOk;
  }

  private _initIds(): void {
    if (typeof window === 'undefined') {
      this.visitorId = genId('vis');
      this.sessionId = genId('ses');
      return;
    }
    try {
      let vid = localStorage.getItem(STORAGE_VID);
      if (!vid) { vid = genId('vis'); localStorage.setItem(STORAGE_VID, vid); }
      this.visitorId = vid;

      const uid = localStorage.getItem(STORAGE_UID);
      if (uid) this.userId = uid;

      this._refreshSession();
    } catch {
      this.visitorId = genId('vis');
      this.sessionId = genId('ses');
    }
  }

  private _refreshSession(): void {
    if (typeof window === 'undefined') return;
    try {
      const lastActive = parseInt(sessionStorage.getItem(STORAGE_LAST_ACTIVE) || '0', 10);
      const now = Date.now();
      const sid = sessionStorage.getItem(STORAGE_SID);

      if (!sid || (lastActive > 0 && now - lastActive > SESSION_TIMEOUT_MS)) {
        const newSid = genId('ses');
        sessionStorage.setItem(STORAGE_SID, newSid);
        this.sessionId = newSid;
        this._log('New session started', { sessionId: newSid });
      } else {
        this.sessionId = sid;
      }
      sessionStorage.setItem(STORAGE_LAST_ACTIVE, String(now));
    } catch {
      if (!this.sessionId) this.sessionId = genId('ses');
    }
  }

  private _loadConsent(): void {
    try {
      const stored = localStorage.getItem(STORAGE_CONSENT);
      this.consentGranted = stored === null ? true : stored === 'true';
    } catch {
      this.consentGranted = true;
    }
  }

  private _attachAutoCapture(): void {
    if (!this.consentGranted) return;
    this._trackPageView();
    window.addEventListener('popstate', () => this._trackPageView());
    window.addEventListener('hashchange', () => this._trackPageView());
  }

  private _trackPageView(): void {
    if (!this.consentGranted) return;
    const utms = typeof window !== 'undefined' ? parseUtm(window.location.search) : {};
    this.track('page_view', {
      title: typeof document !== 'undefined' ? document.title : '',
      path: typeof window !== 'undefined' ? window.location.pathname : '',
      referrer: typeof document !== 'undefined' ? document.referrer : '',
      device_type: getDeviceType(),
      ...utms,
    });
  }

  private _log(message: string, data?: Record<string, any>): void {
    if (this.config?.debug) {
      console.log(`[NEXUS SDK] ${message}`, data || '');
    }
  }
}

export const Nexus = new NexusSDK();

if (typeof window !== 'undefined') {
  (window as any).Nexus = Nexus;
}

export default Nexus;
