const $ = (id) => document.getElementById(id);
const main = $("main");
const suggestBox = $("suggest");
let uiLang = "pt";
let suggestTimer = 0;

const I18N = {
  pt: {
    tagline: "Consulta local do repositório semântico",
    placeholder: "lema, expressão ou identificador (00001740-n)",
    search: "Procurar",
    random: "acaso",
    homeTitle: "Dicionário semântico português",
    homeLead: "Pesquise lemas em português ou inglês. Os synsets locais ligam glosas, exemplos, relações taxonómicas e equivalentes de Princeton WordNet.",
    results: "Resultados",
    empty: "Nenhum synset corresponde a esta pesquisa.",
    loading: "A consultar o índice local…",
    noGloss: "sem glosa",
    examples: "Exemplos",
    path: "Cadeia de hiperónimos",
    relations: "Relações",
    nomlex: "Nominalizações",
    flags: "Marcas",
    also: "também",
    countWords: "lemas PT",
    countEn: "lemas EN",
    countSyn: "synsets PT",
    countRel: "relações",
  },
  en: {
    tagline: "Local consultation of the semantic repository",
    placeholder: "lemma, phrase or identifier (00001740-n)",
    search: "Search",
    random: "random",
    homeTitle: "Portuguese semantic dictionary",
    homeLead: "Search Portuguese or English lemmas. Local synsets join glosses, examples, taxonomic relations and Princeton WordNet equivalents.",
    results: "Results",
    empty: "No synset matches this query.",
    loading: "Querying the local index…",
    noGloss: "no gloss",
    examples: "Examples",
    path: "Hypernym chain",
    relations: "Relations",
    nomlex: "Nominalizations",
    nomlexVerb: "verb",
    flags: "Flags",
    also: "also",
    countWords: "PT lemmas",
    countEn: "EN lemmas",
    countSyn: "PT synsets",
    countRel: "relations",
  },
};

function t(key) {
  return I18N[uiLang][key] || I18N.pt[key] || key;
}

function esc(value) {
  return String(value ?? "")
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;");
}

function posBadge(pos) {
  return `<span class="pos ${esc(pos)}">${esc((pos || "?").toUpperCase())}</span>`;
}

async function api(path) {
  const response = await fetch(path);
  if (!response.ok) throw new Error(`HTTP ${response.status}`);
  return response.json();
}

function setBusy() {
  main.innerHTML = `<p class="busy">${esc(t("loading"))}</p>`;
}

function applyUiLang() {
  $("tagline").textContent = t("tagline");
  $("q").placeholder = t("placeholder");
  document.querySelector('#search-form button[type="submit"]').textContent = t("search");
  $("random-btn").textContent = t("random");
  $("ui-lang").textContent = uiLang.toUpperCase();
  document.documentElement.lang = uiLang;
}

function formatNum(n) {
  return new Intl.NumberFormat(uiLang === "pt" ? "pt-PT" : "en").format(n || 0);
}

async function renderHome() {
  setBusy();
  const stats = await api("/api/stats");
  main.innerHTML = `
    <section class="hero">
      <h1>${esc(t("homeTitle"))}</h1>
      <p class="muted">${esc(t("homeLead"))}</p>
      <div class="stats">
        <div class="stat"><b>${formatNum(stats.pt_words)}</b>${esc(t("countWords"))}</div>
        <div class="stat"><b>${formatNum(stats.en_words)}</b>${esc(t("countEn"))}</div>
        <div class="stat"><b>${formatNum(stats.pt_synsets)}</b>${esc(t("countSyn"))}</div>
        <div class="stat"><b>${formatNum(stats.relations)}</b>${esc(t("countRel"))}</div>
      </div>
    </section>`;
}

function hitButton(hit) {
  const other = hit.other_lemmas?.length
    ? ` <span class="muted">· ${esc(t("also"))}: ${esc(hit.other_lemmas.slice(0, 4).join(", "))}</span>`
    : "";
  return `
    <button class="hit" data-id="${esc(hit.id)}">
      ${posBadge(hit.pos)}
      <div>
        <div class="lemma">${esc(hit.lemmas.slice(0, 6).join(", ") || hit.matched_lemma)}</div>
        <div class="muted">${esc(hit.id)}${other}</div>
        <p class="gloss">${esc(hit.gloss || t("noGloss"))}</p>
      </div>
    </button>`;
}

async function renderSearch(query) {
  setBusy();
  const params = new URLSearchParams({
    q: query,
    lang: $("lang").value,
    pos: $("pos").value,
    mode: $("mode").value,
  });
  const hits = await api(`/api/search?${params}`);
  if (!hits.length) {
    main.innerHTML = `<h2>${esc(t("results"))}</h2><p class="empty">${esc(t("empty"))}</p>`;
    return;
  }
  main.innerHTML = `<h2>${esc(t("results"))} <span class="muted">(${hits.length})</span></h2>
    <div class="hits">${hits.map(hitButton).join("")}</div>`;
}

function lemmaChips(lemmas) {
  return lemmas.map((lemma) => `<button class="chip" data-q="${esc(lemma)}">${esc(lemma)}</button>`).join("");
}

function langCard(title, block) {
  const gloss = (block.gloss || []).map((line) => `<p class="gloss">${esc(line)}</p>`).join("") || `<p class="muted">${esc(t("noGloss"))}</p>`;
  const examples = (block.examples || []).length
    ? `<h3>${esc(t("examples"))}</h3><ul>${block.examples.map((ex) => `<li>${esc(ex)}</li>`).join("")}</ul>`
    : "";
  return `
    <article class="card">
      <h3>${esc(title)}</h3>
      <div class="chips">${lemmaChips(block.lemmas || [])}</div>
      ${gloss}
      ${examples}
    </article>`;
}

