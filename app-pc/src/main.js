// Frontend de la coquille Tauri.
//
// La coquille ne fait aucun calcul : elle rend l'etat pousse par le moteur sur
// le websocket, exactement comme l'ESP32 rend celui qu'il recupere en HTTP.
// Une seule source de verite, deux affichages.

const DEFAULT_ENGINE_URL = "http://127.0.0.1:8787";
const RECONNECT_DELAY_MS = 2000;

/** Resout l'URL du moteur : commande Tauri si disponible, sinon valeur par defaut. */
async function resolveEngineUrl() {
  try {
    const { invoke } = window.__TAURI__.core;
    return await invoke("engine_url");
  } catch {
    // Ouvert dans un simple navigateur (developpement du CSS, par exemple).
    return DEFAULT_ENGINE_URL;
  }
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

function renderLink(status) {
  const map = {
    connected: ["ok", "Moteur connecte"],
    connecting: ["warn", "Connexion au moteur…"],
    offline: ["error", "Moteur injoignable"],
  };
  const [variant, text] = map[status] ?? map.connecting;
  setDot($("link-dot"), variant);
  $("link-text").textContent = text;
}

function renderMusic(music) {
  const card = document.querySelector(".card-music");
  setCardAvailability(card, music.available);

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

  const obs = stream.obs ?? {};
  setDot($("obs-dot"), obs.connected ? (obs.streaming ? "live" : "ok") : "");
  $("obs-text").textContent = obs.connected
    ? `OBS · ${obs.scene || "sans scene"} · ${Math.round(obs.fps)} fps · ${obs.dropped_frames_pct.toFixed(1)} % perdues${obs.recording ? " · REC" : ""}`
    : "OBS deconnecte";
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
  const connect = () => {
    renderLink("connecting");
    const socket = new WebSocket(wsUrl);

    socket.addEventListener("open", () => renderLink("connected"));
    socket.addEventListener("message", (event) => {
      try {
        render(JSON.parse(event.data));
      } catch (error) {
        console.warn("payload illisible", error);
      }
    });
    socket.addEventListener("close", () => {
      renderLink("offline");
      setTimeout(connect, RECONNECT_DELAY_MS);
    });
    socket.addEventListener("error", () => socket.close());
  };

  connect();
}

main();
