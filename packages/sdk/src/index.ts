export interface NexusEvent {
  eventId: string;
  tenantId: string;
  siteId: string;
  type: string;
  occurredAt: string;
  actor: { type: string; id: string };
  sessionId?: string;
  source: string;
  data: Record<string, any>;
  consent?: Record<string, any>;
  traceId?: string;
}

export class NexusClient {
  constructor(private apiKey: string, private endpoint: string = "https://api.nexus.dev") {}

  public async track(event: Omit<NexusEvent, "eventId" | "occurredAt">): Promise<void> {
    // SDK client tracking implementation
  }
}
