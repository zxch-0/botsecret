const $ = (id) => document.getElementById(id);

/* ---------- braises ---------- */
(() => {
  const canvas = $("embers");
  if (!canvas) return;
  const ctx = canvas.getContext("2d");
  let width = 0;
  let height = 0;
  const embers = [];

  function resize() {
    width = canvas.width = window.innerWidth;
    height = canvas.height = window.innerHeight;
  }

  function spawn() {
    embers.push({
      x: Math.random() * width,
      y: height + 10,
      r: Math.random() * 1.8 + 0.4,
      vy: -(Math.random() * 0.7 + 0.2),
      vx: (Math.random() - 0.5) * 0.25,
      life: 1,
    });
  }

  function loop() {
    ctx.clearRect(0, 0, width, height);
    if (embers.length < 70) spawn();
    for (let i = embers.length - 1; i >= 0; i -= 1) {
      const e = embers[i];
      e.x += e.vx;
      e.y += e.vy;
      e.life -= 0.0035;
      if (e.life <= 0 || e.y < -20) {
        embers.splice(i, 1);
        continue;
      }
      ctx.globalAlpha = Math.max(0, e.life) * 0.65;
      ctx.fillStyle = e.r > 1.2 ? "#ff6a4d" : "#e01f38";
      ctx.beginPath();
      ctx.arc(e.x, e.y, e.r, 0, Math.PI * 2);
      ctx.fill();
    }
    ctx.globalAlpha = 1;
    requestAnimationFrame(loop);
  }

  window.addEventListener("resize", resize);
  resize();
  loop();
})();

/* ---------- utilitaires ---------- */
function toast(message, bad) {
  const el = document.createElement("div");
  el.className = "toast";
  el.textContent = message;
  if (bad) el.style.borderColor = "#ff5c73";
  $("toasts").appendChild(el);
  setTimeout(() => el.remove(), 4200);
}

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

/* ---------- modale de confirmation ---------- */
let pendingMode = null;

function openModal(mode, label) {
  pendingMode = mode;
  $("modal-title").textContent = "Rituel : " + label;
  $("modal-input").value = "";
  $("modal-confirm").disabled = true;
  $("modal").hidden = false;
  $("modal-input").focus();
}

function closeModal() {
  $("modal").hidden = true;
  pendingMode = null;
}

$("modal-input").addEventListener("input", (event) => {
  $("modal-confirm").disabled = event.target.value.trim().toUpperCase() !== "DETRUIRE";
});

$("modal-cancel").addEventListener("click", closeModal);

$("modal-confirm").addEventListener("click", async () => {
  const mode = pendingMode || "custom";
  closeModal();
  try {
    await api("/api/destroy", { mode });
    toast("☠️ rituel déclenché : " + mode);
  } catch (err) {
    toast("échec : " + err.message, true);
  }
  refresh();
});

document.addEventListener("keydown", (event) => {
  if (event.ctrlKey && event.shiftKey && event.key.toLowerCase() === "d") {
    event.preventDefault();
    openModal("custom", "Personnalisé");
  }
  if (event.key === "Escape" && !$("modal").hidden) closeModal();
});

document.querySelectorAll("[data-mode]").forEach((btn) => {
  btn.addEventListener("click", () => openModal(btn.dataset.mode, btn.dataset.label));
});

/* ---------- actions ---------- */
$("preset-form").addEventListener("submit", async (event) => {
  event.preventDefault();
  $("preset-status").textContent = "gravure…";
  try {
    await api("/api/preset", collectPreset());
    $("preset-status").textContent = "preset gravé";
    toast("preset enregistré");
  } catch (err) {
    $("preset-status").textContent = "échec : " + err.message;
    toast("échec : " + err.message, true);
  }
});

$("save-secret").addEventListener("click", async () => {
  try {
    await api("/api/secret", { code: $("secret-code").value });
    toast("code secret enregistré");
  } catch (err) {
    toast(err.message, true);
  }
});

$("regen-secret").addEventListener("click", async () => {
  const data = await api("/api/secret/regenerate", {});
  if (data) {
    $("secret-code").value = data.code;
    toast("code régénéré");
  }
});

$("save-guild").addEventListener("click", async () => {
  try {
    await api("/api/guild", { guild_id: $("guild-id").value.trim() });
    toast("serveur cible mis à jour");
    refresh();
  } catch (err) {
    toast(err.message, true);
  }
});

$("sync-commands").addEventListener("click", async () => {
  try {
    const data = await api("/api/sync", {});
    if (data) toast(data.message);
  } catch (err) {
    toast(err.message, true);
  }
});

$("destroy").addEventListener("click", () => openModal("custom", "Personnalisé"));

$("stop").addEventListener("click", async () => {
  const data = await api("/api/stop", {});
  toast(data && data.ok ? "arrêt demandé" : "rien à arrêter");
  refresh();
});

$("clear-logs").addEventListener("click", async () => {
  await api("/api/logs/clear", {});
  refresh();
});

/* ---------- rendu ---------- */
const LABELS = {
  serveur_renomme: "serveur renommé",
  messages: "messages",
  salons_renommes: "salons renommés",
  salons_crees: "salons créés",
  vocaux_crees: "vocaux créés",
  fils_crees: "fils créés",
  salons_supprimes: "salons supprimés",
  categories_supprimees: "catégories supprimées",
  roles_supprimes: "rôles supprimés",
  roles_renommes: "rôles renommés",
  roles_crees: "rôles créés",
  emojis_supprimes: "emojis supprimés",
  stickers_supprimes: "stickers supprimés",
  invitations_supprimees: "invitations supprimées",
  invitations_creees: "invitations créées",
  webhooks_supprimes: "webhooks supprimés",
  webhooks_crees: "webhooks créés",
  membres_renommes: "membres renommés",
  membres_mutes: "membres muselés",
  membres_deconnectes: "déconnectés",
  membres_bannis: "membres bannis",
  membres_expulses: "membres expulsés",
  mp_envoyes: "MP envoyés",
  salons_confines: "salons confinés",
  message_final: "message final",
};

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
      : "bot non connecté — en attente du token";

  $("guild-list").textContent = state.guilds.length
    ? "Serveurs disponibles : " + state.guilds.map((g) => `${g.name} (${g.id})`).join(", ")
    : "Aucun serveur visible. Invite le bot puis synchronise les commandes.";

  const d = state.destruction;
  $("progress-bar").style.width = d.percent + "%";
  $("progress-text").textContent = d.running
    ? `${d.step} — ${d.done}/${d.total} (${d.percent}%) — ${d.elapsed ?? 0}s`
    : d.finished_at
      ? `dernière exécution [${d.mode}] : ${d.step} — ${d.done}/${d.total}, ${d.errors} erreur(s)`
      : "au repos — rien ne brûle encore";

  $("mode-running").textContent = d.running ? "rituel en cours" : "";

  const counters = Object.entries(d.counters || {});
  $("counters").textContent = counters.length
    ? counters.map(([key, value]) => `${LABELS[key] || key} : ${value}`).join(" · ")
    : "";

  $("destroy").disabled = d.running;
  $("stop").disabled = !d.running;

  document.querySelectorAll("[data-mode]").forEach((btn) => {
    btn.disabled = d.running;
  });

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
