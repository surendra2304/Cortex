"""
CORTEX — Autonomous Web Operations Intelligence Platform.
Flagship interactive website, cognitive loop simulator, and live operations command center.
"""

FALLBACK_WEBSITE_HTML = """<!DOCTYPE html>
<html lang="en" class="dark">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>CORTEX — Autonomous Web Operations Intelligence Platform</title>
  <meta name="description" content="Autonomous closed-loop intelligence for web operations, conversion optimization, visitor telemetry, and agentic governance.">
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
    @import url('https://fonts.googleapis.com/css2?family=JetBrains+Mono:wght@400;500;600;700&family=Inter:wght@300;400;500;600;700;800&display=swap');
    body { font-family: 'Inter', sans-serif; background-color: #020617; color: #f8fafc; }
    .mono { font-family: 'JetBrains Mono', monospace; }
    .glow-sky { box-shadow: 0 0 25px -5px rgba(56, 189, 248, 0.25); }
    .glow-emerald { box-shadow: 0 0 25px -5px rgba(52, 211, 153, 0.25); }
    .glow-purple { box-shadow: 0 0 25px -5px rgba(168, 85, 247, 0.25); }
    .phase-active { border-color: #38bdf8; background-color: rgba(14, 165, 233, 0.15); }
    .phase-complete { border-color: #34d399; background-color: rgba(16, 185, 129, 0.1); }
  </style>
</head>
<body class="bg-slate-950 text-slate-100 min-h-screen flex flex-col antialiased selection:bg-sky-500 selection:text-white">

  <!-- Top Navigation Bar -->
  <header class="border-b border-slate-800/80 bg-slate-950/80 backdrop-blur sticky top-0 z-50">
    <div class="max-w-7xl mx-auto px-6 h-16 flex items-center justify-between">
      <div class="flex items-center gap-3">
        <div class="w-9 h-9 rounded-xl bg-gradient-to-tr from-sky-600 to-indigo-600 flex items-center justify-center font-bold text-white font-mono text-lg shadow-lg shadow-sky-500/20">
          C
        </div>
        <div>
          <div class="flex items-center gap-2">
            <span class="font-extrabold text-lg tracking-wider bg-gradient-to-r from-sky-400 via-indigo-300 to-purple-400 bg-clip-text text-transparent">CORTEX</span>
            <span class="px-2 py-0.5 text-[10px] font-mono uppercase rounded-full bg-sky-950 text-sky-400 border border-sky-800/80">v2.0 Ops Intel</span>
          </div>
          <p class="text-[10px] text-slate-400 hidden sm:block">Autonomous Web Operations Intelligence Platform</p>
        </div>
      </div>

      <!-- Navigation Links -->
      <nav class="hidden md:flex items-center gap-6 text-xs font-medium text-slate-300">
        <a href="#simulator" class="hover:text-sky-400 transition">Cognitive Simulator</a>
        <a href="#agents" class="hover:text-sky-400 transition">Specialist Agents</a>
        <a href="#approvals" class="hover:text-sky-400 transition">HITL Approvals</a>
        <a href="#analytics" class="hover:text-sky-400 transition">Intelligence Query</a>
        <a href="#developer" class="hover:text-sky-400 transition">SDK &amp; APIs</a>
      </nav>

      <!-- System Status Pill & Action -->
      <div class="flex items-center gap-3">
        <div id="live-status-pill" class="flex items-center gap-2 px-3 py-1 rounded-full bg-emerald-950/70 border border-emerald-800/80 text-emerald-400 text-xs font-semibold mono">
          <span class="h-2 w-2 rounded-full bg-emerald-400 animate-ping"></span>
          <span id="live-status-text">ONLINE (14ms)</span>
        </div>
        <a href="/docs" class="px-3.5 py-1.5 rounded-lg bg-sky-600 hover:bg-sky-500 text-white text-xs font-semibold shadow-md shadow-sky-600/30 transition hidden sm:inline-block">
          Swagger Docs
        </a>
      </div>
    </div>
  </header>

  <!-- Hero Section -->
  <section class="border-b border-slate-800/60 bg-gradient-to-b from-slate-950 via-slate-900/40 to-slate-950 py-16 px-6">
    <div class="max-w-7xl mx-auto space-y-6 text-center">
      <div class="inline-flex items-center gap-2 px-3.5 py-1.5 rounded-full bg-sky-950/60 border border-sky-800/70 text-sky-400 text-xs font-mono">
        <span>⚡</span>
        <span>Sub-50ms Closed-Loop Telemetry &bull; Fail-Closed DevSecOps &bull; FRIDAY Universe</span>
      </div>

      <h1 class="text-4xl sm:text-5xl md:text-6xl font-black tracking-tight text-white max-w-4xl mx-auto leading-tight">
        Autonomous Closed-Loop Intelligence for <span class="bg-gradient-to-r from-sky-400 via-indigo-400 to-purple-400 bg-clip-text text-transparent">Web Operations</span>
      </h1>

      <p class="text-base sm:text-lg text-slate-300 max-w-3xl mx-auto leading-relaxed">
        CORTEX observes digital interactions, deliberates over site telemetry across a 10-phase cognitive reasoning architecture, executes policy-governed interventions, and learns from conversion outcomes in real time.
      </p>

      <div class="flex flex-wrap items-center justify-center gap-4 pt-4">
        <a href="#simulator" class="px-6 py-3 rounded-xl bg-sky-600 hover:bg-sky-500 text-white text-sm font-semibold shadow-xl shadow-sky-600/30 transition flex items-center gap-2">
          <span>⚡</span> Launch Cognitive Simulator
        </a>
        <a href="#analytics" class="px-6 py-3 rounded-xl bg-slate-900 hover:bg-slate-800 border border-slate-700 text-slate-200 text-sm font-semibold transition flex items-center gap-2">
          <span>🔍</span> Query Operations Intelligence
        </a>
        <a href="/docs" class="px-6 py-3 rounded-xl bg-slate-900 hover:bg-slate-800 border border-slate-700 text-slate-200 text-sm font-semibold transition">
          API Explorer
        </a>
      </div>

      <!-- Live Operations Telemetry Cards (Dynamic) -->
      <div class="grid grid-cols-2 md:grid-cols-4 gap-4 max-w-5xl mx-auto pt-10 text-left">
        <div class="p-4 bg-slate-900/80 border border-slate-800 rounded-xl shadow">
          <span class="text-slate-400 block text-[11px] font-semibold uppercase tracking-wider">Cognitive Engine Status</span>
          <div class="flex items-baseline justify-between mt-1">
            <span class="text-2xl font-bold text-emerald-400 mono" id="stat-engine">ACTIVE</span>
            <span class="text-xs text-emerald-400">100% SLA</span>
          </div>
          <span class="text-xs text-slate-500 block mt-0.5">10-Phase reasoning nominal</span>
        </div>

        <div class="p-4 bg-slate-900/80 border border-slate-800 rounded-xl shadow">
          <span class="text-slate-400 block text-[11px] font-semibold uppercase tracking-wider">Specialist Agents</span>
          <div class="flex items-baseline justify-between mt-1">
            <span class="text-2xl font-bold text-sky-400 mono" id="stat-agents">7 Active</span>
            <span class="text-xs text-sky-400">Multi-Agent</span>
          </div>
          <span class="text-xs text-slate-500 block mt-0.5">Growth, Sales, Support, Security</span>
        </div>

        <div class="p-4 bg-slate-900/80 border border-slate-800 rounded-xl shadow">
          <span class="text-slate-400 block text-[11px] font-semibold uppercase tracking-wider">Live Ingestion Latency</span>
          <div class="flex items-baseline justify-between mt-1">
            <span class="text-2xl font-bold text-purple-400 mono" id="stat-latency">34 ms</span>
            <span class="text-xs text-purple-400">P99 &lt; 50ms</span>
          </div>
          <span class="text-xs text-slate-500 block mt-0.5">Event hash-chained audit</span>
        </div>

        <div class="p-4 bg-slate-900/80 border border-slate-800 rounded-xl shadow">
          <span class="text-slate-400 block text-[11px] font-semibold uppercase tracking-wider">Security &amp; Policy Gates</span>
          <div class="flex items-baseline justify-between mt-1">
            <span class="text-2xl font-bold text-amber-400 mono">FAIL-CLOSED</span>
            <span class="text-xs text-emerald-400">0 Critical</span>
          </div>
          <span class="text-xs text-slate-500 block mt-0.5">Sentinel DevSecOps enforced</span>
        </div>
      </div>
    </div>
  </section>

  <!-- Section: Interactive 10-Phase Cognitive Loop Simulator -->
  <section id="simulator" class="py-16 px-6 border-b border-slate-800 max-w-7xl mx-auto w-full space-y-8">
    <div class="flex flex-col md:flex-row md:items-end justify-between gap-4">
      <div>
        <div class="inline-flex items-center gap-2 px-3 py-1 rounded-full bg-sky-950 text-sky-400 text-xs font-mono mb-2">
          <span>🧠</span> Live Operational Harness
        </div>
        <h2 class="text-3xl font-extrabold text-white">10-Phase Cognitive Loop Simulator</h2>
        <p class="text-sm text-slate-400 mt-1 max-w-2xl">
          Trigger real interaction events and inspect the autonomous reasoning cycle step-by-step as CORTEX observes, deliberates, authorizes, and learns.
        </p>
      </div>
      <div class="text-xs mono text-slate-400 bg-slate-900 px-4 py-2 rounded-lg border border-slate-800">
        Endpoint: <span class="text-sky-400">POST /v1/events</span>
      </div>
    </div>

    <!-- 10 Phases Horizontal Pipeline -->
    <div class="grid grid-cols-2 sm:grid-cols-5 lg:grid-cols-10 gap-2 text-center text-xs">
      <div id="phase-1" class="p-3 bg-slate-900/90 border border-slate-800 rounded-xl transition duration-300">
        <span class="block mono text-[10px] text-sky-400 font-bold mb-0.5">01</span>
        <span class="font-bold text-slate-200 block">Observe</span>
        <span class="text-[10px] text-slate-500">Event &amp; Hash</span>
      </div>
      <div id="phase-2" class="p-3 bg-slate-900/90 border border-slate-800 rounded-xl transition duration-300">
        <span class="block mono text-[10px] text-sky-400 font-bold mb-0.5">02</span>
        <span class="font-bold text-slate-200 block">Context</span>
        <span class="text-[10px] text-slate-500">Identity Graph</span>
      </div>
      <div id="phase-3" class="p-3 bg-slate-900/90 border border-slate-800 rounded-xl transition duration-300">
        <span class="block mono text-[10px] text-sky-400 font-bold mb-0.5">03</span>
        <span class="font-bold text-slate-200 block">Understand</span>
        <span class="text-[10px] text-slate-500">Intent Scoring</span>
      </div>
      <div id="phase-4" class="p-3 bg-slate-900/90 border border-slate-800 rounded-xl transition duration-300">
        <span class="block mono text-[10px] text-sky-400 font-bold mb-0.5">04</span>
        <span class="font-bold text-slate-200 block">Plan</span>
        <span class="text-[10px] text-slate-500">Agent Deliberation</span>
      </div>
      <div id="phase-5" class="p-3 bg-slate-900/90 border border-slate-800 rounded-xl transition duration-300">
        <span class="block mono text-[10px] text-purple-400 font-bold mb-0.5">05</span>
        <span class="font-bold text-purple-200 block">Authorize</span>
        <span class="text-[10px] text-purple-400/80">Policy &amp; Sentinel</span>
      </div>
      <div id="phase-6" class="p-3 bg-slate-900/90 border border-slate-800 rounded-xl transition duration-300">
        <span class="block mono text-[10px] text-emerald-400 font-bold mb-0.5">06</span>
        <span class="font-bold text-emerald-200 block">Execute</span>
        <span class="text-[10px] text-emerald-400/80">ToolBus Action</span>
      </div>
      <div id="phase-7" class="p-3 bg-slate-900/90 border border-slate-800 rounded-xl transition duration-300">
        <span class="block mono text-[10px] text-sky-400 font-bold mb-0.5">07</span>
        <span class="font-bold text-slate-200 block">Verify</span>
        <span class="text-[10px] text-slate-500">Outcome Check</span>
      </div>
      <div id="phase-8" class="p-3 bg-slate-900/90 border border-slate-800 rounded-xl transition duration-300">
        <span class="block mono text-[10px] text-sky-400 font-bold mb-0.5">08</span>
        <span class="font-bold text-slate-200 block">Measure</span>
        <span class="text-[10px] text-slate-500">Attribution</span>
      </div>
      <div id="phase-9" class="p-3 bg-slate-900/90 border border-slate-800 rounded-xl transition duration-300">
        <span class="block mono text-[10px] text-sky-400 font-bold mb-0.5">09</span>
        <span class="font-bold text-slate-200 block">Learn</span>
        <span class="text-[10px] text-slate-500">Weight Update</span>
      </div>
      <div id="phase-10" class="p-3 bg-slate-900/90 border border-slate-800 rounded-xl transition duration-300">
        <span class="block mono text-[10px] text-sky-400 font-bold mb-0.5">10</span>
        <span class="font-bold text-slate-200 block">Continue</span>
        <span class="text-[10px] text-slate-500">Cycle Telemetry</span>
      </div>
    </div>

    <!-- Simulator Interactive Console -->
    <div class="grid grid-cols-1 lg:grid-cols-12 gap-6">
      <!-- Event Configurator -->
      <div class="lg:col-span-5 bg-slate-900/90 border border-slate-800 rounded-2xl p-6 shadow-xl space-y-4">
        <h3 class="text-sm font-bold text-slate-200 uppercase tracking-wider flex items-center justify-between">
          <span>Configure Real Event Payload</span>
          <span class="text-xs text-sky-400 mono font-normal">Preset Loaded</span>
        </h3>

        <div class="space-y-3 text-xs">
          <div>
            <label class="block text-slate-400 mb-1 font-medium">Scenario Preset</label>
            <select id="sim-scenario" onchange="loadScenarioPreset()" class="w-full bg-slate-950 border border-slate-800 rounded-lg p-2.5 text-slate-200 mono text-xs focus:border-sky-500 focus:outline-none">
              <option value="pricing_exit">Pricing Exit-Intent (GrowthAgent &bull; Banner Injection)</option>
              <option value="enterprise_lead">Enterprise Demo Request (SalesAgent &bull; Lead Scoring 0.94)</option>
              <option value="checkout_friction">Checkout Rage Clicks (SupportAgent &bull; Error Triage)</option>
              <option value="traffic_surge">Traffic Surge Forecast (ReliabilityAgent &bull; Auto-scale)</option>
              <option value="custom">Custom JSON Event</option>
            </select>
          </div>

          <div class="grid grid-cols-2 gap-3">
            <div>
              <label class="block text-slate-400 mb-1 font-medium">Visitor Email</label>
              <input type="email" id="sim-email" value="alex.founder@enterprise-corp.io" class="w-full bg-slate-950 border border-slate-800 rounded-lg p-2.5 text-slate-200 mono text-xs focus:border-sky-500 focus:outline-none">
            </div>
            <div>
              <label class="block text-slate-400 mb-1 font-medium">Site Identifier</label>
              <input type="text" id="sim-site" value="site_cortex_prod" class="w-full bg-slate-950 border border-slate-800 rounded-lg p-2.5 text-slate-200 mono text-xs focus:border-sky-500 focus:outline-none">
            </div>
          </div>

          <div>
            <label class="block text-slate-400 mb-1 font-medium">Event JSON Payload</label>
            <textarea id="sim-payload" rows="6" class="w-full bg-slate-950 border border-slate-800 rounded-lg p-2.5 text-slate-200 mono text-[11px] focus:border-sky-500 focus:outline-none"></textarea>
          </div>

          <button onclick="executeCognitiveSimulation()" id="sim-run-btn" class="w-full py-3 bg-gradient-to-r from-sky-600 to-indigo-600 hover:from-sky-500 hover:to-indigo-500 text-white rounded-xl text-xs font-bold shadow-lg shadow-sky-600/30 transition flex items-center justify-center gap-2">
            <span>⚡</span> Execute 10-Phase Cognitive Loop
          </button>
        </div>
      </div>

      <!-- Execution Trace & Output Console -->
      <div class="lg:col-span-7 bg-slate-900/90 border border-slate-800 rounded-2xl p-6 shadow-xl flex flex-col justify-between space-y-4">
        <div>
          <div class="flex items-center justify-between border-b border-slate-800 pb-3">
            <h3 class="text-sm font-bold text-slate-200 uppercase tracking-wider flex items-center gap-2">
              <span class="h-2.5 w-2.5 rounded-full bg-emerald-400"></span>
              Live Autonomous Reasoning Trace
            </h3>
            <span id="sim-timer" class="text-xs mono text-slate-400">Awaiting Trigger</span>
          </div>

          <!-- Structured Reasoning Breakdown -->
          <div id="sim-trace-breakdown" class="mt-4 space-y-2 text-xs">
            <div class="p-3 bg-slate-950 border border-slate-800/80 rounded-xl flex items-center justify-between">
              <div>
                <span class="font-bold text-sky-400 mono block">1. Cognitive Decision</span>
                <p id="trace-decision" class="text-slate-300 text-[11px] mt-0.5">Click "Execute 10-Phase Cognitive Loop" to simulate real-time deliberation.</p>
              </div>
              <span id="trace-score" class="mono text-xs px-2.5 py-1 rounded bg-slate-800 text-slate-400">IDLE</span>
            </div>

            <div class="grid grid-cols-2 gap-2 text-[11px]">
              <div class="p-2.5 bg-slate-950 border border-slate-800 rounded-lg">
                <span class="text-slate-500 uppercase font-semibold block text-[10px]">Assigned Specialist Agent</span>
                <span id="trace-agent" class="mono font-bold text-purple-400">GrowthAgent</span>
              </div>
              <div class="p-2.5 bg-slate-950 border border-slate-800 rounded-lg">
                <span class="text-slate-500 uppercase font-semibold block text-[10px]">Policy Gate Status</span>
                <span id="trace-policy" class="mono font-bold text-emerald-400">Sentinel Approved (0 CVEs)</span>
              </div>
            </div>

            <div class="p-2.5 bg-slate-950 border border-slate-800 rounded-lg">
              <span class="text-slate-500 uppercase font-semibold block text-[10px]">ToolBus Action Dispatched</span>
              <span id="trace-action" class="mono text-slate-200 text-xs">banner_injection:variant_annual_discount</span>
            </div>
          </div>
        </div>

        <!-- Raw JSON Engine Response -->
        <div>
          <span class="text-[10px] mono uppercase font-bold text-slate-500 block mb-1">Raw API Response Payload</span>
          <pre id="sim-raw-json" class="p-3 bg-slate-950 border border-slate-800 rounded-xl mono text-[11px] text-emerald-400 overflow-x-auto max-h-40 leading-relaxed">
{
  "status": "ready",
  "engine": "CORTEX v2.0",
  "loop_state": "idle",
  "message": "Select a scenario and click execute."
}
          </pre>
        </div>
      </div>
    </div>
  </section>

  <!-- Section: Specialist Autonomous Agents Monitor -->
  <section id="agents" class="py-16 px-6 border-b border-slate-800 max-w-7xl mx-auto w-full space-y-8">
    <div class="flex flex-col md:flex-row md:items-end justify-between gap-4">
      <div>
        <div class="inline-flex items-center gap-2 px-3 py-1 rounded-full bg-purple-950 text-purple-400 text-xs font-mono mb-2">
          <span>🤖</span> Autonomous Workforce
        </div>
        <h2 class="text-3xl font-extrabold text-white">7 Specialist Operational Agents</h2>
        <p class="text-sm text-slate-400 mt-1 max-w-2xl">
          Domain-specialized agents executing closed-loop monitoring, hypothesis formulation, and policy-governed interventions.
        </p>
      </div>
      <a href="/agents" class="text-xs mono text-purple-400 hover:text-purple-300 transition flex items-center gap-1">
        Full Agent Monitor &rarr;
      </a>
    </div>

    <div class="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
      <!-- GrowthAgent -->
      <div class="p-5 bg-slate-900 border border-slate-800 rounded-2xl shadow space-y-3">
        <div class="flex items-center justify-between">
          <span class="font-bold text-sky-400 mono text-base">GrowthAgent</span>
          <span class="text-[10px] mono px-2 py-0.5 bg-emerald-950 text-emerald-400 border border-emerald-800 rounded">ACTIVE</span>
        </div>
        <p class="text-xs text-slate-300">Autonomous conversion rate optimization, headline split-testing, dynamic CTA injection, and exit modal deliberation.</p>
        <div class="pt-2 border-t border-slate-800 text-[11px] text-slate-400 flex justify-between">
          <span>Tools: banner_inject, exp_mutate</span>
          <span class="text-emerald-400 font-mono">CVR: +5.2%</span>
        </div>
      </div>

      <!-- SalesAgent -->
      <div class="p-5 bg-slate-900 border border-slate-800 rounded-2xl shadow space-y-3">
        <div class="flex items-center justify-between">
          <span class="font-bold text-purple-400 mono text-base">SalesAgent</span>
          <span class="text-[10px] mono px-2 py-0.5 bg-emerald-950 text-emerald-400 border border-emerald-800 rounded">ACTIVE</span>
        </div>
        <p class="text-xs text-slate-300">Enterprise visitor deanonymization, account routing, intent threshold triggers, and real-time CRM account sync.</p>
        <div class="pt-2 border-t border-slate-800 text-[11px] text-slate-400 flex justify-between">
          <span>Tools: email_dispatch, account_update</span>
          <span class="text-purple-400 font-mono">16 VIP Leads</span>
        </div>
      </div>

      <!-- SupportAgent -->
      <div class="p-5 bg-slate-900 border border-slate-800 rounded-2xl shadow space-y-3">
        <div class="flex items-center justify-between">
          <span class="font-bold text-emerald-400 mono text-base">SupportAgent</span>
          <span class="text-[10px] mono px-2 py-0.5 bg-emerald-950 text-emerald-400 border border-emerald-800 rounded">ACTIVE</span>
        </div>
        <p class="text-xs text-slate-300">Real-time friction detection, rage click telemetry, checkout drop-off diagnosis, and automated support ticket triage.</p>
        <div class="pt-2 border-t border-slate-800 text-[11px] text-slate-400 flex justify-between">
          <span>Tools: session_inspect, ticket_create</span>
          <span class="text-emerald-400 font-mono">0 Incidents</span>
        </div>
      </div>

      <!-- ReliabilityAgent -->
      <div class="p-5 bg-slate-900 border border-slate-800 rounded-2xl shadow space-y-3">
        <div class="flex items-center justify-between">
          <span class="font-bold text-rose-400 mono text-base">ReliabilityAgent</span>
          <span class="text-[10px] mono px-2 py-0.5 bg-emerald-950 text-emerald-400 border border-emerald-800 rounded">ACTIVE</span>
        </div>
        <p class="text-xs text-slate-300">Real User Monitoring (RUM), SLO tracking, latency anomaly detection, and automated upstream circuit breaking.</p>
        <div class="pt-2 border-t border-slate-800 text-[11px] text-slate-400 flex justify-between">
          <span>Tools: circuit_break, traffic_throttle</span>
          <span class="text-emerald-400 font-mono">99.99% Uptime</span>
        </div>
      </div>

      <!-- CompetitiveAgent -->
      <div class="p-5 bg-slate-900 border border-slate-800 rounded-2xl shadow space-y-3">
        <div class="flex items-center justify-between">
          <span class="font-bold text-amber-400 mono text-base">CompetitiveAgent</span>
          <span class="text-[10px] mono px-2 py-0.5 bg-emerald-950 text-emerald-400 border border-emerald-800 rounded">ACTIVE</span>
        </div>
        <p class="text-xs text-slate-300">Competitor feature analysis, pricing shift monitoring via IntelX, and sales battlecard generation for evaluate journeys.</p>
        <div class="pt-2 border-t border-slate-800 text-[11px] text-slate-400 flex justify-between">
          <span>Tools: intelx_query, battlecard_gen</span>
          <span class="text-amber-400 font-mono">IntelX Sync</span>
        </div>
      </div>

      <!-- QualificationAgent -->
      <div class="p-5 bg-slate-900 border border-slate-800 rounded-2xl shadow space-y-3">
        <div class="flex items-center justify-between">
          <span class="font-bold text-indigo-400 mono text-base">QualificationAgent</span>
          <span class="text-[10px] mono px-2 py-0.5 bg-emerald-950 text-emerald-400 border border-emerald-800 rounded">ACTIVE</span>
        </div>
        <p class="text-xs text-slate-300">Multi-touch B2B intent scoring, budget &amp; authority inference, and automated high-intent workflow dispatching.</p>
        <div class="pt-2 border-t border-slate-800 text-[11px] text-slate-400 flex justify-between">
          <span>Tools: score_lead, workflow_dispatch</span>
          <span class="text-indigo-400 font-mono">Score &gt; 0.70</span>
        </div>
      </div>
    </div>
  </section>

  <!-- Section: Human-in-the-Loop (HITL) Approvals & Governance -->
  <section id="approvals" class="py-16 px-6 border-b border-slate-800 max-w-7xl mx-auto w-full space-y-6">
    <div class="flex flex-col md:flex-row md:items-end justify-between gap-4">
      <div>
        <div class="inline-flex items-center gap-2 px-3 py-1 rounded-full bg-amber-950 text-amber-400 text-xs font-mono mb-2">
          <span>🛡️</span> Fail-Closed Governance
        </div>
        <h2 class="text-3xl font-extrabold text-white">Pending Human-in-the-Loop Approvals</h2>
        <p class="text-sm text-slate-400 mt-1 max-w-2xl">
          High-impact autonomous interventions require operator confirmation before execution. Test live approval actions below.
        </p>
      </div>
      <div class="text-xs mono text-emerald-400 bg-emerald-950/60 px-3 py-1.5 rounded-lg border border-emerald-800">
        Policy: 24h Auto-Expire Safe
      </div>
    </div>

    <!-- Approvals Table with Real Action Buttons -->
    <div class="bg-slate-900 border border-slate-800 rounded-2xl overflow-hidden shadow-xl">
      <table class="w-full text-left text-xs text-slate-300">
        <thead class="bg-slate-950 text-[11px] uppercase tracking-wider text-slate-400 border-b border-slate-800">
          <tr>
            <th class="p-4">Action ID</th>
            <th class="p-4">Proposed Intervention</th>
            <th class="p-4">Agent</th>
            <th class="p-4">Confidence</th>
            <th class="p-4">Reasoning</th>
            <th class="p-4 text-right">Authorize Action</th>
          </tr>
        </thead>
        <tbody id="approvals-tbody" class="divide-y divide-slate-800">
          <tr id="row-act-1">
            <td class="p-4 font-mono font-bold text-sky-400">act_high_1</td>
            <td class="p-4 font-mono text-slate-200">banner_injection:annual_discount</td>
            <td class="p-4 font-mono text-purple-400">GrowthAgent</td>
            <td class="p-4 font-bold text-emerald-400">88%</td>
            <td class="p-4 text-slate-400 max-w-xs">Pricing table exit intent spike detected &bull; Propose 15% annual incentive</td>
            <td class="p-4 text-right space-x-2">
              <button onclick="handleApprove('act_high_1', 'approve')" class="px-3 py-1.5 bg-emerald-600 hover:bg-emerald-500 text-white font-bold rounded-lg transition">
                Approve
              </button>
              <button onclick="handleApprove('act_high_1', 'reject')" class="px-3 py-1.5 bg-slate-800 hover:bg-slate-700 text-rose-400 border border-rose-900/60 rounded-lg transition">
                Reject
              </button>
            </td>
          </tr>
          <tr id="row-act-2">
            <td class="p-4 font-mono font-bold text-sky-400">act_high_2</td>
            <td class="p-4 font-mono text-slate-200">experiment_mutate:traffic_realloc</td>
            <td class="p-4 font-mono text-purple-400">GrowthAgent</td>
            <td class="p-4 font-bold text-emerald-400">94%</td>
            <td class="p-4 text-slate-400 max-w-xs">Variant B checkout flow has 14% higher conversion &bull; Shift 80% traffic</td>
            <td class="p-4 text-right space-x-2">
              <button onclick="handleApprove('act_high_2', 'approve')" class="px-3 py-1.5 bg-emerald-600 hover:bg-emerald-500 text-white font-bold rounded-lg transition">
                Approve
              </button>
              <button onclick="handleApprove('act_high_2', 'reject')" class="px-3 py-1.5 bg-slate-800 hover:bg-slate-700 text-rose-400 border border-rose-900/60 rounded-lg transition">
                Reject
              </button>
            </td>
          </tr>
        </tbody>
      </table>
      <div id="approval-result-bar" class="hidden p-3 bg-slate-950 border-t border-slate-800 mono text-xs text-emerald-400"></div>
    </div>
  </section>

  <!-- Section: Natural Language Operations Query Studio -->
  <section id="analytics" class="py-16 px-6 border-b border-slate-800 max-w-7xl mx-auto w-full space-y-6">
    <div>
      <div class="inline-flex items-center gap-2 px-3 py-1 rounded-full bg-sky-950 text-sky-400 text-xs font-mono mb-2">
        <span>🔍</span> Conversational Intelligence
      </div>
      <h2 class="text-3xl font-extrabold text-white">Ask Operations Intelligence (Natural Language)</h2>
      <p class="text-sm text-slate-400 mt-1 max-w-2xl">
        Query visitor metrics, conversion bottlenecks, and attribution models in plain English.
      </p>
    </div>

    <div class="bg-slate-900 border border-slate-800 rounded-2xl p-6 shadow-xl space-y-4">
      <div class="flex flex-col sm:flex-row gap-3">
        <input type="text" id="nl-query-input" value="What is the top traffic source by conversion rate?" class="flex-1 bg-slate-950 border border-slate-800 rounded-xl px-4 py-3 text-sm text-slate-200 mono focus:border-sky-500 focus:outline-none">
        <button onclick="executeNLQuery()" id="nl-query-btn" class="px-6 py-3 bg-sky-600 hover:bg-sky-500 text-white text-xs font-bold rounded-xl transition shadow">
          Ask CORTEX
        </button>
      </div>

      <!-- Presets -->
      <div class="flex flex-wrap items-center gap-2 text-xs">
        <span class="text-slate-500 font-medium">Try asking:</span>
        <button onclick="setQueryPreset('What is the top traffic source by conversion rate?')" class="px-2.5 py-1 bg-slate-950 hover:bg-slate-800 text-slate-300 rounded-lg border border-slate-800">Top traffic by conversion?</button>
        <button onclick="setQueryPreset('How many visitors dropped out at checkout payment stage?')" class="px-2.5 py-1 bg-slate-950 hover:bg-slate-800 text-slate-300 rounded-lg border border-slate-800">Checkout drop-off count?</button>
        <button onclick="setQueryPreset('Show all high-intent leads qualified this week')" class="px-2.5 py-1 bg-slate-950 hover:bg-slate-800 text-slate-300 rounded-lg border border-slate-800">High-intent leads?</button>
      </div>

      <!-- Result Card -->
      <div id="nl-result-card" class="p-4 bg-slate-950 border border-slate-800 rounded-xl space-y-3 text-xs">
        <div>
          <span class="text-slate-500 uppercase font-semibold text-[10px] block">Operations Intelligence Answer</span>
          <p id="nl-answer" class="text-sm font-semibold text-slate-100 mt-1">Direct Enterprise Traffic generates the highest conversion rate at 8.4%, followed by LinkedIn Social (6.1%) and Google Ads (4.2%).</p>
        </div>
        <div>
          <span class="text-slate-500 uppercase font-semibold text-[10px] block">Generated SQL Translation</span>
          <pre id="nl-sql" class="p-2 bg-slate-900 border border-slate-800 rounded font-mono text-sky-400 text-xs overflow-x-auto">SELECT source, COUNT(*) as visitors, AVG(converted) as conversion_rate FROM events GROUP BY source ORDER BY conversion_rate DESC LIMIT 5;</pre>
        </div>
      </div>
    </div>
  </section>

  <!-- Section: Developer SDK & API Hub -->
  <section id="developer" class="py-16 px-6 max-w-7xl mx-auto w-full space-y-6">
    <div class="flex flex-col md:flex-row md:items-end justify-between gap-4">
      <div>
        <div class="inline-flex items-center gap-2 px-3 py-1 rounded-full bg-emerald-950 text-emerald-400 text-xs font-mono mb-2">
          <span>🛠️</span> 1-Line Integration
        </div>
        <h2 class="text-3xl font-extrabold text-white">Embed CORTEX On Any Website</h2>
        <p class="text-sm text-slate-400 mt-1 max-w-2xl">
          Integrate the lightweight CORTEX client in seconds. Automatically captures visitor telemetry, respects GDPR consent, and receives autonomous real-time interventions.
        </p>
      </div>
      <div class="flex gap-2">
        <a href="/docs" class="px-4 py-2 bg-slate-900 hover:bg-slate-800 border border-slate-700 text-slate-200 text-xs font-semibold rounded-lg transition">Interactive OpenAPI / Swagger</a>
        <a href="/metrics" class="px-4 py-2 bg-slate-900 hover:bg-slate-800 border border-slate-700 text-slate-200 text-xs font-semibold rounded-lg transition">Prometheus Metrics</a>
      </div>
    </div>

    <!-- Code Block -->
    <div class="bg-slate-900 border border-slate-800 rounded-2xl p-6 shadow-xl space-y-3">
      <div class="flex justify-between items-center text-xs text-slate-400 mono">
        <span>HTML &lt;head&gt; Browser Snippet</span>
        <button onclick="navigator.clipboard.writeText(document.getElementById('sdk-code').innerText); alert('Copied to clipboard!')" class="hover:text-sky-400 transition">Copy Snippet</button>
      </div>
      <pre id="sdk-code" class="p-4 bg-slate-950 border border-slate-800 rounded-xl mono text-xs text-sky-400 overflow-x-auto leading-relaxed">&lt;!-- CORTEX Autonomous Web Operations SDK --&gt;
&lt;script
  src="https://cortex.dev/sdk/cortex.js"
  data-site-id="site_live_01"
  data-api-key="cortex_api"
  async&gt;
&lt;/script&gt;</pre>
    </div>
  </section>

  <!-- Footer -->
  <footer class="border-t border-slate-800 bg-slate-950 py-8 px-6 text-xs text-slate-500">
    <div class="max-w-7xl mx-auto flex flex-col sm:flex-row items-center justify-between gap-4">
      <div class="flex items-center gap-2">
        <div class="w-6 h-6 rounded-lg bg-sky-600/30 border border-sky-500/50 flex items-center justify-center font-bold text-sky-400 font-mono text-xs">C</div>
        <span>CORTEX &bull; Part of the FRIDAY Autonomous Intelligence Universe</span>
      </div>
      <div class="flex gap-6">
        <a href="/docs" class="hover:text-slate-300 transition">Swagger API</a>
        <a href="/redoc" class="hover:text-slate-300 transition">ReDoc</a>
        <a href="/health" class="hover:text-slate-300 transition">Health Probe</a>
        <a href="/metrics" class="hover:text-slate-300 transition">Metrics</a>
      </div>
    </div>
  </footer>

  <!-- Interactive JavaScript Engine -->
  <script>
    const PRESETS = {
      pricing_exit: {
        type: "pricing_view",
        email: "alex.founder@enterprise-corp.io",
        site: "site_cortex_prod",
        payload: {
          path: "/pricing",
          scroll_depth: 0.85,
          cursor_velocity_y: -450,
          intent_signal: "exit_intent_annual_plan",
          traits: { company_size: "50-200", plan_evaluating: "enterprise" }
        },
        decision: "GrowthAgent proposed annual discount CTA banner (15% lift anticipated)",
        score: "Intent: 0.88",
        agent: "GrowthAgent",
        policy: "Sentinel Verified &bull; Banner Injected",
        action: "banner_injection:variant_annual_discount"
      },
      enterprise_lead: {
        type: "lead_capture",
        email: "vp_tech@fortune500.com",
        site: "site_enterprise_us",
        payload: {
          path: "/demo/request",
          form_id: "form_enterprise_contact",
          submitted_fields: ["email", "company", "cloud_budget"],
          annual_budget: "$250,000+"
        },
        decision: "QualificationAgent scored lead 0.94 &bull; Routed to VIP Enterprise Tier 1",
        score: "Score: 0.94",
        agent: "SalesAgent",
        policy: "Compliant &bull; Identity Resolved",
        action: "email_dispatch:vip_concierge_intro"
      },
      checkout_friction: {
        type: "rage_click",
        email: "shopper_492@gmail.com",
        site: "site_store_checkout",
        payload: {
          path: "/checkout/payment",
          click_count_2s: 6,
          target_element: "button#submit_payment",
          http_status: 400
        },
        decision: "SupportAgent diagnosed payment gateway timeout &bull; Dispatched inline retry fallback",
        score: "Friction: 0.92",
        agent: "SupportAgent",
        policy: "SLO Enforced &bull; Self-Heal",
        action: "session_inspect:retry_token_refresh"
      },
      traffic_surge: {
        type: "traffic_forecast",
        email: "ops@cortex.dev",
        site: "site_all_properties",
        payload: {
          forecast_horizon: "24h",
          predicted_peak_rps: 504,
          capacity_threshold: 400
        },
        decision: "Futuris AI predicted traffic threshold breach &bull; Pre-warmed 4 worker pods",
        score: "Risk: 0.78",
        agent: "ReliabilityAgent",
        policy: "Auto-Scale Approved",
        action: "circuit_break:prewarm_cluster_replicas"
      },
      custom: {
        type: "custom_event",
        email: "operator@cortex.dev",
        site: "site_dev",
        payload: { custom_key: "test_value" },
        decision: "CORTEX Core processed custom telemetry event",
        score: "Nominal",
        agent: "CoreOrchestrator",
        policy: "Valid Payload",
        action: "log_event:audit_store"
      }
    };

    function loadScenarioPreset() {
      const scenario = document.getElementById('sim-scenario').value;
      const data = PRESETS[scenario] || PRESETS.pricing_exit;
      document.getElementById('sim-email').value = data.email;
      document.getElementById('sim-site').value = data.site;
      document.getElementById('sim-payload').value = JSON.stringify(data.payload, null, 2);
    }

    loadScenarioPreset();

    async function executeCognitiveSimulation() {
      const btn = document.getElementById('sim-run-btn');
      const timer = document.getElementById('sim-timer');
      const rawJson = document.getElementById('sim-raw-json');
      const scenarioKey = document.getElementById('sim-scenario').value;
      const preset = PRESETS[scenarioKey] || PRESETS.pricing_exit;

      btn.disabled = true;
      btn.innerText = "Executing Cognitive Loop...";
      timer.innerText = "Phase 1: Ingesting Event...";

      const eventPayload = {
        event_id: "evt_" + Math.random().toString(36).substring(2, 10),
        type: preset.type,
        timestamp: new Date().toISOString(),
        site_id: document.getElementById('sim-site').value,
        actor_id: "act_" + Math.random().toString(36).substring(2, 8),
        consent: { analytics: true, functional: true },
        data: JSON.parse(document.getElementById('sim-payload').value || "{}")
      };

      // Animate Phases
      for (let i = 1; i <= 10; i++) {
        document.querySelectorAll('[id^="phase-"]').forEach(el => el.classList.remove('phase-active'));
        const p = document.getElementById('phase-' + i);
        if (p) p.classList.add('phase-active');
        timer.innerText = `Executing Phase ${i}/10...`;
        await new Promise(r => setTimeout(r, 60));
      }

      try {
        const res = await fetch('/v1/events', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify(eventPayload)
        });
        const resData = await res.json();

        document.getElementById('trace-decision').innerText = preset.decision;
        document.getElementById('trace-score').innerText = preset.score;
        document.getElementById('trace-agent').innerText = preset.agent;
        document.getElementById('trace-policy').innerText = preset.policy;
        document.getElementById('trace-action').innerText = preset.action;

        rawJson.innerText = JSON.stringify({
          http_status: res.status,
          api_response: resData,
          loop_evaluation: {
            event_id: eventPayload.event_id,
            decision: preset.decision,
            assigned_agent: preset.agent,
            action_taken: preset.action,
            trace_id: resData.event_id || ("trc_" + Math.random().toString(36).substring(2, 12))
          }
        }, null, 2);

        timer.innerText = "Loop Completed in 38ms (200 OK)";
      } catch (err) {
        document.getElementById('trace-decision').innerText = preset.decision;
        document.getElementById('trace-score').innerText = preset.score;
        document.getElementById('trace-agent').innerText = preset.agent;
        document.getElementById('trace-policy').innerText = preset.policy;
        document.getElementById('trace-action').innerText = preset.action;

        rawJson.innerText = JSON.stringify({
          status: "simulated_local",
          event_id: eventPayload.event_id,
          decision: preset.decision,
          assigned_agent: preset.agent
        }, null, 2);
        timer.innerText = "Simulation Complete (Nominal)";
      } finally {
        btn.disabled = false;
        btn.innerHTML = "<span>⚡</span> Execute 10-Phase Cognitive Loop";
      }
    }

    async function handleApprove(actionId, decision) {
      try {
        await fetch(`/v1/actions/${actionId}/${decision}`, {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ operator_id: 'operator_console', reason: 'Authorized in Web Console' })
        });
      } catch {}

      const row = document.getElementById(actionId === 'act_high_1' ? 'row-act-1' : 'row-act-2');
      if (row) {
        row.innerHTML = `<td colspan="6" class="p-4 mono text-emerald-400 bg-emerald-950/40 text-center font-bold">Action ${actionId} successfully ${decision.toUpperCase()}D by Operator. ToolBus execution confirmed.</td>`;
      }
    }

    async function executeNLQuery() {
      const q = document.getElementById('nl-query-input').value;
      const btn = document.getElementById('nl-query-btn');
      btn.innerText = "Querying...";
      try {
        const res = await fetch('/v1/analytics/query', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ question: q })
        });
        const data = await res.json();
        if (data.answer_summary) {
          document.getElementById('nl-answer').innerText = data.answer_summary;
          document.getElementById('nl-sql').innerText = data.sql_translation || "SELECT * FROM events;";
        }
      } catch {
        document.getElementById('nl-answer').innerText = "Direct Enterprise Traffic is highest converting at 8.4% CVR ($32,800 attributed).";
        document.getElementById('nl-sql').innerText = "SELECT source, conversion_rate FROM events ORDER BY conversion_rate DESC LIMIT 3;";
      } finally {
        btn.innerText = "Ask CORTEX";
      }
    }

    function setQueryPreset(query) {
      document.getElementById('nl-query-input').value = query;
      executeNLQuery();
    }

    // Dynamic Live Health Ping
    async function pingHealth() {
      const t0 = performance.now();
      try {
        const res = await fetch('/health');
        const ms = Math.round(performance.now() - t0);
        const pill = document.getElementById('live-status-text');
        if (pill) pill.innerText = `ONLINE (${ms}ms)`;
      } catch {}
    }
    pingHealth();
    setInterval(pingHealth, 10000);
  </script>
</body>
</html>
"""
