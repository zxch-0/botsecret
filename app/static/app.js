const $ = (id) => document.getElementById(id);

async function api(path, body) {
  const res = await fetch(path, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: body === undefined ? undefined : JSON.stringify(body),
  });
  if (res.status === 401) {
    window.location.href = "/login";
    return null;
  }
  const data = await res.json().catch(() => ({}));
  if (!res.ok) throw new Error(data.detail || "erreur");
  return data;
}

function collectPreset() {
  const preset = {};
  document.querySelectorAll("#preset-form [data-key]").forEach((el) => {
    const key = el.dataset.key;
    if (el.type === "checkbox") preset[key] = el.checked;
    else if (el.type === "number") preset[key] = Number(el.value || 0);
    else preset[key] = el.value;
  });
  return preset;
}

$("preset-form").addEventListener("submit", async (event) => {
  event.preventDefault();
  $("preset-status").textContent = "enregistrement…";
  try {
    await api("/api/preset", collectPreset());
    $("preset-status").textContent = "preset enregistré";
  } catch (err) {
    $("preset-status").textContent = "échec : " + err.message;
  }
});

$("save-secret").addEventListener("click", async () => {
  try {
    await api("/api/secret", { code: $("secret-code").value });
    $("preset-status").textContent = "code secret enregistré";
  } catch (err) {
    alert(err.message);
  }
});

$("regen-secret").addEventListener("click", async () => {
  const data = await api("/api/secret/regenerate", {});
  if (data) $("secret-code").value = data.code;
});

$("save-guild").addEventListener("click", async () => {
  try {
    await api("/api/guild", { guild_id: $("guild-id").value.trim() });
    refresh();
  } catch (err) {
    alert(err.message);
  }
});

$("sync-commands").addEventListener("click", async () => {
  try {
    const data = await api("/api/sync", {});
    if (data) alert(data.message);
  } catch (err) {
    alert(err.message);
  }
});

$("destroy").addEventListener("click", async () => {
  if (!confirm("Lancer la destruction du serveur ?")) return;
  try {
    await api("/api/destroy", {});
  } catch (err) {
    alert(err.message);
  }
  refresh();
});

$("stop").addEventListener("click", async () => {
  await api("/api/stop", {});
  refresh();
});

$("clear-logs").addEventListener("click", async () => {
  await api("/api/logs/clear", {});
  refresh();
});

function renderLogs(logs) {
  const consoleEl = $("console");
  consoleEl.textContent = "";
  logs.forEach((entry) => {
    const line = document.createElement("div");
    line.className = entry.level;
    const time = new Date(entry.ts * 1000).toLocaleTimeString("fr-FR");
    line.textContent = `[${time}] ${entry.message}`;
    consoleEl.appendChild(line);
  });
}

function renderState(state) {
  const bot = state.bot;
  $("bot-badge").textContent = bot.ready ? "en ligne" : "hors ligne";
  $("bot-badge").classList.toggle("online", bot.ready);
  $("bot-line").textContent = bot.guild
    ? `${bot.guild.name} · ${bot.guild.members} membres · ${bot.guild.channels} salons`
    : bot.user
      ? `connecté en ${bot.user} — aucun serveur cible`
      : "bot non connecté";

  $("guild-list").textContent = state.guilds.length
    ? "Serveurs disponibles : " + state.guilds.map((g) => `${g.name} (${g.id})`).join(", ")
    : "Aucun serveur visible. Invitez le bot puis synchronisez les commandes.";

  const d = state.destruction;
  $("progress-bar").style.width = d.percent + "%";
  $("progress-text").textContent = d.running
    ? `${d.step} — ${d.done}/${d.total} (${d.percent}%) — ${d.elapsed ?? 0}s`
    : d.finished_at
      ? `dernière exécution : ${d.step} — ${d.done}/${d.total}, ${d.errors} erreur(s)`
      : "au repos";

  const counters = Object.entries(d.counters || {});
  $("counters").textContent = counters.length
    ? counters.map(([key, value]) => `${key.replaceAll("_", " ")} : ${value}`).join(" · ")
    : "";

  $("destroy").disabled = d.running;
  $("stop").disabled = !d.running;

  renderLogs(state.logs || []);
}

async function refresh() {
  try {
    const res = await fetch("/api/state");
    if (res.status === 401) {
      window.location.href = "/login";
      return;
    }
    renderState(await res.json());
  } catch (err) {
    $("bot-line").textContent = "dashboard injoignable";
  }
}

refresh();
setInterval(refresh, 1500);
