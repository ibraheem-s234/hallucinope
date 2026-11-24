// Hallucinope web interface: send the text, mark the numbers, write the notes.
// User text is only ever inserted with textContent, never as HTML.
"use strict";

(function () {
  const VERDICTS = {
    wrong:       { word: "Nope.",        icon: "✗", name: "Nope" },
    correct:     { word: "Checks out",   icon: "✓", name: "Checks out" },
    unconfirmed: { word: "Double-check", icon: "!", name: "Double-check" },
    cant_verify: { word: "Can't check",  icon: "?", name: "Can't check" },
  };
  const TIMEOUT_MS = 20000;
  const MARK_STEP_MS = 160;
  const reducedMotion = window.matchMedia("(prefers-reduced-motion: reduce)").matches;

  const $ = (id) => document.getElementById(id);
  const form = $("check-form"), input = $("text-input"), marked = $("marked");
  const checkBtn = $("check-button"), editBtn = $("edit-button");
  const status = $("status"), uncheckedLine = $("unchecked");
  const cards = $("cards"), keyTitle = $("key-title"), margin = document.querySelector(".margin");
  const charCount = $("char-count");
  const DEFAULT_KEY_TITLE = keyTitle.textContent;
  let timers = [];

  function el(tag, className, text) {
    const node = document.createElement(tag);
    if (className) node.className = className;
    if (text !== undefined) node.textContent = text;
    return node;
  }

  function setStatus(message, isError) {
    status.textContent = message || "";
    status.classList.toggle("is-error", Boolean(isError));
  }

  function updateCount() {
    const n = input.value.length;
    charCount.textContent = n > 4000 ? `${n.toLocaleString()} / 5,000 characters` : "";
  }

  // ---------- talking to the checker ----------
  // Two ways to run the same Python checker:
  //   * website: window.HALLUCINOPE_STATIC is set by build_site.py, and Python runs
  //     inside this browser tab (Pyodide). The text never leaves the visitor's computer.
  //   * local:   python -m hallucinope.web answers POST /api/check.

  const STATIC = window.HALLUCINOPE_STATIC || null;
  let engine = null;        // a promise of check(text) -> result, created once
  let busy = false;

  function loadScript(src) {
    return new Promise((resolve, reject) => {
      const script = document.createElement("script");
      script.src = src;
      script.onload = resolve;
      script.onerror = () => reject(new Error(`Couldn't load ${src}`));
      document.head.append(script);
    });
  }

  async function fetchBytes(path) {
    const response = await fetch(path);
    if (!response.ok) throw new Error(`${path}: error ${response.status}`);
    return new Uint8Array(await response.arrayBuffer());
  }

  async function startPython() {
    await loadScript(`${STATIC.pyodide}pyodide.js`);
    const py = await window.loadPyodide({ indexURL: STATIC.pyodide });
    const [code, wb, un] = await Promise.all([
      fetchBytes("static/hallucinope.zip"),
      fetchBytes("data/worldbank_population.json"),
      fetchBytes("data/un_population.json").catch(() => null),   // optional
    ]);
    py.unpackArchive(code, "zip", { extractDir: "/app" });
    py.FS.mkdirTree("/data");
    py.FS.writeFile("/data/worldbank_population.json", wb);
    if (un) py.FS.writeFile("/data/un_population.json", un);
    const info = JSON.parse(py.runPython(
      "import sys\nsys.path.insert(0, '/app')\n" +
      "from hallucinope.web.browser import init, check\n" +
      "init('/data/worldbank_population.json', '/data/un_population.json')"));
    if (!info.ok) throw new Error(`No data: ${info.notes.join("; ")}`);
    const when = info.worldbank || info.un;
    if (when) $("data-date").textContent = ` Data downloaded ${when}.`;
    const check = py.globals.get("check");
    return (text) => JSON.parse(check(text));
  }

  function getEngine() {
    if (!engine) {
      engine = startPython().catch((err) => {
        engine = null;                    // allow another try
        console.error("[Web:App] Python didn't start", err);
        throw new Error("The checker couldn't start. Check your internet connection, " +
          "then refresh the page.");
      });
    }
    return engine;
  }

  async function requestCheck(text) {
    if (STATIC) {
      const check = await getEngine();
      await new Promise((r) => setTimeout(r, 30));   // let "Checking…" appear first
      const data = check(text);
      if (data.error) throw new Error(data.error);
      return data;
    }
    return requestServer(text);
  }

  async function requestServer(text) {
    const controller = new AbortController();
    const timer = setTimeout(() => controller.abort(), TIMEOUT_MS);
    try {
      const response = await fetch("/api/check", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ text }),
        signal: controller.signal,
      });
      const data = await response.json().catch(() => ({}));
      if (!response.ok) throw new Error(data.error || `The checker answered with error ${response.status}.`);
      return data;
    } catch (err) {
      if (err.name === "AbortError") {
        throw new Error("Checking took too long. Try a shorter paragraph.");
      }
      if (err instanceof TypeError) {   // the server isn't there
        throw new Error("Hallucinope's checker isn't responding. Make sure the terminal " +
          "running python -m hallucinope.web is still open, then try again.");
      }
      throw err;
    } finally {
      clearTimeout(timer);
    }
  }

  async function runCheck() {
    const text = input.value.trim();
    if (!text) {
      setStatus("Paste some text first, or try a sample.", true);
      input.focus();
      return;
    }
    checkBtn.disabled = true;
    busy = true;
    setStatus("Checking the numbers…");
    try {
      const result = await requestCheck(text);
      render(result);
    } catch (err) {
      console.error("[Web:App] check failed", err);
      setStatus(err.message, true);
    } finally {
      busy = false;
      checkBtn.disabled = false;
    }
  }

  // ---------- drawing the results ----------

  function render(result) {
    timers.forEach(clearTimeout);
    timers = [];
    marked.replaceChildren();
    cards.replaceChildren();

    const claims = [...result.claims].sort((a, b) => a.start - b.start);
    let pos = 0;
    for (const claim of claims) {
      if (claim.start < pos) continue;            // never overlap (defensive)
      marked.append(document.createTextNode(result.text.slice(pos, claim.start)));
      marked.append(makeMark(claim, result.text.slice(claim.start, claim.end)));
      pos = claim.end;
    }
    marked.append(document.createTextNode(result.text.slice(pos)));

    claims.forEach((claim) => cards.append(makeCard(claim)));
    renderSummary(result, claims.length);

    input.hidden = true;
    marked.hidden = false;
    checkBtn.hidden = true;
    editBtn.hidden = false;
    $("shortcut-hint").hidden = true;
    setStatus(claims.length ? "" : "No numbers to check here. Hallucinope checks populations " +
      "of countries and the world, and unit conversions.");
    marked.focus({ preventScroll: true });
    animateMarks();
  }

  function makeMark(claim, text) {
    const v = VERDICTS[claim.verdict];
    const mark = el("span", `mark mark-${claim.verdict} is-pending`, text);
    mark.dataset.id = claim.id;
    mark.dataset.kind = claim.kind;
    mark.tabIndex = 0;
    mark.setAttribute("role", "button");
    mark.setAttribute("aria-label", `Number ${claim.id}, ${text}: ${v.name}. ${claim.detail}`);
    const badge = el("sup", "badge", `${v.icon}${claim.id}`);
    badge.setAttribute("aria-hidden", "true");
    mark.append(badge);
    return mark;
  }

  function makeCard(claim) {
    const v = VERDICTS[claim.verdict];
    const card = el("li", "card");
    card.id = `card-${claim.id}`;
    card.dataset.id = claim.id;
    card.dataset.verdict = claim.verdict;
    card.tabIndex = 0;

    const head = el("div", "card-head");
    head.append(el("span", "card-number", `${v.icon}${claim.id}`),
                el("span", "card-verdict", v.word),
                el("span", "card-claim", `“${shorten(claim.text)}”`));
    const body = el("div", "card-body");
    const detail = claim.detail.charAt(0).toUpperCase() + claim.detail.slice(1);
    body.append(el("p", "card-detail", detail));

    const source = el("p", "card-source");
    const f = claim.figure;
    if (f) {
      const org = f.source.split(",")[0];          // "World Bank", "United Nations"
      const when = f.kind === "projection" ? `${f.year} projection` : f.year;
      source.append(document.createTextNode(`Source: ${org} (${when}). `));
      if (f.url) {
        const link = el("a", "", "Open the source");
        link.href = f.url;
        link.target = "_blank";
        link.rel = "noopener noreferrer";
        link.title = f.citation;                    // the full receipt, on hover
        link.addEventListener("click", (e) => e.stopPropagation());
        source.append(link);
      }
    } else if (claim.kind === "conversion") {
      source.textContent = "Worked out from exact unit definitions.";
    }
    if (source.childNodes.length) body.append(source);
    card.append(head, body);
    return card;
  }

  function shorten(text) {
    return text.length > 28 ? `${text.slice(0, 26)}…` : text;
  }

  function renderSummary(result, total) {
    margin.classList.add("has-results");
    for (const key of Object.keys(VERDICTS)) {
      document.querySelector(`[data-count="${key}"]`).textContent = result.counts[key] || 0;
    }
    keyTitle.textContent = total === 1 ? "Marked 1 number" : `Marked ${total} numbers`;

    uncheckedLine.replaceChildren();
    const notes = result.notes || [];
    if (result.unchecked.length || notes.length) {
      if (result.unchecked.length) {
        uncheckedLine.append(document.createTextNode("Not checked: "));
        result.unchecked.forEach((u, i) => {
          if (i) uncheckedLine.append(document.createTextNode(", "));
          uncheckedLine.append(el("b", "", u.text));
        });
        uncheckedLine.append(document.createTextNode(
          ". Hallucinope only checks populations and unit conversions."));
      }
      for (const note of notes) {
        uncheckedLine.append(el("span", "", ` ${note}.`));
      }
      uncheckedLine.hidden = false;
    } else {
      uncheckedLine.hidden = true;
    }
  }

  function animateMarks() {
    const marks = [...marked.querySelectorAll(".mark")];
    marks.forEach((mark, i) => {
      if (reducedMotion) { mark.classList.remove("is-pending"); return; }
      timers.push(setTimeout(() => mark.classList.remove("is-pending"), 250 + i * MARK_STEP_MS));
    });
  }

  // ---------- linking marks and cards ----------

  function activate(id, from) {
    document.querySelectorAll(".is-active").forEach((n) => n.classList.remove("is-active"));
    const mark = marked.querySelector(`.mark[data-id="${id}"]`);
    const card = $(`card-${id}`);
    if (!mark || !card) return;
    mark.classList.add("is-active");
    card.classList.add("is-active");
    const behavior = reducedMotion ? "auto" : "smooth";
    if (from === "mark") card.scrollIntoView({ block: "nearest", behavior });
    else mark.scrollIntoView({ block: "center", behavior });
  }

  function onPick(event, from) {
    const target = event.target.closest(from === "mark" ? ".mark" : ".card");
    if (target) activate(target.dataset.id, from);
  }

  function onKeyPick(event, from) {
    if (event.key === "Enter" || event.key === " ") {
      const target = event.target.closest(from === "mark" ? ".mark" : ".card");
      if (target) { event.preventDefault(); activate(target.dataset.id, from); }
    }
  }

  function backToEditing() {
    timers.forEach(clearTimeout);
    marked.hidden = true;
    input.hidden = false;
    editBtn.hidden = true;
    checkBtn.hidden = false;
    $("shortcut-hint").hidden = false;
    cards.replaceChildren();
    uncheckedLine.hidden = true;
    margin.classList.remove("has-results");
    keyTitle.textContent = DEFAULT_KEY_TITLE;
    document.querySelectorAll("[data-count]").forEach((n) => { n.textContent = ""; });
    setStatus("");
    input.focus();
  }

  // ---------- yellow desk or chalkboard ----------

  function setTheme(theme) {
    document.documentElement.dataset.theme = theme;
    const button = $("theme-button");
    const dark = theme === "dark";
    button.textContent = dark ? "Yellow page" : "Chalkboard";
    button.setAttribute("aria-pressed", String(dark));
    try { localStorage.setItem("hallucinope-theme", theme); } catch (e) { /* storage blocked: fine */ }
  }

  function savedTheme() {
    try { return localStorage.getItem("hallucinope-theme") === "dark" ? "dark" : "light"; }
    catch (e) { return "light"; }
  }

  // ---------- wiring ----------

  try {
    setTheme(savedTheme());              // yellow by default, whatever the computer's setting
    $("theme-button").addEventListener("click", () =>
      setTheme(document.documentElement.dataset.theme === "dark" ? "light" : "dark"));
    for (const sample of window.HALLUCINOPE_SAMPLES || []) {
      const button = el("button", "sample", sample.label);
      button.type = "button";
      button.addEventListener("click", () => {
        if (!marked.hidden) backToEditing();      // leave the marked view first
        input.value = sample.text;
        updateCount();
        runCheck();
      });
      $("samples").append(button);
    }
    if (/Mac|iPhone|iPad/.test(navigator.platform)) {
      $("shortcut-hint").innerHTML = "or press <kbd>⌘</kbd> + <kbd>Enter</kbd>";
    }

    form.addEventListener("submit", (e) => { e.preventDefault(); runCheck(); });
    input.addEventListener("keydown", (e) => {
      if (e.key === "Enter" && (e.ctrlKey || e.metaKey)) { e.preventDefault(); runCheck(); }
    });
    input.addEventListener("input", updateCount);
    editBtn.addEventListener("click", backToEditing);
    marked.addEventListener("click", (e) => onPick(e, "mark"));
    marked.addEventListener("keydown", (e) => onKeyPick(e, "mark"));
    cards.addEventListener("click", (e) => onPick(e, "card"));
    cards.addEventListener("keydown", (e) => onKeyPick(e, "card"));

    if (STATIC) {               // website: start Python now, so the first check is quick
      setStatus("Getting the checker ready (the first visit downloads about 10 MB)…");
      getEngine().then(
        () => { if (!busy) setStatus(""); },
        (err) => { if (!busy) setStatus(err.message, true); });
    }
  } catch (err) {
    console.error("[Web:App] setup failed", err);
    setStatus("The page didn't load properly. Refresh to try again.", true);
  }
})();