export interface NexusInitConfig {
  siteId: string;
  publicKey: string;
  endpoint?: string;
  autoCapture?: boolean;
  debug?: boolean;
}

export interface NexusEventPayload {
  eventName: string;
  properties?: Record<string, any>;
  userId?: string;
  traits?: Record<string, any>;
  consent?: Record<string, boolean>;
}

export interface WireEventPayload {
  event_id: string;
  tenant_id: string;
  site_id: string;
  type: string;
  occurred_at: string;
  actor: {
    type: "visitor" | "user" | "agent" | "system";
    id: string;
  };
  session_id?: string;
  source: string;
  data: Record<string, any>;
  consent?: Record<string, any>;
  trace_id?: string;
}

export class NexusSDK {
  private config: NexusInitConfig | null = null;
  private visitorId: string = "";
  private sessionId: string = "";
  private queue: WireEventPayload[] = [];
  private isFlushing: boolean = false;

  constructor() {
    this.initSession();
  }

  public init(config: NexusInitConfig): void {
    this.config = {
      endpoint: "http://localhost:8000",
      autoCapture: true,
      debug: false,
      ...config,
    };
    if (this.config.debug) {
      console.log("[NEXUS SDK] Initialized with siteId:", this.config.siteId);
    }
    if (this.config.autoCapture && typeof window !== "undefined") {
      this.attachAutoCapture();
    }
    this.flush();
  }

  private initSession(): void {
    if (typeof window === "undefined") return;
    try {
      let vid = localStorage.getItem("nexus_vid");
      if (!vid) {
        vid = "vis_" + Math.random().toString(36).substring(2, 15) + Date.now().toString(36);
        localStorage.setItem("nexus_vid", vid);
      }
      this.visitorId = vid;

      let sid = sessionStorage.getItem("nexus_sid");
      if (!sid) {
        sid = "ses_" + Math.random().toString(36).substring(2, 15) + Date.now().toString(36);
        sessionStorage.setItem("nexus_sid", sid);
      }
      this.sessionId = sid;
    } catch {
      this.visitorId = "vis_fallback_" + Math.random().toString(36).substring(2, 10);
      this.sessionId = "ses_fallback_" + Math.random().toString(36).substring(2, 10);
    }
  }

  public track(eventName: string, properties: Record<string, any> = {}, options: Partial<NexusEventPayload> = {}): void {
    if (!this.config) {
      console.warn("[NEXUS SDK] Track called before init. Event queued.");
    }

    const payload: WireEventPayload = {
      event_id: "evt_" + Math.random().toString(36).substring(2, 15) + Date.now().toString(36),
      tenant_id: "default", // Resolved by publicKey server-side
      site_id: this.config?.siteId || "unknown",
      type: eventName,
      occurred_at: new Date().toISOString(),
      actor: {
        type: options.userId ? "user" : "visitor",
        id: options.userId || this.visitorId,
      },
      session_id: this.sessionId,
      source: "web-sdk",
      data: {
        ...properties,
        ...(options.traits ? { traits: options.traits } : {}),
        url: typeof window !== "undefined" ? window.location.href : undefined,
        referrer: typeof document !== "undefined" ? document.referrer : undefined,
      },
      consent: options.consent || { analytics: true },
      trace_id: "trc_" + Math.random().toString(36).substring(2, 12),
    };

    this.queue.push(payload);
    this.flush();
  }

  public identify(userId: string, traits: Record<string, any> = {}): void {
    this.track("identify", traits, { userId, traits });
  }

  public async flush(): Promise<void> {
    if (!this.config || this.queue.length === 0 || this.isFlushing) {
      return;
    }
    this.isFlushing = true;
    const eventsToSend = [...this.queue];
    this.queue = [];

    for (const evt of eventsToSend) {
      try {
        const res = await fetch(`${this.config.endpoint}/v1/events`, {
          method: "POST",
          headers: {
            "Content-Type": "application/json",
            "X-Nexus-Public-Key": this.config.publicKey,
          },
          body: JSON.stringify(evt),
        });
        if (!res.ok && this.config.debug) {
          console.error("[NEXUS SDK] Failed to send event:", res.statusText);
        }
      } catch (err) {
        if (this.config.debug) {
          console.error("[NEXUS SDK] Network error sending event:", err);
        }
      }
    }
    this.isFlushing = false;
  }

  private attachAutoCapture(): void {
    if (typeof window === "undefined") return;
    this.track("page_view", {
      title: document.title,
      path: window.location.pathname,
    });
  }
}

export const Nexus = new NexusSDK();

if (typeof window !== "undefined") {
  (window as any).Nexus = Nexus;
}

export default Nexus;
