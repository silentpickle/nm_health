// Live search and filters for the place list. The page works without it: every place is listed in the HTML.

/** @typedef {{ item: HTMLElement, text: string, flags: Set<string> }} Entry */

const ALL = "all";

/**
 * @param {Element} li
 * @returns {Entry | null}
 */
function toEntry(li) {
  if (!(li instanceof HTMLElement)) {
    return null;
  }
  const text = li.dataset.search ?? "";
  const flags = new Set((li.dataset.flags ?? "").split(" ").filter(Boolean));
  return { item: li, text, flags };
}

/**
 * @param {Entry} entry
 * @param {string[]} words
 * @param {string} filter
 */
function matches(entry, words, filter) {
  if (filter !== ALL && !entry.flags.has(filter)) {
    return false;
  }
  return words.every((word) => entry.text.includes(word));
}

/**
 * @param {Entry[]} entries
 * @param {string} query
 * @param {string} filter
 * @param {HTMLElement} counter
 */
function apply(entries, query, filter, counter) {
  const words = query.toLowerCase().split(/\s+/).filter(Boolean);
  let shown = 0;
  for (const entry of entries) {
    const visible = matches(entry, words, filter);
    entry.item.hidden = !visible;
    shown += visible ? 1 : 0;
  }
  counter.textContent = `${String(shown)} of ${String(entries.length)} places`;
}

/**
 * @param {HTMLElement} root
 * @param {string} active
 */
function pressOnly(root, active) {
  for (const button of root.querySelectorAll("button[data-filter]")) {
    button.setAttribute(
      "aria-pressed",
      String(button.getAttribute("data-filter") === active),
    );
  }
}

function start() {
  const input = document.getElementById("q");
  const list = document.getElementById("places");
  const counter = document.getElementById("count");
  const filters = document.getElementById("filters");
  if (!(input instanceof HTMLInputElement) || !list || !counter || !filters) {
    return;
  }
  const entries = [...list.children].map(toEntry).filter((e) => e !== null);
  let filter = ALL;
  const refresh = () => {
    apply(entries, input.value, filter, counter);
  };
  input.addEventListener("input", refresh);
  filters.addEventListener("click", (event) => {
    const target = event.target;
    if (!(target instanceof HTMLButtonElement) || !target.dataset.filter) {
      return;
    }
    filter = target.dataset.filter;
    pressOnly(filters, filter);
    refresh();
  });
  filters.hidden = false;
  refresh();
}

start();
