// Frontend de la coquille Tauri.
//
// La coquille ne fait aucun calcul : elle rend l'etat pousse par le moteur sur
// le websocket, exactement comme l'ESP32 rend celui qu'il recupere en HTTP.
// Une seule source de verite, deux affichages.

const DEFAULT_ENGINE_URL = "http://127.0.0.1:8787";
const RECONNECT_DELAY_MS = 2000;

// Le moteur est un binaire PyInstaller : son demarrage prend quelques secondes.
// On ne parle d'echec qu'apres plusieurs tentatives, sinon on alarmerait pour
// un simple demarrage a froid.
const ATTEMPTS_BEFORE_DIAGNOSIS = 4;

/** Appelle une commande Rust, ou renvoie `null` hors contexte Tauri. */
async function callTauri(command) {
  try {
    return await window.__TAURI__.core.invoke(command);
  } catch {
    // Page ouverte dans un simple navigateur (developpement du CSS).
    return null;
  }
}

/** Bandeau de mise a jour : propose, sans jamais interrompre le dashboard. */
function setupUpdates() {
  const bar = $("update-bar");
  const text = $("update-text");

  const show = (info) => {
    text.textContent = `Version ${info.version} disponible (vous avez la ${info.current_version}).`;
    bar.hidden = false;
  };

  $("update-dismiss").addEventListener("click", () => {
    bar.hidden = true;
  });

  $("update-install").addEventListener("click", async () => {
    bar.classList.add("busy");
    text.textContent = "Telechargement de la mise a jour…";
    try {
      // Sous Windows, l'application se ferme d'elle-meme pour laisser la main
      // a l'installeur : si on revient ici, c'est que ca a echoue.
      await window.__TAURI__.core.invoke("install_update");
    } catch (error) {
      text.textContent = `Mise a jour impossible : ${error}`;
      bar.classList.remove("busy");
    }
  });

  // Le Rust previent au demarrage ; on interroge aussi une fois, au cas ou
  // l'evenement serait parti avant que la page ne soit prete.
  window.__TAURI__?.event
    ?.listen("update-available", (event) => show(event.payload))
    .catch(() => {});
  callTauri("check_update").then((info) => {
    if (info) show(info);
  });
}

async function resolveEngineUrl() {
  return (await callTauri("engine_url")) ?? DEFAULT_ENGINE_URL;
}

const $ = (id) => document.getElementById(id);

const fmtDuration = (seconds) => {
  const total = Math.max(0, Math.floor(seconds || 0));
  const h = Math.floor(total / 3600);
  const m = Math.floor((total % 3600) / 60);
  const s = total % 60;
  const pad = (n) => String(n).padStart(2, "0");
  return h > 0 ? `${h}:${pad(m)}:${pad(s)}` : `${m}:${pad(s)}`;
};

const setCardAvailability = (element, available) =>
  element.classList.toggle("unavailable", !available);

const setDot = (element, variant) => {
  element.className = `dot${variant ? ` ${variant}` : ""}`;
};

// --- rendu ----------------------------------------------------------------

function renderLink(status, detail = "") {
  const map = {
    connected: ["ok", "Moteur connecte"],
    connecting: ["warn", "Connexion au moteur…"],
    offline: ["error", "Moteur injoignable"],
  };
  const [variant, text] = map[status] ?? map.connecting;
  setDot($("link-dot"), variant);
  $("link-text").textContent = detail ? `${text} — ${detail}` : text;
  $("link").title = detail;
}

/** Etat courant, garde pour la recherche : on ne relit pas le DOM pour ca. */
let lastMusic = { duration_s: 0, controls: {} };

function renderMusic(music) {
  const card = document.querySelector(".card-music");
  setCardAvailability(card, music.available);
  lastMusic = music;

  const controls = music.controls ?? {};
  // Les capacites viennent du lecteur : Spotify accepte « suivant », un onglet
  // YouTube souvent non.
  $("music-previous").disabled = !music.available || !controls.can_previous;
  $("music-next").disabled = !music.available || !controls.can_next;
  $("music-toggle").disabled =
    !music.available || !(music.playing ? controls.can_pause : controls.can_play);
  $("music-toggle").textContent = music.playing ? "\u23F8" : "\u25B6";
  $("music-bar").classList.toggle("seekable", Boolean(music.available && controls.can_seek));

  if (!music.available) {
    $("music-state").textContent = "Module indisponible";
    $("music-title").textContent = "Musique hors service";
    $("music-artist").textContent = music.error ?? "";
    $("music-progress").style.width = "0%";
    return;
  }

  const hasTrack = Boolean(music.title);
  $("music-state").textContent = music.playing ? "En lecture" : hasTrack ? "En pause" : "Silence";
  $("music-title").textContent = hasTrack ? music.title : "Aucune lecture";
  $("music-artist").textContent = [music.artist, music.album].filter(Boolean).join(" — ");

  const ratio = music.duration_s > 0 ? music.position_s / music.duration_s : 0;
  $("music-progress").style.width = `${Math.min(100, Math.max(0, ratio * 100))}%`;
  $("music-elapsed").textContent = fmtDuration(music.position_s);
  $("music-total").textContent = fmtDuration(music.duration_s);
}

