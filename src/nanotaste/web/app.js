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

function show(el, html) {
  document.getElementById(el).innerHTML = html;
}

async function loadStatus() {
  const status = await api("/api/status");
  show(
    "status-card",
    `<p><strong>Workspace</strong> ${status.workspace}</p>
     <p><strong>Configured</strong> ${status.configured ? "yes" : "no"}</p>
     <p><strong>Sources</strong> ${(status.enabled_sources || []).join(", ") || "none yet"}</p>
     <p><strong>Schedule</strong> ${status.report_frequency || "unset"} · due ${status.report_due ? "now" : "later"}</p>
     <p><strong>Last harvest</strong> ${status.last_ingest_at || "never"}</p>
     <p><strong>Seeds</strong> ${status.seed_count ?? 0} · <strong>Catalog nodes</strong> ${status.catalog_nodes ?? 0}</p>`
  );
  if (status.report_frequency) document.getElementById("frequency").value = status.report_frequency;
}

async function loadOpinion() {
  const catalog = await api("/api/catalog");
  const tags = [...new Set(catalog.nodes.flatMap((node) => node.tags || []))];
  const rules = catalog.nodes.reduce((sum, node) => sum + (node.rule_count || 0), 0);
  show(
    "opinion",
    `<h2>What the files currently encode</h2>
     <p>${catalog.nodes.length} files · ${rules} inspectable rules · categories ${catalog.categories.join(", ")}</p>
     <div class="tags">${tags.map((tag) => `<span class="tag">${tag}</span>`).join("")}</div>
     <p class="lede">This is a lexical reading of your index, category files, and learned overlays. It is not a trained preference model.</p>`
  );
}

async function loadCatalog() {
  const catalog = await api("/api/catalog");
  show(
    "catalog",
    catalog.nodes
      .map(
        (node) => `<article>
          <h2>${node.title}</h2>
          <p>${node.summary}</p>
          <p><code>${node.path}</code> · ${node.kind} · ${node.rule_count} rules · ${node.exists ? "present" : "missing"}</p>
          <div class="tags">${(node.tags || []).map((tag) => `<span class="tag">${tag}</span>`).join("")}</div>
        </article>`
      )
      .join("")
  );
}

async function loadSeeds() {
  const data = await api("/api/seeds");
  show(
    "seed-list",
    data.seeds
      .slice()
      .reverse()
      .map(
        (seed) => `<article>
          <p><strong>${seed.kind}</strong> → ${seed.domain} · ${seed.label || ""}</p>
          <p>${(seed.excerpt || "").slice(0, 280)}</p>
        </article>`
      )
      .join("") || "<p>No seeds yet.</p>"
  );
}

async function loadSources() {
  const sources = await api("/api/sources");
  show(
    "source-list",
    sources
      .map(
        (source) => `<article>
          <h2>${source.name}</h2>
          <p>${source.present ? "present" : "not detected"} · ${source.session_files} session files</p>
          <p>${source.detail}</p>
        </article>`
      )
      .join("")
  );
}

async function loadReport() {
  const report = await api("/api/report");
  document.getElementById("report-md").textContent = report.markdown;
}

document.getElementById("harvest-btn").addEventListener("click", async () => {
  try {
    const result = await api("/api/harvest", { method: "POST", headers: { "Content-Type": "application/json" }, body: "{}" });
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
  show("status-card", `<p>${String(err)}</p>`);
});
