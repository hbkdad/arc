// ACR cognitive graph (master §1242-1256, scoped to Canvas2D — see
// docs/ARCHITECTURE.md Phase 12). No external library: this file is the
// entire rendering stack. Polls /api/graph on an interval; every shape on
// screen is a direct encoding of a real row from that endpoint, never
// synthesized or randomized data.

(function () {
  "use strict";

  const POLL_MS = 2000;
  const canvas = document.getElementById("graph");
  const statusEl = document.getElementById("graph-status");
  if (!canvas) return;
  const ctx = canvas.getContext("2d");

  const STATUS_COLORS = {
    created: "#8a8a8a",
    planning: "#4a90d9",
    executing: "#d9a24a",
    verifying: "#9b59b6",
    completed: "#2a8f3f",
    failed: "#c0392b",
    cancelled: "#8a8a8a",
  };

  const TYPE_COLORS = [
    "#4a90d9", "#2a8f3f", "#d9a24a", "#9b59b6", "#c0392b",
    "#16a085", "#e67e22", "#2c3e50", "#f1c40f",
  ];

  function colorForType(name, palette) {
    let hash = 0;
    for (let i = 0; i < name.length; i++) hash = (hash * 31 + name.charCodeAt(i)) >>> 0;
    return palette[hash % palette.length];
  }

  let latest = { memory_types: [], tasks: [], agents: [], events: [] };
  let lastNewestEventKey = null;
  let pulseUntil = 0; // performance.now() timestamp; core flashes until this time

  function eventKey(e) {
    return e.created_at + "|" + e.event_type + "|" + (e.task_id || "");
  }

  async function poll() {
    try {
      const res = await fetch("/api/graph");
      if (!res.ok) throw new Error("HTTP " + res.status);
      const data = await res.json();
      const newestKey = data.events.length ? eventKey(data.events[0]) : null;
      if (newestKey && newestKey !== lastNewestEventKey && lastNewestEventKey !== null) {
        pulseUntil = performance.now() + 500;
      }
      lastNewestEventKey = newestKey;
      latest = data;
      statusEl.textContent =
        "live — " + data.tasks.length + " recent task(s), " +
        data.agents.length + " agent spawn(s), " + data.events.length + " event(s)";
      statusEl.className = "";
    } catch (err) {
      statusEl.textContent = "disconnected: " + err;
      statusEl.className = "status-fail";
    }
  }

  function drawCore(cx, cy, t) {
    const idlePulse = 4 * Math.sin(t / 600);
    const flashing = performance.now() < pulseUntil;
    const radius = 34 + idlePulse + (flashing ? 14 : 0);
    ctx.beginPath();
    ctx.arc(cx, cy, Math.max(radius, 4), 0, Math.PI * 2);
    ctx.fillStyle = flashing ? "#f1c40f" : "#4a90d955";
    ctx.fill();
    ctx.strokeStyle = "#4a90d9";
    ctx.lineWidth = 2;
    ctx.stroke();
  }

  function drawMemoryRings(cx, cy) {
    const types = latest.memory_types;
    const n = types.length;
    if (!n) return;
    const orbit = 150;
    types.forEach((m, i) => {
      const angle = (i / n) * Math.PI * 2;
      const x = cx + orbit * Math.cos(angle);
      const y = cy + orbit * Math.sin(angle);
      const r = 10 + Math.min(30, Math.sqrt(m.count) * 6);
      ctx.beginPath();
      ctx.arc(x, y, r, 0, Math.PI * 2);
      ctx.fillStyle = colorForType(m.type, TYPE_COLORS) + "aa";
      ctx.fill();
      ctx.strokeStyle = colorForType(m.type, TYPE_COLORS);
      ctx.stroke();
      ctx.fillStyle = "#888";
      ctx.font = "11px system-ui, sans-serif";
      ctx.textAlign = "center";
      ctx.fillText(m.type + " (" + m.count + ")", x, y + r + 14);
    });
  }

  function drawTasks(width) {
    const y = 40;
    const tasks = latest.tasks;
    tasks.forEach((task, i) => {
      const x = 30 + i * ((width - 60) / Math.max(tasks.length, 1));
      ctx.fillStyle = STATUS_COLORS[task.status] || "#888";
      ctx.fillRect(x, y - 6, 12, 12);
    });
    ctx.fillStyle = "#888";
    ctx.font = "11px system-ui, sans-serif";
    ctx.textAlign = "left";
    ctx.fillText("tasks (newest first, colored by status)", 30, y - 14);
  }

  function drawAgents(width, height) {
    const y = height - 90;
    const agents = latest.agents;
    agents.forEach((agent, i) => {
      const x = 30 + i * ((width - 60) / Math.max(agents.length, 1));
      const size = 6 + agent.quality_score * 10;
      ctx.save();
      ctx.translate(x, y);
      ctx.rotate(Math.PI / 4);
      ctx.fillStyle = agent.succeeded ? "#2a8f3f99" : "#c0392b99";
      ctx.fillRect(-size / 2, -size / 2, size, size);
      ctx.restore();
    });
    ctx.fillStyle = "#888";
    ctx.font = "11px system-ui, sans-serif";
    ctx.textAlign = "left";
    ctx.fillText("agent spawns (size = quality, color = succeeded)", 30, y - 14);
  }

  function drawEventTimeline(width, height) {
    const y = height - 30;
    ctx.strokeStyle = "#8884";
    ctx.beginPath();
    ctx.moveTo(30, y);
    ctx.lineTo(width - 30, y);
    ctx.stroke();

    const events = latest.events;
    events.forEach((e, i) => {
      const x = width - 30 - i * ((width - 60) / Math.max(events.length, 1, 40));
      const fresh = i === 0 && performance.now() < pulseUntil;
      ctx.beginPath();
      ctx.arc(x, y, fresh ? 5 : 3, 0, Math.PI * 2);
      ctx.fillStyle = fresh ? "#f1c40f" : "#4a90d988";
      ctx.fill();
    });
    ctx.fillStyle = "#888";
    ctx.font = "11px system-ui, sans-serif";
    ctx.textAlign = "left";
    ctx.fillText("event flow (newest on the right, flashes on arrival)", 30, y + 18);
  }

  function render(t) {
    const width = canvas.width;
    const height = canvas.height;
    ctx.clearRect(0, 0, width, height);
    const cx = width / 2;
    const cy = height / 2 - 20;

    drawTasks(width);
    drawMemoryRings(cx, cy);
    drawCore(cx, cy, t);
    drawAgents(width, height);
    drawEventTimeline(width, height);

    requestAnimationFrame(render);
  }

  poll();
  setInterval(poll, POLL_MS);
  requestAnimationFrame(render);
})();