function renderWeather(weather) {
  const card = document.querySelector(".card-weather");
  setCardAvailability(card, weather.available);

  if (!weather.available) {
    $("weather-city").textContent = "Module indisponible";
    $("weather-temp").textContent = "--°";
    $("weather-desc").textContent = weather.error ?? "";
    $("weather-stats").replaceChildren();
    return;
  }

  $("weather-city").textContent = weather.city;
  $("weather-temp").textContent = `${Math.round(weather.temp_c)}°`;
  $("weather-desc").textContent = weather.description;
  renderStats($("weather-stats"), [
    ["Ressenti", `${Math.round(weather.feels_like_c)}°`],
    ["Humidite", `${weather.humidity} %`],
    ["Vent", `${Math.round(weather.wind_kph)} km/h`],
  ]);
}

function renderStream(stream) {
  const card = document.querySelector(".card-stream");
  setCardAvailability(card, stream.available);

  const badge = $("stream-badge");
  badge.classList.toggle("live", stream.live);
  badge.textContent = stream.live ? "EN DIRECT" : stream.available ? "HORS LIGNE" : "INDISPO.";

  $("stream-title").textContent = stream.title || "—";
  $("stream-game").textContent = stream.game || "";
  renderStats($("stream-stats"), [
    ["Spectateurs", stream.live ? String(stream.viewers) : "—"],
    ["Followers", stream.followers > 0 ? String(stream.followers) : "—"],
    ["A l'antenne", stream.live && stream.uptime_s > 0 ? fmtDuration(stream.uptime_s) : "—"],
  ]);

  const obs = stream.broadcaster ?? {};
  // Nommer le vrai logiciel : « OBS deconnecte » chez un utilisateur de
  // Streamlabs l'enverrait chercher au mauvais endroit.
  const software = obs.kind === "streamlabs" ? "Streamlabs" : obs.kind === "obs" ? "OBS" : "";
  setDot($("obs-dot"), obs.connected ? (obs.streaming ? "live" : "ok") : "");
  $("obs-text").textContent = obs.connected
    ? `${software} · ${obs.scene || "sans scene"} · ${Math.round(obs.fps)} fps · ${(obs.dropped_frames_pct ?? 0).toFixed(1)} % perdues${obs.recording ? " · REC" : ""}`
    : software
      ? `${software} deconnecte`
      : "Aucun logiciel de diffusion configure";
}

function renderStats(container, entries) {
  container.replaceChildren(
    ...entries.map(([key, value]) => {
      const li = document.createElement("li");
      const k = document.createElement("span");
      k.className = "k";
      k.textContent = key;
      const v = document.createElement("span");
      v.className = "v";
      v.textContent = value;
      li.append(k, v);
      return li;
    }),
  );
}

function renderServers(servers) {
  const card = document.querySelector(".card-servers");
  setCardAvailability(card, servers.available);

  const total = servers.items.filter((s) => s.online).reduce((n, s) => n + s.players_online, 0);
  $("servers-summary").textContent = servers.available
    ? `${total} joueur${total > 1 ? "s" : ""} en ligne`
    : (servers.error ?? "Module indisponible");

  const list = $("server-list");
  if (servers.items.length === 0) {
    list.replaceChildren(emptyRow("Aucun serveur declare dans config.toml"));
    return;
  }

  list.replaceChildren(
    ...servers.items.map((server) => {
      const li = document.createElement("li");

      const dot = document.createElement("span");
      setDot(dot, server.online ? "ok" : "error");

      const info = document.createElement("div");
      const name = document.createElement("span");
      name.className = "name";
      name.textContent = server.name;
      const meta = document.createElement("span");
      meta.className = "meta";
      meta.textContent = server.online
        ? [server.version, `${server.latency_ms} ms`, server.motd].filter(Boolean).join(" · ")
        : "Hors ligne";
      info.append(name, meta);

      const players = document.createElement("span");
      players.className = `players${server.online ? "" : " off"}`;
      players.textContent = server.online ? `${server.players_online}/${server.players_max}` : "—";

      li.append(dot, info, players);
      return li;
    }),
  );
}

function emptyRow(text) {
  const li = document.createElement("li");
  li.className = "empty";
  li.textContent = text;
  return li;
}

