// Hand-rolled chart primitives for pages that aren't the live node graph
// (see visualization.js for that). No external library, no CDN, no build
// step -- consistent with every other phase's "no separate frontend build"
// and ACR's local-first/offline-usable requirement (docs/ARCHITECTURE.md).
//
// Deliberately NOT circle/donut-based: every shape here is a bar, line, or
// track, reusing the same CSS custom properties (--accent, --ok, --line,
// ...) base.html already defines so colors stay theme-reactive (default,
// dark, neo-cyber) without any JS re-render on theme toggle -- the SVG/DOM
// just references var(...) through chart-* classes defined in base.html.
//
// Every chart here is rendered once from real server-supplied data (a
// Jinja `{{ ... | tojson }}` blob in the calling template), not polled --
// unlike the live graph, these pages don't have a live-updating data
// source to poll against.
(function () {
  "use strict";

  function el(tag, attrs, children) {
    const isSvg = tag === "svg" || tag === "polyline" || tag === "polygon" ||
      tag === "circle" || tag === "line" || tag === "path" || tag === "rect" || tag === "title";
    const node = isSvg
      ? document.createElementNS("http://www.w3.org/2000/svg", tag)
      : document.createElement(tag);
    for (const k in attrs || {}) {
      if (k === "class") node.setAttribute("class", attrs[k]);
      else if (k === "text") node.textContent = attrs[k];
      else node.setAttribute(k, attrs[k]);
    }
    (children || []).forEach((c) => node.appendChild(c));
    return node;
  }

  function empty(container, message) {
    container.replaceChildren(el("p", { class: "chart-empty", text: message }));
  }

  // items: [{label, value, colorClass?, formatted?}]. colorClass matches
  // the same ok/warn/danger/info vocabulary the pill/metric-card system
  // already uses, so a chart bar and its table row read as the same
  // semantic color rather than a second, disconnected palette.
  function barChart(container, items, opts) {
    opts = opts || {};
    if (!items.length) return empty(container, opts.emptyMessage || "No data yet.");
    const max = opts.max || Math.max(...items.map((i) => i.value), 1e-9);
    const rows = items.map((item) => {
      const pct = Math.max(0, Math.min(100, (item.value / max) * 100));
      const fill = el("div", {
        class: "chart-bar-fill" + (item.colorClass ? " " + item.colorClass : ""),
        style: "width:" + pct.toFixed(1) + "%",
      });
      return el("div", { class: "chart-bar-row" }, [
        el("span", { class: "chart-bar-label", title: item.label, text: item.label }),
        el("div", { class: "chart-bar-track" }, [fill]),
        el("span", {
          class: "chart-bar-value",
          text: item.formatted !== undefined ? item.formatted : String(item.value),
        }),
      ]);
    });
    container.replaceChildren(el("div", { class: "chart-bars" }, rows));
  }

  // groups: [{label, a, b, aFormatted?, bFormatted?}] -- two bars per
  // group sharing one track width, e.g. predicted-vs-actual (calibration)
  // or calls-vs-cost-share (usage). aLabel/bLabel name the two series once
  // in a legend rather than per row.
  function pairedBarChart(container, groups, opts) {
    opts = opts || {};
    if (!groups.length) return empty(container, opts.emptyMessage || "No data yet.");
    const max = opts.max || Math.max(...groups.flatMap((g) => [g.a, g.b]), 1e-9);
    const legend = el("div", { class: "chart-legend" }, [
      el("span", { class: "chart-legend-item" }, [
        el("span", { class: "chart-swatch a" }),
        el("span", { text: opts.aLabel || "series a" }),
      ]),
      el("span", { class: "chart-legend-item" }, [
        el("span", { class: "chart-swatch b" }),
        el("span", { text: opts.bLabel || "series b" }),
      ]),
    ]);
    const rows = groups.map((g) => {
      const pctA = Math.max(0, Math.min(100, (g.a / max) * 100));
      const pctB = Math.max(0, Math.min(100, (g.b / max) * 100));
      return el("div", { class: "chart-paired-group" }, [
        el("div", { class: "chart-bar-row" }, [
          el("span", { class: "chart-bar-label", text: g.label }),
          el("div", { class: "chart-bar-track" }, [
            el("div", { class: "chart-bar-fill a", style: "width:" + pctA.toFixed(1) + "%" }),
          ]),
          el("span", { class: "chart-bar-value", text: g.aFormatted || g.a.toFixed(2) }),
        ]),
        el("div", { class: "chart-bar-row" }, [
          el("span", { class: "chart-bar-label" }),
          el("div", { class: "chart-bar-track" }, [
            el("div", { class: "chart-bar-fill b", style: "width:" + pctB.toFixed(1) + "%" }),
          ]),
          el("span", { class: "chart-bar-value", text: g.bFormatted || g.b.toFixed(2) }),
        ]),
      ]);
    });
    container.replaceChildren(el("div", { class: "chart-paired" }, [legend, ...rows]));
  }

  // points: [{label, value}], oldest first. Needs at least 2 real points
  // to draw a line -- a single point has no trend to show.
  function sparkline(container, points, opts) {
    opts = opts || {};
    const W = 300;
    const H = opts.height || 48;
    const PAD = 3;
    if (points.length < 2 || points.every((p) => p.value === 0)) {
      return empty(container, opts.emptyMessage || "No activity in this window yet.");
    }
    const values = points.map((p) => p.value);
    const min = Math.min(...values, 0);
    const max = Math.max(...values, 1e-9);
    const span = max - min || 1;
    const coords = points.map((p, i) => {
      const x = (i / (points.length - 1)) * (W - PAD * 2) + PAD;
      const y = H - PAD - ((p.value - min) / span) * (H - PAD * 2);
      return [x, y];
    });
    const lineStr = coords.map(([x, y]) => x.toFixed(1) + "," + y.toFixed(1)).join(" ");
    const areaStr =
      PAD + "," + (H - PAD) + " " + lineStr + " " + (W - PAD) + "," + (H - PAD);
    const last = coords[coords.length - 1];
    const totalLabel = opts.totalLabel;
    const svg = el(
      "svg",
      { viewBox: "0 0 " + W + " " + H, preserveAspectRatio: "none", class: "sparkline" },
      [
        el("title", { text: points.map((p) => p.label + ": " + p.value).join("\n") }),
        el("polygon", { class: "sparkline-area", points: areaStr }),
        el("polyline", { class: "sparkline-line", points: lineStr }),
        el("circle", { class: "sparkline-dot", cx: last[0], cy: last[1], r: 3 }),
      ]
    );
    const wrap = el("div", { class: "chart-sparkline-wrap" }, [svg]);
    if (totalLabel) {
      wrap.appendChild(el("span", { class: "chart-sparkline-label", text: totalLabel }));
    }
    container.replaceChildren(wrap);
  }

  window.ACRCharts = { barChart, pairedBarChart, sparkline };
})();
