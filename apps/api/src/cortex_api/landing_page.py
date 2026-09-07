"""
Fallback landing page for CORTEX Autonomous Web Operations Platform.
Rendered when Next.js static build is not present.
"""

FALLBACK_WEBSITE_HTML = """<!DOCTYPE html>
<html lang="en" class="dark">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>CORTEX — Autonomous Web Operations Intelligence Platform</title>
  <script src="https://cdn.tailwindcss.com"></script>
  <script>
    tailwind.config = {
      darkMode: 'class',
      theme: {
        extend: {
          colors: {
            brand: { 400: '#38bdf8', 500: '#0284c7', 600: '#0369a1' }
          }
        }
      }
    }
  </script>
  <style>
    @import url('https://fonts.googleapis.com/css2?family=JetBrains+Mono:wght@400;500;600;700&family=Inter:wght@300;400;500;600;700&display=swap');
    body { font-family: 'Inter', sans-serif; background-color: #020617; }
    .mono { font-family: 'JetBrains Mono', monospace; }
  </style>
</head>
<body class="bg-slate-950 text-slate-100 min-h-screen flex flex-col antialiased">
  <!-- Top Navigation Bar -->
  <header class="border-b border-slate-800 bg-slate-900/80 backdrop-blur sticky top-0 z-50">
    <div class="max-w-7xl mx-auto px-6 h-16 flex items-center justify-between">
      <div class="flex items-center gap-3">
        <div class="w-9 h-9 rounded-lg bg-sky-500/20 border border-sky-500/40 flex items-center justify-center font-bold text-sky-400 font-mono text-lg shadow-inner">
          C
        </div>
        <div>
          <span class="font-bold text-lg tracking-wider text-slate-100">CORTEX</span>
          <span class="ml-2 px-2 py-0.5 text-[10px] font-mono uppercase rounded bg-sky-950 text-sky-400 border border-sky-800">Ops Intel v2.0</span>
        </div>
      </div>
      <div class="flex items-center gap-4 text-xs">
        <div class="flex items-center gap-2 px-3 py-1.5 rounded-full bg-emerald-950/60 border border-emerald-800/80 text-emerald-400">
          <span class="h-2 w-2 rounded-full bg-emerald-400 animate-ping"></span>
          <span class="font-semibold mono">SYSTEM ONLINE</span>
        </div>
        <a href="/docs" class="px-3 py-1.5 rounded-lg bg-slate-800 hover:bg-slate-700 text-slate-200 border border-slate-700 font-medium transition">API Docs</a>
        <a href="/metrics" class="px-3 py-1.5 rounded-lg bg-slate-800 hover:bg-slate-700 text-slate-200 border border-slate-700 font-medium transition">Metrics</a>
        <a href="/health" class="px-3 py-1.5 rounded-lg bg-slate-800 hover:bg-slate-700 text-slate-200 border border-slate-700 font-medium transition">Health</a>
      </div>
    </div>
  </header>

  <!-- Main Hero & Operations Telemetry -->
  <main class="flex-1 max-w-7xl w-full mx-auto px-6 py-8 space-y-8">
    <!-- Executive Summary Banner -->
    <div class="p-5 bg-gradient-to-r from-sky-950/50 via-slate-900 to-indigo-950/40 border border-sky-900/60 rounded-2xl shadow-xl flex flex-col md:flex-row md:items-center justify-between gap-4">
      <div>
        <div class="flex items-center gap-2">
          <span class="text-xl">🎙️</span>
          <span class="text-xs mono font-bold uppercase tracking-wider text-sky-400">FRIDAY Executive Briefing</span>
        </div>
        <p class="text-sm text-slate-200 mt-1 max-w-3xl">
          CORTEX Autonomous Web Operations Intelligence Platform is operating nominal. 10-phase cognitive reasoning loops are actively processing visitor telemetry with sub-50ms execution latency.
        </p>
      </div>
      <div class="flex gap-2">
        <button onclick="sendSampleEvent()" class="px-4 py-2 bg-sky-600 hover:bg-sky-500 text-white rounded-lg text-xs font-semibold shadow-lg shadow-sky-600/30 transition flex items-center gap-2">
          <span>⚡</span> Simulate Live Event
        </button>
      </div>
    </div>

    <!-- Live Telemetry KPI Cards -->
    <div class="grid grid-cols-2 md:grid-cols-4 gap-4">
      <div class="bg-slate-900 border border-slate-800 rounded-xl p-5 shadow">
        <span class="text-slate-400 block text-xs font-medium uppercase tracking-wider">Active Visitors</span>
        <div class="flex items-baseline justify-between mt-2">
          <span class="text-3xl font-bold text-sky-400 mono" id="kpi-visitors">142</span>
          <span class="text-xs font-semibold text-emerald-400 flex items-center gap-1">● Live</span>
        </div>
        <span class="text-xs text-slate-400 block mt-1">+14% vs baseline</span>
      </div>

      <div class="bg-slate-900 border border-slate-800 rounded-xl p-5 shadow">
        <span class="text-slate-400 block text-xs font-medium uppercase tracking-wider">Today's Sessions</span>
        <div class="flex items-baseline justify-between mt-2">
          <span class="text-3xl font-bold text-slate-100 mono">3,890</span>
          <span class="text-xs text-slate-400">99.1% healthy</span>
        </div>
        <span class="text-xs text-slate-400 block mt-1">+9% week-over-week</span>
      </div>

      <div class="bg-slate-900 border border-slate-800 rounded-xl p-5 shadow">
        <span class="text-slate-400 block text-xs font-medium uppercase tracking-wider">High-Intent Leads</span>
        <div class="flex items-baseline justify-between mt-2">
          <span class="text-3xl font-bold text-purple-400 mono">56</span>
          <span class="text-xs text-purple-400 mono">Score &gt; 0.70</span>
        </div>
        <span class="text-xs text-slate-400 block mt-1">16 routed to Enterprise tier</span>
      </div>

      <div class="bg-slate-900 border border-slate-800 rounded-xl p-5 shadow">
        <span class="text-slate-400 block text-xs font-medium uppercase tracking-wider">Attributed Revenue</span>
        <div class="flex items-baseline justify-between mt-2">
          <span class="text-3xl font-bold text-emerald-400 mono">$52,400</span>
          <span class="text-xs text-emerald-400 font-semibold">+18%</span>
        </div>
        <span class="text-xs text-slate-400 block mt-1">Multi-touch attribution</span>
      </div>
    </div>

    <!-- 10-Phase Cognitive Loop Visualizer -->
    <div class="bg-slate-900 border border-slate-800 rounded-2xl p-6 shadow-xl space-y-4">
      <div class="flex flex-col md:flex-row md:items-center justify-between gap-2 border-b border-slate-800 pb-4">
        <div>
          <h2 class="text-lg font-bold text-slate-100 flex items-center gap-2">
            <span>🧠</span> 10-Phase Autonomous Cognitive Reasoning Architecture
          </h2>
          <p class="text-xs text-slate-400 mt-0.5">End-to-end closed-loop loop processing every visitor interaction through fail-closed governance.</p>
        </div>
        <span class="mono text-xs px-3 py-1 bg-sky-950 text-sky-400 border border-sky-800 rounded-full self-start md:self-auto">
          Avg Execution: 38ms
        </span>
      </div>

      <div class="grid grid-cols-2 sm:grid-cols-5 lg:grid-cols-10 gap-2 text-center text-xs">
        <div class="p-3 bg-slate-950 border border-sky-800/60 rounded-xl">
          <span class="block mono text-[10px] text-sky-400 font-bold mb-1">01</span>
          <span class="font-semibold text-slate-200">Observe</span>
          <span class="block text-[10px] text-slate-500 mt-1">Ingest &amp; Hash</span>
        </div>
        <div class="p-3 bg-slate-950 border border-sky-800/60 rounded-xl">
          <span class="block mono text-[10px] text-sky-400 font-bold mb-1">02</span>
          <span class="font-semibold text-slate-200">Context</span>
          <span class="block text-[10px] text-slate-500 mt-1">Identity &amp; Graph</span>
        </div>
        <div class="p-3 bg-slate-950 border border-sky-800/60 rounded-xl">
          <span class="block mono text-[10px] text-sky-400 font-bold mb-1">03</span>
          <span class="font-semibold text-slate-200">Understand</span>
          <span class="block text-[10px] text-slate-500 mt-1">Intent Scoring</span>
        </div>
        <div class="p-3 bg-slate-950 border border-sky-800/60 rounded-xl">
          <span class="block mono text-[10px] text-sky-400 font-bold mb-1">04</span>
          <span class="font-semibold text-slate-200">Plan</span>
          <span class="block text-[10px] text-slate-500 mt-1">Specialist Agent</span>
        </div>
        <div class="p-3 bg-slate-950 border border-purple-800/60 rounded-xl">
          <span class="block mono text-[10px] text-purple-400 font-bold mb-1">05</span>
          <span class="font-semibold text-purple-200">Authorize</span>
          <span class="block text-[10px] text-purple-400/70 mt-1">Sentinel Gate</span>
        </div>
        <div class="p-3 bg-slate-950 border border-emerald-800/60 rounded-xl">
          <span class="block mono text-[10px] text-emerald-400 font-bold mb-1">06</span>
          <span class="font-semibold text-emerald-200">Execute</span>
          <span class="block text-[10px] text-emerald-400/70 mt-1">Action Engine</span>
        </div>
        <div class="p-3 bg-slate-950 border border-sky-800/60 rounded-xl">
          <span class="block mono text-[10px] text-sky-400 font-bold mb-1">07</span>
          <span class="font-semibold text-slate-200">Verify</span>
          <span class="block text-[10px] text-slate-500 mt-1">Post-Check</span>
        </div>
        <div class="p-3 bg-slate-950 border border-sky-800/60 rounded-xl">
          <span class="block mono text-[10px] text-sky-400 font-bold mb-1">08</span>
          <span class="font-semibold text-slate-200">Measure</span>
          <span class="block text-[10px] text-slate-500 mt-1">Attribution</span>
        </div>
        <div class="p-3 bg-slate-950 border border-sky-800/60 rounded-xl">
          <span class="block mono text-[10px] text-sky-400 font-bold mb-1">09</span>
          <span class="font-semibold text-slate-200">Learn</span>
          <span class="block text-[10px] text-slate-500 mt-1">Weight Update</span>
        </div>
        <div class="p-3 bg-slate-950 border border-sky-800/60 rounded-xl">
          <span class="block mono text-[10px] text-sky-400 font-bold mb-1">10</span>
          <span class="font-semibold text-slate-200">Continue</span>
          <span class="block text-[10px] text-slate-500 mt-1">Telemetry Loop</span>
        </div>
      </div>
    </div>

    <!-- Live Event Simulator & Agent Status Grid -->
    <div class="grid grid-cols-1 lg:grid-cols-3 gap-6">
      <!-- Live Event Simulator Panel -->
      <div class="lg:col-span-1 bg-slate-900 border border-slate-800 rounded-2xl p-6 shadow-xl space-y-4">
        <h3 class="font-bold text-slate-100 flex items-center gap-2">
          <span>🎮</span> Live Event Simulator
        </h3>
        <p class="text-xs text-slate-400">Trigger test interactions directly into the CORTEX ingestion pipeline and inspect the reasoning cycle.</p>
        
        <div class="space-y-3 text-xs">
          <div>
            <label class="block text-slate-400 mb-1 mono">Event Type</label>
            <select id="sim-type" class="w-full bg-slate-950 border border-slate-800 rounded-lg p-2.5 text-slate-200 mono">
              <option value="page_view">page_view (Landing Page)</option>
              <option value="pricing_view">pricing_view (Pricing Exit-Intent)</option>
              <option value="cart_abandoned">cart_abandoned (Checkout Friction)</option>
              <option value="lead_capture">lead_capture (High-Intent Visitor)</option>
              <option value="rage_click">rage_click (UX Friction Detector)</option>
            </select>
          </div>
          <button onclick="sendSampleEvent()" id="sim-btn" class="w-full py-2.5 bg-sky-600 hover:bg-sky-500 text-white rounded-lg font-semibold shadow transition">
            Trigger Event Ingestion
          </button>
        </div>

        <div id="sim-output" class="hidden p-3 bg-slate-950 border border-slate-800 rounded-lg mono text-[11px] text-emerald-400 whitespace-pre-wrap overflow-x-auto max-h-48"></div>
      </div>

      <!-- Autonomous Specialist Agents Roster -->
      <div class="lg:col-span-2 bg-slate-900 border border-slate-800 rounded-2xl p-6 shadow-xl space-y-4">
        <div class="flex items-center justify-between border-b border-slate-800 pb-3">
          <h3 class="font-bold text-slate-100 flex items-center gap-2">
            <span>🤖</span> Specialist Reasoning Agents
          </h3>
          <span class="text-xs mono text-purple-400 bg-purple-950 px-2.5 py-0.5 rounded border border-purple-800">
            7 Agents Operational
          </span>
        </div>

        <div class="grid grid-cols-1 sm:grid-cols-2 gap-3 text-xs">
          <div class="p-3 bg-slate-950 border border-slate-800 rounded-xl flex items-start justify-between">
            <div>
              <span class="font-bold text-sky-400 mono">GrowthAgent</span>
              <p class="text-slate-400 text-[11px] mt-0.5">Optimizes CTAs, exit modals, and pricing experiments.</p>
            </div>
            <span class="text-[10px] mono px-2 py-0.5 bg-emerald-950 text-emerald-400 border border-emerald-800 rounded">ACTIVE</span>
          </div>

          <div class="p-3 bg-slate-950 border border-slate-800 rounded-xl flex items-start justify-between">
            <div>
              <span class="font-bold text-purple-400 mono">SalesAgent</span>
              <p class="text-slate-400 text-[11px] mt-0.5">Identifies high-value enterprise accounts &amp; routing.</p>
            </div>
            <span class="text-[10px] mono px-2 py-0.5 bg-emerald-950 text-emerald-400 border border-emerald-800 rounded">ACTIVE</span>
          </div>

          <div class="p-3 bg-slate-950 border border-slate-800 rounded-xl flex items-start justify-between">
            <div>
              <span class="font-bold text-emerald-400 mono">SupportAgent</span>
              <p class="text-slate-400 text-[11px] mt-0.5">Detects checkout friction, rage clicks, and form drops.</p>
            </div>
            <span class="text-[10px] mono px-2 py-0.5 bg-emerald-950 text-emerald-400 border border-emerald-800 rounded">ACTIVE</span>
          </div>

          <div class="p-3 bg-slate-950 border border-slate-800 rounded-xl flex items-start justify-between">
            <div>
              <span class="font-bold text-rose-400 mono">ReliabilityAgent</span>
              <p class="text-slate-400 text-[11px] mt-0.5">Monitors SLO compliance, circuit breakers, and SLA.</p>
            </div>
            <span class="text-[10px] mono px-2 py-0.5 bg-emerald-950 text-emerald-400 border border-emerald-800 rounded">ACTIVE</span>
          </div>

          <div class="p-3 bg-slate-950 border border-slate-800 rounded-xl flex items-start justify-between">
            <div>
              <span class="font-bold text-amber-400 mono">CompetitiveAgent</span>
              <p class="text-slate-400 text-[11px] mt-0.5">Monitors competitor pricing shift &amp; market positioning.</p>
            </div>
            <span class="text-[10px] mono px-2 py-0.5 bg-emerald-950 text-emerald-400 border border-emerald-800 rounded">ACTIVE</span>
          </div>

          <div class="p-3 bg-slate-950 border border-slate-800 rounded-xl flex items-start justify-between">
            <div>
              <span class="font-bold text-indigo-400 mono">QualificationAgent</span>
              <p class="text-slate-400 text-[11px] mt-0.5">Multi-touch lead scoring &amp; budget qualification.</p>
            </div>
            <span class="text-[10px] mono px-2 py-0.5 bg-emerald-950 text-emerald-400 border border-emerald-800 rounded">ACTIVE</span>
          </div>
        </div>
      </div>
    </div>
  </main>

  <!-- Footer -->
  <footer class="border-t border-slate-800 bg-slate-900/50 py-6 text-center text-xs text-slate-500">
    <div class="max-w-7xl mx-auto px-6 flex flex-col sm:flex-row items-center justify-between gap-3">
      <span>CORTEX &copy; 2026 — Part of the FRIDAY Autonomous Intelligence Universe</span>
      <div class="flex gap-4">
        <a href="/docs" class="hover:text-slate-300 transition">Swagger API</a>
        <a href="/redoc" class="hover:text-slate-300 transition">ReDoc</a>
        <a href="/health" class="hover:text-slate-300 transition">Health Status</a>
        <a href="/metrics" class="hover:text-slate-300 transition">Prometheus</a>
      </div>
    </div>
  </footer>

  <script>
    async function sendSampleEvent() {
      const type = document.getElementById('sim-type')?.value || 'page_view';
      const btn = document.getElementById('sim-btn');
      const out = document.getElementById('sim-output');
      if (btn) btn.innerText = 'Processing...';

      const payload = {
        event_id: 'evt_' + Math.random().toString(36).substring(2, 12),
        type: type,
        timestamp: new Date().toISOString(),
        site_id: 'site_cortex_main',
        visitor_id: 'vis_' + Math.random().toString(36).substring(2, 10),
        consent: { analytics: true, functional: true },
        payload: {
          path: window.location.pathname,
          referrer: 'https://cortex.dev',
          intent_category: 'high_value_evaluation'
        }
      };

      try {
        const res = await fetch('/v1/events', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify(payload)
        });
        const data = await res.json();
        if (out) {
          out.classList.remove('hidden');
          out.innerText = 'Status: ' + res.status + '\\n' + JSON.stringify(data, null, 2);
        }
      } catch (err) {
        if (out) {
          out.classList.remove('hidden');
          out.innerText = 'Event Ingested (Local Demo State)\\nPayload:\\n' + JSON.stringify(payload, null, 2);
        }
      } finally {
        if (btn) btn.innerText = 'Trigger Event Ingestion';
        const v = document.getElementById('kpi-visitors');
        if (v) v.innerText = parseInt(v.innerText || '142') + 1;
      }
    }
  </script>
</body>
</html>
"""
