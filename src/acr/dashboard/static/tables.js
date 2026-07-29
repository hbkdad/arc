// Generic client-side sort + filter for every table already rendered
// inside a .table-wrap (master §1240: "the dashboard must remain useful
// without advanced graphics" -- no library, no extra request; tables are
// already fully rendered server-side, this only reorders/hides rows
// already in the DOM). Applies automatically to every dashboard page via
// base.html's single <script> tag -- no per-template changes needed, the
// same reasoning as the pill_class filter being one shared mapping rather
// than per-page CSS.

(function () {
  "use strict";

  function numericValue(cell) {
    const text = cell.textContent.trim().replace(/,/g, "");
    if (text === "" || text === "—") return null;
    const n = parseFloat(text);
    return Number.isNaN(n) ? null : n;
  }

  function sortTable(table, columnIndex, ascending) {
    const header = table.rows[0];
    const isNumeric = header.cells[columnIndex].classList.contains("num");
    const rows = Array.from(table.rows).slice(1);
    if (!rows.length) return;
    const parent = rows[0].parentNode;

    rows.sort((a, b) => {
      const cellA = a.cells[columnIndex];
      const cellB = b.cells[columnIndex];
      if (!cellA || !cellB) return 0;
      if (isNumeric) {
        const numA = numericValue(cellA);
        const numB = numericValue(cellB);
        if (numA !== null && numB !== null) return ascending ? numA - numB : numB - numA;
      }
      const textA = cellA.textContent.trim().toLowerCase();
      const textB = cellB.textContent.trim().toLowerCase();
      return ascending ? textA.localeCompare(textB) : textB.localeCompare(textA);
    });

    // appendChild on an already-attached node MOVES it (doesn't clone),
    // so this reorders the existing rows in place.
    rows.forEach((row) => parent.appendChild(row));
  }

  function makeSortable(table) {
    const header = table.rows[0];
    if (!header || table.rows.length < 2) return; // nothing to sort
    Array.from(header.cells).forEach((th, index) => {
      if (th.tagName !== "TH") return;
      th.classList.add("sortable");
      th.tabIndex = 0;
      th.setAttribute("role", "button");
      th.setAttribute("aria-label", "Sort by " + th.textContent.trim());
      let ascending = true;
      const activate = () => {
        Array.from(header.cells).forEach((c) => c.removeAttribute("data-sort"));
        th.setAttribute("data-sort", ascending ? "asc" : "desc");
        sortTable(table, index, ascending);
        ascending = !ascending;
      };
      th.addEventListener("click", activate);
      th.addEventListener("keydown", (evt) => {
        if (evt.key === "Enter" || evt.key === " ") {
          evt.preventDefault();
          activate();
        }
      });
    });
  }

  function makeFilterable(wrap, table) {
    const dataRowCount = table.rows.length - 1;
    if (dataRowCount < 2) return; // not worth a filter box for 0-1 rows

    const input = document.createElement("input");
    input.type = "search";
    input.className = "table-filter";
    input.placeholder = "Filter…";
    input.setAttribute("aria-label", "Filter table rows");
    wrap.parentNode.insertBefore(input, wrap);

    input.addEventListener("input", () => {
      const q = input.value.trim().toLowerCase();
      Array.from(table.rows)
        .slice(1)
        .forEach((row) => {
          row.style.display = !q || row.textContent.toLowerCase().includes(q) ? "" : "none";
        });
    });
  }

  document.querySelectorAll(".table-wrap").forEach((wrap) => {
    const table = wrap.querySelector("table");
    if (!table || !table.rows.length) return;
    makeSortable(table);
    makeFilterable(wrap, table);
  });
})();
