# 🏛️ SYSTEM MANIFEST — Cortex Autonomous Web Operations

> **Official Subsystem Name:** Cortex  
> **Role in Ecosystem:** Autonomous Web Operations, Real-Time Visitor Telemetry & Lead Qualification  
> **Repository:** [surendra2304/Cortex](https://github.com/surendra2304/Cortex) (Branch: main)  
> **Workspace Path:** d:\FRIDAY Universe\Cortex  

---

## ☁️ 1. Configured service (runtime unverified)

| Attribute | Repository configuration |
| :--- | :--- |
| **Configured Service URL (deployment unverified)** | [https://cortex-0m7c.onrender.com](https://cortex-0m7c.onrender.com) |
| **Health Check Endpoint** | https://cortex-0m7c.onrender.com/health |
| **API key variable (keep value in secret environment)** | CORTEX_API_KEY=<configure in secret environment> |
| **Authentication Header** | Authorization: Bearer <configured API key> / X-API-KEY: <configured API key> |
| **Configured database topology (runtime unverified)** | SQLite State DB / Connected to Memora |
| **Configured database URL or namespace (not a secret)** | sqlite+aiosqlite:///./data/cortex.db |
| **Configured host (plan, region, and runtime unverified)** | Render service configured (current plan, region, and deployment unverified) |

---

## 🎯 2. Purpose & Responsibilities

### What Cortex IS:
* Cortex is an autonomous digital operations layer for live websites and web applications. It tracks real-time visitor traffic, calculates lead intent scores, orchestrates conversion experiments, and manages web health.

### What Cortex DOES:
* Operates as the **Autonomous Web Operations, Real-Time Visitor Telemetry & Lead Qualification** within the 9-agent FRIDAY Universe.
* Communicates directly with peer agents via authenticated REST and WebSocket protocols.
* Persists private long-term memory records to **Memora** under memora://cortex/private.

---

## 🌐 3. Ecosystem endpoint configuration

These variable names and URLs are references only; they do not prove live communication. Set real credentials in secret environments.

```env
# ============================================================================== #
#               FRIDAY UNIVERSE MASTER ECOSYSTEM CONFIGURATION                  #
# ============================================================================== #

# 1. ⚡ Inference AI Multi-Model Gateway (25 Keys)
INFERENCE_URL=https://inference-h7bn.onrender.com
INFERENCE_API_KEY=<configure in secret environment>

# 2. Memora cloud memory service (active backend/capacity not verified)
MEMORA_URL=https://memora-cavc.onrender.com
MEMORA_API_KEY=<configure in secret environment>

# 3. 📈 Stratex Paper/Testnet Strategy Platform (Binance Futures)
STRATEX_URL=https://stratex-8wj1.onrender.com
STRATEX_API_KEY=<configure in secret environment>

# 4. IntelX research service (active storage backend not verified)
INTELX_URL=https://intelx-mygl.onrender.com
INTELX_API_KEY=<configure in secret environment>

# 5. 🔮 Futuris Calibrated Predictive Forecasting Engine
FUTURIS_URL=https://futuris-th6f.onrender.com
FUTURIS_API_KEY=<configure in secret environment>

# 6. 🌐 Cortex Autonomous Web Operations & Intelligence
CORTEX_URL=https://cortex-0m7c.onrender.com
CORTEX_API_KEY=<configure in secret environment>

# 7. 🛠️ Forge Local Software Engineering Engine
FORGE_URL=https://forge-e9kl.onrender.com
FORGE_API_KEY=<configure in secret environment>

# 8. 🛡️ Sentinel Local Cybersecurity & Threat Defense Shield
SENTINEL_URL=https://sentinel-a861.onrender.com
SENTINEL_API_KEY=<configure in secret environment>

# 9. 🤖 FRIDAY Central Desktop Operating System
FRIDAY_URL=https://friday-zw59.onrender.com
FRIDAY_API_KEY=<configure in secret environment>
```

---

## 🤖 4. Repository guide

When opening this repository:
* **Identity:** You are working inside **Cortex** (d:\FRIDAY Universe\Cortex).
* **Configured URL (deployment unverified): https://cortex-0m7c.onrender.com.
* **Authentication:** Incoming requests use CORTEX_API_KEY=<configure in secret environment>
* **Never Fake Tests:** All tests and verifications must be executed against real code and real endpoints.
* **No Unapproved Git Pushes:** Keep modifications local unless explicitly instructed to push.
