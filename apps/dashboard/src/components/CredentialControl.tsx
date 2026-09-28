"use client";

import { FormEvent, useEffect, useState } from "react";
import { getOperatorToken } from "@/lib/api";

export default function CredentialControl() {
  const [configured, setConfigured] = useState(false);
  const [open, setOpen] = useState(false);
  const [draft, setDraft] = useState("");

  useEffect(() => {
    setConfigured(Boolean(getOperatorToken()));
  }, []);

  const openDialog = () => {
    setDraft(getOperatorToken());
    setOpen(true);
  };

  const save = (event: FormEvent) => {
    event.preventDefault();
    const token = draft.trim().replace(/^Bearer\s+/i, "");
    if (token) window.localStorage.setItem("cortex_operator_token", token);
    else window.localStorage.removeItem("cortex_operator_token");
    window.location.reload();
  };

  return (
    <>
      <button className="credential-button" type="button" onClick={openDialog} aria-label="Configure CORTEX API credentials">
        <span className={`credential-dot${configured ? " configured" : ""}`} />
        <span>{configured ? "Credentials set" : "Add API token"}</span>
      </button>
      {open && (
        <div className="modal-backdrop" role="presentation" onMouseDown={(event) => { if (event.target === event.currentTarget) setOpen(false); }}>
          <form className="credential-dialog" onSubmit={save} role="dialog" aria-modal="true" aria-labelledby="credential-title">
            <button className="dialog-close" type="button" aria-label="Close" onClick={() => setOpen(false)}>×</button>
            <span className="eyebrow">WORKSPACE ACCESS</span>
            <h2 id="credential-title">Connect your API token</h2>
            <p>Paste a CORTEX operator JWT. It stays in this browser and is sent as a Bearer token. Leave blank to remove it.</p>
            <label htmlFor="operator-token">Operator token</label>
            <input id="operator-token" autoComplete="off" type="password" value={draft} onChange={(event) => setDraft(event.target.value)} placeholder="eyJ…" />
            <div className="dialog-actions">
              <button type="button" className="button-quiet" onClick={() => setOpen(false)}>Cancel</button>
              <button type="submit" className="button-primary">Save token</button>
            </div>
          </form>
        </div>
      )}
    </>
  );
}