function briefLink(item) {
  const lemmas = (item.lemmas_pt || []).slice(0, 3).join(", ") || (item.lemmas_en || []).slice(0, 3).join(", ") || item.id;
  return `<div class="rel-item" data-id="${esc(item.id)}">${posBadge(item.pos)} <strong>${esc(lemmas)}</strong>
    <span class="muted">${esc(item.id)}</span>
    <div class="muted">${esc(item.gloss || "")}</div></div>`;
}

async function renderSynset(id) {
  setBusy();
  const syn = await api(`/api/synset/${encodeURIComponent(id)}`);
  const title = (syn.pt.lemmas[0] || syn.en.lemmas[0] || syn.id);
  const flags = syn.flags.length
    ? `<p><span class="muted">${esc(t("flags"))}:</span> ${syn.flags.map(esc).join(", ")}</p>`
    : "";
  const path = syn.hypernym_path.length
    ? `<section class="card"><h3>${esc(t("path"))}</h3>
        <div class="path">${["<strong>" + esc(title) + "</strong>"].concat(
          syn.hypernym_path.map((item) => `<a data-id="${esc(item.id)}">${esc((item.lemmas_pt[0] || item.lemmas_en[0] || item.id))}</a>`)
        ).join(" <span class='muted'>→</span> ")}</div></section>`
    : "";
  const relations = syn.relations.map((block) => {
    const label = uiLang === "en" ? block.label_en : block.label_pt;
    return `<section class="rel-block">
      <h3>${esc(label)} <span class="muted">(${block.targets.length})</span></h3>
      <div class="rel-list">${block.targets.map(briefLink).join("")}</div>
    </section>`;
  }).join("");
  const nomlex = syn.nominalizations.length
    ? `<section class="card"><h3>${esc(t("nomlex"))}</h3>
        <ul>${syn.nominalizations.map((item) =>
          `<li><button class="chip" data-q="${esc(item.verb)}">${esc(item.verb)}</button>
               → <button class="chip" data-q="${esc(item.noun)}">${esc(item.noun)}</button>
               ${item.provenance ? `<span class="muted">(${esc(item.provenance)})</span>` : ""}
           </li>`).join("")}</ul></section>`
    : "";

  main.innerHTML = `
    <div class="syn-head">${posBadge(syn.pos)}<h2>${esc(title)}</h2>
      <span class="muted">${esc(syn.id)} · ${esc(syn.pos_label[uiLang] || syn.pos)}${syn.lexfile ? " · " + esc(syn.lexfile) : ""}</span>
    </div>
    ${flags}
    <div class="col-grid">
      ${langCard("Português", syn.pt)}
      ${langCard("English", syn.en)}
    </div>
    ${path}
    ${nomlex}
    <h2>${esc(t("relations"))}</h2>
    ${relations || `<p class="muted">${esc(t("empty"))}</p>`}
  `;
}

function goHome() {
  history.replaceState(null, "", "#/");
  renderHome();
}

function goSearch(query) {
  const term = query.trim();
  if (!term) return goHome();
  $("q").value = term;
  history.replaceState(null, "", `#/q/${encodeURIComponent(term)}`);
  renderSearch(term);
}

function goSynset(id) {
  history.replaceState(null, "", `#/s/${encodeURIComponent(id)}`);
  renderSynset(id);
}

function route() {
  const hash = decodeURIComponent(location.hash || "#/");
  if (hash.startsWith("#/s/")) return renderSynset(hash.slice(4));
  if (hash.startsWith("#/q/")) {
    const term = hash.slice(4);
    $("q").value = term;
    return renderSearch(term);
  }
  renderHome();
}

$("search-form").addEventListener("submit", (event) => {
  event.preventDefault();
  suggestBox.hidden = true;
  goSearch($("q").value);
});

$("go-home").addEventListener("click", goHome);

$("random-btn").addEventListener("click", async () => {
  setBusy();
  const syn = await api("/api/random");
  if (syn.id) goSynset(syn.id);
});

$("ui-lang").addEventListener("click", () => {
  uiLang = uiLang === "pt" ? "en" : "pt";
  applyUiLang();
  route();
});

$("q").addEventListener("input", () => {
  clearTimeout(suggestTimer);
  const term = $("q").value.trim();
  if (term.length < 2) {
    suggestBox.hidden = true;
    return;
  }
  suggestTimer = setTimeout(async () => {
    const lang = $("lang").value === "en" ? "en" : "pt";
    const items = await api(`/api/suggest?q=${encodeURIComponent(term)}&lang=${lang}`);
    if (!items.length) {
      suggestBox.hidden = true;
      return;
    }
    suggestBox.innerHTML = items.map((item) => `<button type="button" data-q="${esc(item)}">${esc(item)}</button>`).join("");
    suggestBox.hidden = false;
  }, 180);
});

document.addEventListener("click", (event) => {
  const chip = event.target.closest("[data-q]");
  if (chip) {
    suggestBox.hidden = true;
    goSearch(chip.dataset.q);
    return;
  }
  const syn = event.target.closest("[data-id]");
  if (syn) {
    suggestBox.hidden = true;
    goSynset(syn.dataset.id);
  }
});

document.addEventListener("click", (event) => {
  if (!event.target.closest(".suggest") && event.target !== $("q")) {
    suggestBox.hidden = true;
  }
});

applyUiLang();
route();
window.addEventListener("hashchange", route);
