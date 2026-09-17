const views = document.querySelectorAll(".view");
const buttons = document.querySelectorAll("nav button");
const log = document.getElementById("action-log");

buttons.forEach((button) => {
  button.addEventListener("click", () => {
    buttons.forEach((item) => item.classList.remove("active"));
    button.classList.add("active");
    views.forEach((view) => view.classList.toggle("hidden", view.id !== button.dataset.view));
    if (button.dataset.view === "hierarchy") loadCatalog();
    if (button.dataset.view === "seeds") loadSeeds();
    if (button.dataset.view === "sources") loadSources();
    if (button.dataset.view === "report") loadReport();
  });
});

async function api(path, options) {
  const response = await fetch(path, options);
  const data = await response.json();
  if (!response.ok) throw new Error(data.error || response.statusText);
  return data;
}

function element(tag, { className, text } = {}) {
  const item = document.createElement(tag);
  if (className) item.className = className;
  if (text !== undefined) item.textContent = String(text);
  return item;
}

function replace(id, ...children) {
  document.getElementById(id).replaceChildren(...children);
}

function labeledParagraph(label, value) {
  const paragraph = element("p");
  paragraph.append(element("strong", { text: label }), document.createTextNode(` ${value}`));
  return paragraph;
}

function tagList(tags) {
  const list = element("div", { className: "tags" });
  (tags || []).forEach((tag) => list.append(element("span", { className: "tag", text: tag })));
  return list;
}

async function loadStatus() {
  const status = await api("/api/status");
  replace(
    "status-card",
    labeledParagraph("Workspace", status.workspace),
    labeledParagraph("Configured", status.configured ? "yes" : "no"),
    labeledParagraph("Sources", (status.enabled_sources || []).join(", ") || "none yet"),
    labeledParagraph(
      "Schedule",
      `${status.report_frequency || "unset"} · due ${status.report_due ? "now" : "later"}`,
    ),
    labeledParagraph("Last harvest", status.last_ingest_at || "never"),
    labeledParagraph(
      "Seeds",
      `${status.seed_count ?? 0} · Catalog nodes ${status.catalog_nodes ?? 0}`,
    ),
  );
  if (status.report_frequency) document.getElementById("frequency").value = status.report_frequency;
}

async function loadOpinion() {
  const catalog = await api("/api/catalog");
  const tags = [...new Set(catalog.nodes.flatMap((node) => node.tags || []))];
  const rules = catalog.nodes.reduce((sum, node) => sum + (node.rule_count || 0), 0);
  replace(
    "opinion",
    element("h2", { text: "What the files currently encode" }),
    element("p", {
      text: `${catalog.nodes.length} files · ${rules} inspectable rules · categories ${catalog.categories.join(", ")}`,
    }),
    tagList(tags),
    element("p", {
      className: "lede",
      text: "This is a lexical reading of your index, category files, and learned overlays. It is not a trained preference model.",
    }),
  );
}

async function loadCatalog() {
  const catalog = await api("/api/catalog");
  const articles = catalog.nodes.map((node) => {
    const article = element("article");
    const details = element("p");
    details.append(
      element("code", { text: node.path }),
      document.createTextNode(
        ` · ${node.kind} · ${node.rule_count} rules · ${node.exists ? "present" : "missing"}`,
      ),
    );
    article.append(
      element("h2", { text: node.title }),
      element("p", { text: node.summary }),
      details,
      tagList(node.tags),
    );
    return article;
  });
  replace("catalog", ...articles);
}

async function loadSeeds() {
  const data = await api("/api/seeds");
  const articles = data.seeds
    .slice()
    .reverse()
    .map((seed) => {
      const article = element("article");
      const heading = element("p");
      heading.append(
        element("strong", { text: seed.kind }),
        document.createTextNode(` → ${seed.domain} · ${seed.label || ""}`),
      );
      article.append(heading, element("p", { text: (seed.excerpt || "").slice(0, 280) }));
      return article;
    });
  replace("seed-list", ...(articles.length ? articles : [element("p", { text: "No seeds yet." })]));
}

async function loadSources() {
  const sources = await api("/api/sources");
  const articles = sources.map((source) => {
    const article = element("article");
    article.append(
      element("h2", { text: source.name }),
      element("p", {
        text: `${source.present ? "present" : "not detected"} · ${source.session_files} session files`,
      }),
      element("p", { text: source.detail }),
    );
    return article;
  });
  replace("source-list", ...articles);
}

async function loadReport() {
  const report = await api("/api/report");
  document.getElementById("report-md").textContent = report.markdown;
}

document.getElementById("harvest-btn").addEventListener("click", async () => {
  try {
    const result = await api("/api/harvest", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: "{}",
    });
    log.textContent = JSON.stringify(result, null, 2);
    await loadStatus();
    await loadOpinion();
  } catch (err) {
    log.textContent = String(err);
  }
});

document.getElementById("schedule-btn").addEventListener("click", async () => {
  const every = document.getElementById("frequency").value;
  const result = await api("/api/schedule", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ every }),
  });
  log.textContent = JSON.stringify(result, null, 2);
  await loadStatus();
});

document.getElementById("like-form").addEventListener("submit", async (event) => {
  event.preventDefault();
  const form = event.target;
  const unlike = event.submitter && event.submitter.id === "unlike-btn";
  try {
    const result = await api("/api/like", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        text: form.text.value,
        domain: form.domain.value,
        unlike,
      }),
    });
    log.textContent = JSON.stringify(result, null, 2);
    form.reset();
    await loadStatus();
  } catch (err) {
    log.textContent = String(err);
  }
});

document.getElementById("seed-form").addEventListener("submit", async (event) => {
  event.preventDefault();
  const form = event.target;
  const payload = {
    domain: form.domain.value,
    url: form.url.value,
    text: form.text.value,
    caption: form.caption.value,
  };
  const file = form.file.files[0];
  try {
    if (file) {
      const buffer = await file.arrayBuffer();
      const bytes = new Uint8Array(buffer);
      let binary = "";
      bytes.forEach((value) => {
        binary += String.fromCharCode(value);
      });
      payload.filename = file.name;
      payload.content = btoa(binary);
    }
    const result = await api("/api/seed", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload),
    });
    log.textContent = JSON.stringify(result, null, 2);
    form.reset();
    await loadSeeds();
  } catch (err) {
    log.textContent = String(err);
  }
});

Promise.all([loadStatus(), loadOpinion()]).catch((err) => {
  replace("status-card", element("p", { text: String(err) }));
});
