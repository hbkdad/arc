// ACR cognitive graph (master §1242-1256, scoped to Canvas2D -- see
// docs/ARCHITECTURE.md Phase 12). No external library: this file is the
// entire rendering stack. Polls /api/graph on an interval; every shape on
// screen is a direct encoding of a real row from that endpoint, never
// synthesized or randomized data.
//
// Design informed by a real competitive review (see docs/ARCHITECTURE.md):
// every AI-observability tool surveyed (LangSmith, Langfuse, Helicone,
// Arize Phoenix, W&B) keeps a table/timeline as the *primary* debugging
// surface and a graph view as a secondary, exploratory one -- matching
// this dashboard's own structure (Tasks/Events/Security stay tables; this
// is the exploratory overview). The specific finding that mattered most:
// what makes a node-graph go from "pretty but useless" (Obsidian's own
// community's description of its graph view past ~200 notes) to actually
// useful isn't a better layout algorithm, it's interactivity -- Logseq's
// fix for Roam's "unusable" graph was hover/filter/click, not physics.
// Hence: real hover tooltips and drag-to-pin below, on top of a light
// force-directed layout for the memory-type rings.

(function () {
  "use strict";

  const POLL_MS = 2000;
  const canvas = document.getElementById("graph");
  const timelineCanvas = document.getElementById("timeline");
  const statusEl = document.getElementById("graph-status");
  if (!canvas) return;
  const ctx = canvas.getContext("2d");
  const timelineCtx = timelineCanvas ? timelineCanvas.getContext("2d") : null;

  // All layout math below (drawTasks, hitTest, ...) works in this fixed
  // logical coordinate space -- the same 900x560 the canvas element was
  // authored with. The *backing store* is separately scaled up by
  // devicePixelRatio so the canvas renders sharp on hi-DPI displays
  // instead of stretching a fixed-resolution buffer (the CSS width:100%
  // previously did exactly that: same pixel data, blurrier the further
  // the rendered size drifted from 900x560).
  const LOGICAL_W = canvas.width;
  const LOGICAL_H = canvas.height;
  const TIMELINE_W = timelineCanvas ? timelineCanvas.width : 0;
  const TIMELINE_H = timelineCanvas ? timelineCanvas.height : 0;

  function fitCanvasToDisplay(target, logicalW, logicalH) {
    const dpr = window.devicePixelRatio || 1;
    target.width = logicalW * dpr;
    target.height = logicalH * dpr;
  }
  fitCanvasToDisplay(canvas, LOGICAL_W, LOGICAL_H);
  if (timelineCanvas) fitCanvasToDisplay(timelineCanvas, TIMELINE_W, TIMELINE_H);
  window.addEventListener("resize", function () {
    fitCanvasToDisplay(canvas, LOGICAL_W, LOGICAL_H);
    if (timelineCanvas) fitCanvasToDisplay(timelineCanvas, TIMELINE_W, TIMELINE_H);
  });

  // --- view switcher (graph vs timeline) ---------------------------------
  let activeView = localStorage.getItem("acr-viz-view") === "timeline" ? "timeline" : "graph";
  const viewGraphBtn = document.getElementById("view-graph");
  const viewTimelineBtn = document.getElementById("view-timeline");
  const legendGraph = document.getElementById("legend-graph");
  const legendTimeline = document.getElementById("legend-timeline");

  function applyView() {
    const isTimeline = activeView === "timeline";
    canvas.style.display = isTimeline ? "none" : "block";
    if (timelineCanvas) timelineCanvas.style.display = isTimeline ? "block" : "none";
    if (legendGraph) legendGraph.style.display = isTimeline ? "none" : "flex";
    if (legendTimeline) legendTimeline.style.display = isTimeline ? "flex" : "none";
    if (viewGraphBtn) viewGraphBtn.setAttribute("aria-pressed", String(!isTimeline));
    if (viewTimelineBtn) viewTimelineBtn.setAttribute("aria-pressed", String(isTimeline));
  }

  function setView(view) {
    activeView = view;
    localStorage.setItem("acr-viz-view", view);
    applyView();
  }

  if (viewGraphBtn) viewGraphBtn.addEventListener("click", () => setView("graph"));
  if (viewTimelineBtn) viewTimelineBtn.addEventListener("click", () => setView("timeline"));
  applyView();

  // Pulled from the same design tokens base.html defines (light/dark both
  // handled automatically by the browser resolving the CSS custom
  // properties) rather than a second, hardcoded color set that would drift
  // out of sync with the rest of the dashboard and ignore the theme.
  function theme() {
    const css = getComputedStyle(document.documentElement);
    const v = (name, fallback) => (css.getPropertyValue(name).trim() || fallback);
    return {
      bg: v("--bg", "#14120E"),
      surface: v("--surface", "#1B1812"),
      line: v("--line", "#332E24"),
      ink: v("--ink", "#EDE7D9"),
      inkDim: v("--ink-dim", "#A39985"),
      accent: v("--accent", "#D98A4B"),
      wire: v("--wire", "#6B8A72"),
      ok: v("--ok", "#5FAE7C"),
      warn: v("--warn", "#D9A24A"),
      danger: v("--danger", "#D9695A"),
      info: v("--info", "#7FA0C7"),
      // A plain number (not a CSS length) the cyber theme sets to a real
      // shadowBlur radius and every other theme leaves at 0 -- lets the
      // canvas pick up "does this theme want glow" from the same token
      // system as everything else, no second hardcoded theme check.
      glow: parseFloat(v("--canvas-glow", "0")) || 0,
    };
  }

  // Wraps a draw call with ctx.shadowBlur/shadowColor set to `color`, then
  // resets shadowBlur to 0 afterward -- canvas shadow state persists
  // across draw calls otherwise, so every unrelated shape drawn after a
  // glowing one would silently inherit the glow too.
  function withGlow(th, color, fn) {
    if (th.glow > 0) {
      ctx.shadowBlur = th.glow;
      ctx.shadowColor = color;
    }
    fn();
    if (th.glow > 0) ctx.shadowBlur = 0;
  }

  function statusColors(t) {
    return {
      created: t.inkDim,
      planning: t.info,
      executing: t.warn,
      verifying: t.wire,
      completed: t.ok,
      failed: t.danger,
      cancelled: t.inkDim,
    };
  }

  function typePalette(t) {
    return [t.wire, t.info, t.ok, t.warn, t.danger, t.accent];
  }

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

  // --- memory-ring force layout -----------------------------------------
  // Spring-to-ideal-angle + pairwise repulsion + damping: settles into an
  // organic, non-overlapping arrangement instead of a rigid fixed circle,
  // without pulling in a physics/graph library for a handful of nodes.
  let ringSim = [];

  function syncRingSim(types, cx, cy) {
    const n = types.length;
    const orbit = 150;
    const byType = new Map(ringSim.map((s) => [s.type, s]));
    ringSim = types.map((m, i) => {
      const angle = (i / n) * Math.PI * 2;
      const idealX = cx + orbit * Math.cos(angle);
      const idealY = cy + orbit * Math.sin(angle);
      const r = 10 + Math.min(30, Math.sqrt(m.count) * 6);
      const prev = byType.get(m.type);
      if (prev) {
        prev.count = m.count;
        prev.r = r;
        prev.idealX = idealX;
        prev.idealY = idealY;
        return prev;
      }
      return {
        type: m.type, count: m.count, r, idealX, idealY,
        x: idealX, y: idealY, vx: 0, vy: 0, pinned: false,
      };
    });
  }

  function stepPhysics() {
    const SPRING = 0.02;
    const REPEL = 1100;
    const DAMPING = 0.82;
    let energy = 0;
    for (let i = 0; i < ringSim.length; i++) {
      const a = ringSim[i];
      if (a.pinned) { energy += a.vx * a.vx + a.vy * a.vy; continue; }
      let fx = (a.idealX - a.x) * SPRING;
      let fy = (a.idealY - a.y) * SPRING;
      for (let j = 0; j < ringSim.length; j++) {
        if (i === j) continue;
        const b = ringSim[j];
        const dx = a.x - b.x, dy = a.y - b.y;
        const distSq = Math.max(dx * dx + dy * dy, 100);
        const dist = Math.sqrt(distSq);
        const force = REPEL / distSq;
        fx += (dx / dist) * force;
        fy += (dy / dist) * force;
      }
      a.vx = (a.vx + fx) * DAMPING;
      a.vy = (a.vy + fy) * DAMPING;
      a.x += a.vx;
      a.y += a.vy;
      energy += a.vx * a.vx + a.vy * a.vy;
    }
    return energy;
  }

  // --- pointer interaction (hover tooltip + drag-to-pin) ------------------
  let hoverTargets = []; // rebuilt every frame: [{x, y, r, label, detail}]
  let hovered = null;
  let dragging = null; // a ringSim entry currently being dragged
  let mouse = null; // {x, y} in canvas-internal coordinates, or null

  function canvasPoint(evt) {
    const rect = canvas.getBoundingClientRect();
    // Map into the LOGICAL coordinate space (what hoverTargets/ringSim are
    // expressed in), not the DPR-scaled backing-store pixel space.
    const scaleX = LOGICAL_W / rect.width;
    const scaleY = LOGICAL_H / rect.height;
    return { x: (evt.clientX - rect.left) * scaleX, y: (evt.clientY - rect.top) * scaleY };
  }

  function hitTest(pt) {
    // Last-drawn-wins (iterate in reverse) so overlapping shapes resolve to
    // whatever visually renders on top.
    for (let i = hoverTargets.length - 1; i >= 0; i--) {
      const h = hoverTargets[i];
      const dx = pt.x - h.x, dy = pt.y - h.y;
      if (dx * dx + dy * dy <= h.r * h.r) return h;
    }
    return null;
  }

  canvas.addEventListener("mousemove", (evt) => {
    mouse = canvasPoint(evt);
    if (dragging) {
      dragging.x = mouse.x;
      dragging.y = mouse.y;
      dragging.vx = 0;
      dragging.vy = 0;
    } else {
      hovered = hitTest(mouse);
      canvas.style.cursor = hovered && hovered.ring ? "grab" : hovered ? "pointer" : "default";
    }
  });

  canvas.addEventListener("mousedown", () => {
    if (hovered && hovered.ring) {
      dragging = hovered.ring;
      dragging.pinned = true;
      canvas.style.cursor = "grabbing";
    }
  });

  window.addEventListener("mouseup", () => {
    dragging = null;
  });

  canvas.addEventListener("dblclick", () => {
    // Double-click a pinned ring to release it back to the simulation.
    if (hovered && hovered.ring) hovered.ring.pinned = false;
  });

  canvas.addEventListener("mouseleave", () => {
    mouse = null;
    hovered = null;
  });

  // --- timeline pointer interaction (hover only -- no drag/pin) ---------
  let timelineHoverTargets = []; // rebuilt every frame: [{x, y, w, h, label, detail}]
  let timelineHovered = null;
  let timelineMouse = null;

  function timelineCanvasPoint(evt) {
    const rect = timelineCanvas.getBoundingClientRect();
    const scaleX = TIMELINE_W / rect.width;
    const scaleY = TIMELINE_H / rect.height;
    return { x: (evt.clientX - rect.left) * scaleX, y: (evt.clientY - rect.top) * scaleY };
  }

  function timelineHitTest(pt) {
    for (let i = timelineHoverTargets.length - 1; i >= 0; i--) {
      const h = timelineHoverTargets[i];
      if (pt.x >= h.x && pt.x <= h.x + h.w && pt.y >= h.y && pt.y <= h.y + h.h) return h;
    }
    return null;
  }

  if (timelineCanvas) {
    timelineCanvas.addEventListener("mousemove", (evt) => {
      timelineMouse = timelineCanvasPoint(evt);
      timelineHovered = timelineHitTest(timelineMouse);
      timelineCanvas.style.cursor = timelineHovered ? "pointer" : "default";
    });
    timelineCanvas.addEventListener("mouseleave", () => {
      timelineMouse = null;
      timelineHovered = null;
    });
  }

  // --- drawing --------------------------------------------------------
  function drawCore(th, cx, cy, elapsed) {
    const idlePulse = 4 * Math.sin(elapsed / 600);
    const flashing = performance.now() < pulseUntil;
    const radius = 34 + idlePulse + (flashing ? 14 : 0);
    withGlow(th, th.accent, () => {
      ctx.beginPath();
      ctx.arc(cx, cy, Math.max(radius, 4), 0, Math.PI * 2);
      ctx.fillStyle = flashing ? th.warn : th.accent + "55";
      ctx.fill();
      ctx.strokeStyle = th.accent;
      ctx.lineWidth = 2;
      ctx.stroke();
    });
    hoverTargets.push({ x: cx, y: cy, r: radius, label: "core", detail: "pulses on each new telemetry event" });
  }

  function drawMemoryRings(th, cx, cy) {
    const palette = typePalette(th);
    if (!ringSim.length) return;
    ringSim.forEach((s) => {
      const swatch = colorForType(s.type, palette);
      withGlow(th, swatch, () => {
        ctx.beginPath();
        ctx.arc(s.x, s.y, s.r, 0, Math.PI * 2);
        ctx.fillStyle = swatch + "aa";
        ctx.fill();
        ctx.strokeStyle = s.pinned ? th.ink : swatch;
        ctx.lineWidth = s.pinned ? 2 : 1;
        ctx.stroke();
      });
      ctx.fillStyle = th.inkDim;
      ctx.font = "11px system-ui, sans-serif";
      ctx.textAlign = "center";
      ctx.fillText(s.type + " (" + s.count + ")", s.x, s.y + s.r + 14);
      hoverTargets.push({
        x: s.x, y: s.y, r: Math.max(s.r, 14), ring: s,
        label: s.type, detail: s.count + " record(s)" + (s.pinned ? " — pinned, double-click to release" : ""),
      });
    });
  }

  function drawTasks(th, width) {
    const colors = statusColors(th);
    const y = 40;
    const tasks = latest.tasks;
    tasks.forEach((task, i) => {
      const x = 30 + i * ((width - 60) / Math.max(tasks.length, 1));
      const swatch = colors[task.status] || th.inkDim;
      withGlow(th, swatch, () => {
        ctx.fillStyle = swatch;
        ctx.fillRect(x, y - 6, 12, 12);
      });
      hoverTargets.push({
        x: x + 6, y, r: 10,
        label: task.objective || "(task)",
        detail: "status: " + task.status,
      });
    });
    ctx.fillStyle = th.inkDim;
    ctx.font = "11px system-ui, sans-serif";
    ctx.textAlign = "left";
    ctx.fillText("tasks (newest first, colored by status)", 30, y - 14);
  }

  function drawAgents(th, width, height) {
    const y = height - 90;
    const agents = latest.agents;
    agents.forEach((agent, i) => {
      const x = 30 + i * ((width - 60) / Math.max(agents.length, 1));
      const size = 6 + agent.quality_score * 10;
      const swatch = agent.succeeded ? th.ok : th.danger;
      withGlow(th, swatch, () => {
        ctx.save();
        ctx.translate(x, y);
        ctx.rotate(Math.PI / 4);
        ctx.fillStyle = swatch + "99";
        ctx.fillRect(-size / 2, -size / 2, size, size);
        ctx.restore();
      });
      hoverTargets.push({
        x, y, r: Math.max(size, 10),
        label: agent.task_class + " (" + agent.worker_count + " worker" + (agent.worker_count === 1 ? "" : "s") + ")",
        detail: "quality " + agent.quality_score.toFixed(2) + " — " + (agent.succeeded ? "succeeded" : "failed"),
      });
    });
    ctx.fillStyle = th.inkDim;
    ctx.font = "11px system-ui, sans-serif";
    ctx.textAlign = "left";
    ctx.fillText("agent spawns (size = quality, color = succeeded)", 30, y - 14);
  }

  function drawEventTimeline(th, width, height) {
    const y = height - 30;
    ctx.strokeStyle = th.line;
    ctx.beginPath();
    ctx.moveTo(30, y);
    ctx.lineTo(width - 30, y);
    ctx.stroke();

    const events = latest.events;
    events.forEach((e, i) => {
      const x = width - 30 - i * ((width - 60) / Math.max(events.length, 1, 40));
      const fresh = i === 0 && performance.now() < pulseUntil;
      const swatch = fresh ? th.warn : th.accent;
      withGlow(th, swatch, () => {
        ctx.beginPath();
        ctx.arc(x, y, fresh ? 5 : 3, 0, Math.PI * 2);
        ctx.fillStyle = fresh ? th.warn : th.accent + "88";
        ctx.fill();
      });
      hoverTargets.push({
        x, y, r: 8,
        label: e.event_type,
        detail: e.task_id ? "task " + e.task_id.slice(0, 8) : "no task",
      });
    });
    ctx.fillStyle = th.inkDim;
    ctx.font = "11px system-ui, sans-serif";
    ctx.textAlign = "left";
    ctx.fillText("event flow (newest on the right, flashes on arrival)", 30, y + 18);
  }

  function drawTooltip(targetCtx, th, item, width, height) {
    if (!item) return;
    const pad = 8;
    targetCtx.font = "12px system-ui, sans-serif";
    const w = Math.max(
      targetCtx.measureText(item.label).width,
      targetCtx.measureText(item.detail).width
    ) + pad * 2;
    const h = 40;
    let x = item.x + 14;
    let y = item.y - h - 10;
    if (x + w > width) x = width - w - 4;
    if (y < 0) y = item.y + 14;
    targetCtx.fillStyle = th.surface;
    targetCtx.strokeStyle = th.line;
    targetCtx.lineWidth = 1;
    targetCtx.beginPath();
    targetCtx.roundRect(x, y, w, h, 4);
    targetCtx.fill();
    targetCtx.stroke();
    targetCtx.fillStyle = th.ink;
    targetCtx.textAlign = "left";
    targetCtx.font = "bold 12px system-ui, sans-serif";
    targetCtx.fillText(item.label, x + pad, y + 17);
    targetCtx.fillStyle = th.inkDim;
    targetCtx.font = "11px system-ui, sans-serif";
    targetCtx.fillText(item.detail, x + pad, y + 32);
  }

  function formatDuration(ms) {
    const s = Math.max(0, ms / 1000);
    if (s < 60) return s.toFixed(1) + "s";
    if (s < 3600) return (s / 60).toFixed(1) + "m";
    return (s / 3600).toFixed(1) + "h";
  }

  // A real Gantt-style read of the same `latest.tasks` the graph view
  // already has -- start = created_at, end = updated_at (or "now" for a
  // task still in flight), so sequence and duration are directly visible
  // instead of implied by dot position on a fixed-width strip.
  function drawTimeline(th) {
    const width = TIMELINE_W;
    const height = TIMELINE_H;
    timelineCtx.fillStyle = th.bg;
    timelineCtx.fillRect(0, 0, width, height);
    timelineHoverTargets = [];

    const tasks = latest.tasks;
    const padLeft = 30;
    const padRight = 30;
    const padTop = 34;
    const rowH = Math.min(28, Math.max(14, (height - padTop - 30) / Math.max(tasks.length, 1)));
    const barH = Math.max(6, rowH - 8);

    timelineCtx.fillStyle = th.inkDim;
    timelineCtx.font = "11px system-ui, sans-serif";
    timelineCtx.textAlign = "left";
    timelineCtx.fillText(
      "recent tasks, newest first (bar = creation → last update or now)",
      padLeft,
      18
    );

    if (!tasks.length) {
      timelineCtx.fillStyle = th.inkDim;
      timelineCtx.font = "13px system-ui, sans-serif";
      timelineCtx.fillText("no tasks recorded yet", padLeft, padTop + 20);
      return;
    }

    const now = Date.now();
    const starts = tasks.map((t) => new Date(t.created_at).getTime());
    const ends = tasks.map((t) => new Date(t.updated_at).getTime());
    const minT = Math.min(...starts);
    const maxT = Math.max(now, ...ends);
    const span = Math.max(maxT - minT, 1000);
    const usableW = width - padLeft - padRight;
    const mapX = (t) => padLeft + ((t - minT) / span) * usableW;

    // A few evenly-spaced time-axis ticks, oldest to "now".
    timelineCtx.strokeStyle = th.line;
    timelineCtx.fillStyle = th.inkDim;
    timelineCtx.font = "10px system-ui, sans-serif";
    const tickCount = 4;
    for (let i = 0; i <= tickCount; i++) {
      const t = minT + (span * i) / tickCount;
      const x = mapX(t);
      timelineCtx.beginPath();
      timelineCtx.moveTo(x, padTop - 6);
      timelineCtx.lineTo(x, height - 22);
      timelineCtx.stroke();
      const label = i === tickCount ? "now" : formatDuration(now - t) + " ago";
      timelineCtx.textAlign = i === 0 ? "left" : i === tickCount ? "right" : "center";
      timelineCtx.fillText(label, x, height - 8);
    }

    const colors = statusColors(th);
    tasks.forEach((task, i) => {
      const y = padTop + i * rowH;
      const start = new Date(task.created_at).getTime();
      const end = new Date(task.updated_at).getTime();
      const x0 = mapX(start);
      const x1 = Math.max(mapX(Math.max(end, start)), x0 + 2);
      const swatch = colors[task.status] || th.inkDim;
      withGlow(th, swatch, () => {
        timelineCtx.fillStyle = swatch;
        timelineCtx.beginPath();
        timelineCtx.roundRect(x0, y, x1 - x0, barH, 3);
        timelineCtx.fill();
      });
      timelineCtx.fillStyle = th.ink;
      timelineCtx.font = "10px system-ui, sans-serif";
      timelineCtx.textAlign = "left";
      const label = (task.objective || "(task)").slice(0, 46);
      timelineCtx.fillText(label, Math.min(x1 + 6, width - padRight - 8), y + barH - 2);
      timelineHoverTargets.push({
        x: x0,
        y,
        w: Math.max(x1 - x0, 4),
        h: barH,
        label: task.objective || "(task)",
        detail: "status: " + task.status + " — " + formatDuration(Math.max(end, start) - start),
      });
    });
  }

  function render(elapsed) {
    const th = theme();

    if (activeView === "graph") {
      const width = LOGICAL_W;
      const height = LOGICAL_H;
      const dpr = window.devicePixelRatio || 1;
      // Reset (not compound -- setTransform is absolute) so every draw
      // call below can keep using logical 900x560 coordinates while
      // actually painting onto the DPR-scaled backing store.
      ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
      ctx.fillStyle = th.bg;
      ctx.fillRect(0, 0, width, height);
      const cx = width / 2;
      const cy = height / 2 - 20;

      syncRingSim(latest.memory_types, cx, cy);
      stepPhysics();

      hoverTargets = [];
      drawTasks(th, width);
      drawMemoryRings(th, cx, cy);
      drawCore(th, cx, cy, elapsed);
      drawAgents(th, width, height);
      drawEventTimeline(th, width, height);
      if (mouse) hovered = hitTest(mouse);
      drawTooltip(ctx, th, dragging ? null : hovered, width, height);
    } else if (timelineCtx) {
      const dpr = window.devicePixelRatio || 1;
      timelineCtx.setTransform(dpr, 0, 0, dpr, 0, 0);
      drawTimeline(th);
      if (timelineMouse) timelineHovered = timelineHitTest(timelineMouse);
      drawTooltip(timelineCtx, th, timelineHovered, TIMELINE_W, TIMELINE_H);
    }

    requestAnimationFrame(render);
  }

  poll();
  setInterval(poll, POLL_MS);
  requestAnimationFrame(render);
})();
