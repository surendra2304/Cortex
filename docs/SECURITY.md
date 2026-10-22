# CORTEX Security, Governance & Trust Model

## 1. Action Side-Effect Levels
Every tool registered in the **Universal Tool Bus** declares a strict side-effect level:

| Level | Definition | Execution Rule |
| :--- | :--- | :--- |
| **`READ`** | Safe read-only data query (e.g. analytics queries, profile lookups). | Automatically authorized. |
| **`SENSITIVE`** | External communications (e.g. email dispatch, SMS, CRM note updates). | Evaluated by Policy Engine; executed if confidence > 0.8. |
| **`HIGH_IMPACT`**| Financial mutations, account role changes, or experiment modifications. | **Requires Human Operator Approval** in Dashboard. |
| **`DANGEROUS`** | Irreversible destructive actions (data deletion, credential rotations). | **Blocked by default**; requires multi-party admin auth. |

---

## 2. Prompt Injection & Memory Trust Classifications
Per specification section 32, cognitive memory entries are tagged with immutable **Trust Labels**:
- **`system_fact`**: Verified configuration or hard policy rule.
- **`verified_telemetry`**: Cryptographically signed SDK/Webhook event payload.
- **`inferred_profile`**: Derived agent score or intent classification.
- **`untrusted_user_input`**: Raw user input (chat transcripts, form fields, email bodies).

> **Defense Rule**: Agents are explicitly instructed never to treat `untrusted_user_input` as instructions or authorization to bypass policy constraints.

---

## 3. Privacy by Design & Consent Gating
- **Pseudonymous Baseline**: Telemetry without explicit user consent remains strictly pseudonymous.
- **Identity Merging**: Anonymous visitors are stitched into profiles and promoted to leads only when consent is granted (`consent.analytics = true`).
- **Consent Revocation**: Calling `Cortex.consent(false)` in the browser SDK immediately flushes local queues and halts all auto-capture event tracking.
