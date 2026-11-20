// Copyright (c) 2026 nm_health contributors
// Content script (manifest.json) for Albuquerque Journal restaurant-inspection articles. It adds one button; a click
// saves the open page's citation and body lines as a JSON file for `uv run nm-health news add` (docs/news-links.md).
// It fetches nothing and runs only on the page you have open: no crawling. nm-health keeps facts, never the prose.

const NM_CAPTURE_KIND = "nm-health-news/1";
const NM_TAG_SELECTOR =
  'meta[property="article:tag"][content="restaurant inspections" i]';
const NM_BODY_SELECTOR = ".bodytext";
const NM_LINE_TAGS = new Set(["P", "H2", "H3", "H4"]);
const NM_BUTTON_ID = "nm-health-news-capture";
const NM_JSON_INDENT = 2;
const NM_REVOKE_AFTER_MS = 10000;
const NM_BUTTON_STYLE = [
  "position:fixed",
  "right:16px",
  "bottom:16px",
  "z-index:2147483647",
  "padding:10px 14px",
  "border:0",
  "border-radius:6px",
  "background:#1f6f43",
  "color:#fff",
  "font:600 14px system-ui,sans-serif",
  "cursor:pointer",
].join(";");

/**
 * @typedef {object} NewsCapture
 * @property {string} capture format tag nm-health checks
 * @property {string} url canonical article URL
 * @property {string} headline
 * @property {string} published article:published_time
 * @property {string} author
 * @property {string} captured_at
 * @property {string[]} lines the article body's paragraphs and headings, in order
 */

/**
 * @param {string} selector
 * @param {string} attribute
 * @returns {string}
 */
function nmAttribute(selector, attribute) {
  const found = document.querySelector(selector);
  return found?.getAttribute(attribute)?.trim() ?? "";
}

/** @returns {string} */
function nmCanonicalUrl() {
  const canonical = nmAttribute('link[rel="canonical"]', "href");
  if (canonical !== "") return canonical;
  const og = nmAttribute('meta[property="og:url"]', "content");
  if (og !== "") return og;
  return location.origin + location.pathname;
}

/** @returns {string} */
function nmHeadline() {
  const heading = document.querySelector("h1")?.textContent.trim() ?? "";
  if (heading !== "") return heading;
  return nmAttribute('meta[property="og:title"]', "content");
}

/**
 * @param {Element} body
 * @returns {string[]}
 */
function nmBodyLines(body) {
  return [...body.children]
    .filter((child) => NM_LINE_TAGS.has(child.tagName))
    .map((child) => child.textContent.trim())
    .filter((text) => text !== "");
}

/**
 * @param {Element} body
 * @returns {NewsCapture}
 */
function nmCapture(body) {
  return {
    capture: NM_CAPTURE_KIND,
    url: nmCanonicalUrl(),
    headline: nmHeadline(),
    published: nmAttribute(
      'meta[property="article:published_time"]',
      "content",
    ),
    author: nmAttribute('meta[property="article:author"]', "content"),
    captured_at: new Date().toISOString(),
    lines: nmBodyLines(body),
  };
}

/**
 * @param {string} url
 * @returns {string}
 */
function nmFileName(url) {
  const parts = new URL(url).pathname.split("/").filter((part) => part !== "");
  return `nm-health-news-${parts.at(-1) ?? "article"}.json`;
}

/** @param {NewsCapture} record */
function nmSave(record) {
  const blob = new Blob([JSON.stringify(record, null, NM_JSON_INDENT)], {
    type: "application/json",
  });
  const link = document.createElement("a");
  link.href = URL.createObjectURL(blob);
  link.download = nmFileName(record.url);
  link.click();
  setTimeout(() => {
    URL.revokeObjectURL(link.href);
  }, NM_REVOKE_AFTER_MS);
}

/** @param {Element} body */
function nmAddButton(body) {
  const button = document.createElement("button");
  button.id = NM_BUTTON_ID;
  button.type = "button";
  button.textContent = "Save for nm_health";
  button.style.cssText = NM_BUTTON_STYLE;
  button.addEventListener("click", () => {
    const record = nmCapture(body);
    nmSave(record);
    button.textContent = `Saved (${String(record.lines.length)} lines)`;
  });
  document.body.append(button);
}

function nmStart() {
  const body = document.querySelector(NM_BODY_SELECTOR);
  if (body === null || document.querySelector(NM_TAG_SELECTOR) === null) return;
  if (document.getElementById(NM_BUTTON_ID) !== null) return;
  nmAddButton(body);
}

nmStart();