function renderChecklist(checklist, actions) {
  const done = checklist.items.filter((item) => item.done).length;
  const ratio = checklist.items.length > 0 ? (done / checklist.items.length) * 100 : 0;
  $("checklist-progress").style.width = `${ratio}%`;
  $("checklist-caption").textContent = `Checklist — ${done} / ${checklist.items.length}`;

  const list = $("checklist");
  if (checklist.items.length === 0) {
    list.replaceChildren(emptyRow("Aucune tache — ajoutez-en une ci-dessous"));
    return;
  }

  list.replaceChildren(
    ...checklist.items.map((item) => {
      const li = document.createElement("li");
      li.classList.toggle("done", item.done);

      const box = document.createElement("span");
      box.className = "box";
      box.textContent = "✓";

      const text = document.createElement("span");
      text.className = "text";
      text.textContent = item.label;

      const remove = document.createElement("button");
      remove.className = "remove";
      remove.type = "button";
      remove.title = "Supprimer";
      remove.textContent = "×";
      remove.addEventListener("click", (event) => {
        event.stopPropagation();  // sinon le clic bascule aussi la case
        actions.remove(item.id);
      });

      li.append(box, text, remove);
      li.addEventListener("click", () => actions.toggle(item.id, !item.done));
      return li;
    }),
  );
}

// --- liaison au moteur -----------------------------------------------------

async function main() {
  setupUpdates();
  const engineUrl = await resolveEngineUrl();
  const wsUrl = `${engineUrl.replace(/^http/, "ws")}/ws`;

  /** POST vers le moteur ; le prochain message websocket confirmera le resultat. */
  const post = async (path, body) => {
    try {
      const response = await fetch(`${engineUrl}${path}`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(body ?? {}),
      });
      if (!response.ok) console.warn(`${path} a repondu ${response.status}`);
    } catch (error) {
      console.warn(`${path} a echoue`, error);
    }
  };

  /** Pilote le lecteur du PC. L'etat reel revient au cycle suivant. */
  const music = (action, extra = {}) => post("/api/music/command", { action, ...extra });

  $("music-previous").addEventListener("click", () => music("previous"));
  $("music-next").addEventListener("click", () => music("next"));
  $("music-toggle").addEventListener("click", () => music("toggle"));

  // Clic sur la barre = recherche, seulement si le lecteur l'accepte.
  $("music-bar").addEventListener("click", (event) => {
    if (!lastMusic.controls?.can_seek || !(lastMusic.duration_s > 0)) return;
    const bar = event.currentTarget.getBoundingClientRect();
    const ratio = Math.min(1, Math.max(0, (event.clientX - bar.left) / bar.width));
    music("seek", { position_s: ratio * lastMusic.duration_s });
  });

  // Raccourcis clavier : le dashboard sert pendant un live, les mains sont
  // ailleurs. Ctrl evite de voler l'espace au champ de la checklist.
  document.addEventListener("keydown", (event) => {
    if (!event.ctrlKey || event.altKey || event.metaKey) return;
    const shortcuts = { " ": "toggle", ArrowRight: "next", ArrowLeft: "previous" };
    const action = shortcuts[event.key];
    if (!action) return;
    event.preventDefault();
    music(action);
  });

  const actions = {
    toggle: (id, done) => post("/api/checklist/toggle", { id, done }),
    add: (label) => post("/api/checklist/items", { label }),
    remove: async (id) => {
      try {
        await fetch(`${engineUrl}/api/checklist/items/${id}`, { method: "DELETE" });
      } catch (error) {
        console.warn("suppression impossible", error);
      }
    },
    reset: () => post("/api/checklist/reset"),
  };

  $("checklist-form").addEventListener("submit", (event) => {
    event.preventDefault();
    const input = $("checklist-input");
    const label = input.value.trim();
    if (!label) return;
    input.value = "";
    actions.add(label);
  });

  $("checklist-reset").addEventListener("click", () => actions.reset());

  const render = (state) => {
    renderMusic(state.music);
    renderWeather(state.weather);
    renderStream(state.stream);
    renderServers(state.servers);
    renderChecklist(state.checklist, actions);
  };

  // Reconnexion perpetuelle : le moteur peut redemarrer sans que l'utilisateur
  // ait a relancer la coquille.
  let attempts = 0;

  /** Explique *pourquoi* rien n'arrive, plutot que de boucler en silence. */
  const diagnose = async () => {
    if (attempts < ATTEMPTS_BEFORE_DIAGNOSIS) return "";
    const status = await callTauri("engine_status");
    if (status && !status.spawned) return status.detail;
    if (status) return `aucune reponse sur ${engineUrl}`;
    // Hors Tauri : c'est un moteur lance a la main qui manque.
    return `aucune reponse sur ${engineUrl} — le moteur est-il lance ?`;
  };

  const connect = () => {
    attempts += 1;
    renderLink("connecting");
    const socket = new WebSocket(wsUrl);

    socket.addEventListener("open", () => {
      attempts = 0;
      renderLink("connected");
    });
    socket.addEventListener("message", (event) => {
      try {
        render(JSON.parse(event.data));
      } catch (error) {
        console.warn("payload illisible", error);
      }
    });
    socket.addEventListener("close", async () => {
      renderLink("offline", await diagnose());
      setTimeout(connect, RECONNECT_DELAY_MS);
    });
    socket.addEventListener("error", () => socket.close());
  };

  connect();
}

main();
