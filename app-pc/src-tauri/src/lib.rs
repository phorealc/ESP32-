//! Coquille PC du Dashboard Phorealc.
//!
//! Le role de cette application est volontairement mince : elle lance le moteur
//! Python en sidecar, affiche l'interface web locale, et vit dans la barre des
//! taches. Toute la logique metier reste cote moteur, partagee avec l'ESP32.

use std::sync::Mutex;

use tauri::{
    menu::{Menu, MenuItem},
    tray::TrayIconBuilder,
    Emitter, Manager, RunEvent, State, WindowEvent,
};
use tauri_plugin_shell::process::{CommandChild, CommandEvent};
use tauri_plugin_shell::ShellExt;
use tauri_plugin_updater::UpdaterExt;

/// Nom du sidecar.
///
/// C'est bien le nom **sans chemin**, meme si `tauri.conf.json` declare
/// `binaries/dashboard-engine` : ce dernier designe l'emplacement dans les
/// sources, alors qu'a l'execution Tauri resout le sidecar dans le dossier de
/// l'executable (`relative_command_path` fait `dossier_exe.join(nom)`).
/// Passer le chemin complet ferait chercher `<install>/binaries/...`, qui
/// n'existe pas — et le moteur ne demarrerait jamais.
const ENGINE_SIDECAR: &str = "dashboard-engine";

/// Etat du moteur, expose au frontend pour qu'il puisse expliquer une panne
/// au lieu d'afficher « connexion… » indefiniment.
#[derive(Clone, serde::Serialize)]
struct EngineStatus {
    /// True si le processus sidecar a bien demarre.
    spawned: bool,
    /// Message lisible : cause de l'echec, ou mode de fonctionnement.
    detail: String,
}

impl Default for EngineStatus {
    fn default() -> Self {
        Self {
            spawned: false,
            detail: "demarrage en cours".into(),
        }
    }
}

#[derive(Default)]
struct Engine {
    child: Mutex<Option<CommandChild>>,
    status: Mutex<EngineStatus>,
}

impl Engine {
    fn set_status(&self, spawned: bool, detail: impl Into<String>) {
        let detail = detail.into();
        log_line(&detail);
        if let Ok(mut guard) = self.status.lock() {
            *guard = EngineStatus { spawned, detail };
        }
    }
}

/// Adresse du moteur, exposee au frontend pour eviter de la coder en dur en JS.
#[tauri::command]
fn engine_url() -> String {
    // Le moteur ecoute en local ; l'ESP32 le joint par l'IP LAN, la coquille
    // par la boucle locale.
    std::env::var("DASHBOARD_ENGINE_URL").unwrap_or_else(|_| "http://127.0.0.1:8787".into())
}

#[tauri::command]
fn engine_status(engine: State<'_, Engine>) -> EngineStatus {
    engine
        .status
        .lock()
        .map(|status| status.clone())
        .unwrap_or_default()
}

/// Arrete le moteur. Idempotent : appele a la fermeture et au quit du tray.
fn stop_engine(engine: &Engine) {
    if let Ok(mut guard) = engine.child.lock() {
        if let Some(child) = guard.take() {
            let _ = child.kill();
        }
    }
}

/// Demarre le moteur en sidecar. Un echec n'est pas fatal : l'utilisateur peut
/// deja faire tourner `python -m dashboard_engine` a la main, auquel cas
/// l'interface se connectera au moteur existant.
fn start_engine(app: &tauri::AppHandle) {
    let engine = app.state::<Engine>();
    if engine.child.lock().map(|g| g.is_some()).unwrap_or(false) {
        return;
    }

    let command = match app.shell().sidecar(ENGINE_SIDECAR) {
        Ok(command) => command,
        Err(error) => {
            engine.set_status(
                false,
                format!("sidecar « {ENGINE_SIDECAR} » introuvable ({error}) — la coquille se rabat sur un moteur lance a la main"),
            );
            return;
        }
    };

    match command.spawn() {
        Ok((receiver, child)) => {
            if let Ok(mut guard) = engine.child.lock() {
                *guard = Some(child);
            }
            engine.set_status(true, "moteur demarre en sidecar");
            forward_engine_output(app.clone(), receiver);
        }
        Err(error) => engine.set_status(false, format!("echec du demarrage du moteur : {error}")),
    }
}

/// Recopie la sortie du moteur dans celle de la coquille.
///
/// Sans ca, un moteur qui s'arrete au demarrage (configuration illisible, port
/// occupe) le fait en silence : l'interface reste sur « connexion… » sans que
/// rien n'explique pourquoi.
fn forward_engine_output(
    app: tauri::AppHandle,
    mut receiver: tauri::async_runtime::Receiver<CommandEvent>,
) {
    tauri::async_runtime::spawn(async move {
        while let Some(event) = receiver.recv().await {
            match event {
                CommandEvent::Stdout(line) | CommandEvent::Stderr(line) => {
                    log_line(&format!("moteur: {}", String::from_utf8_lossy(&line).trim_end()));
                }
                CommandEvent::Error(error) => {
                    app.state::<Engine>()
                        .set_status(false, format!("erreur du moteur : {error}"));
                }
                CommandEvent::Terminated(payload) => {
                    app.state::<Engine>().set_status(
                        false,
                        format!("le moteur s'est arrete (code {:?})", payload.code),
                    );
                    break;
                }
                _ => {}
            }
        }
    });
}


// --- mise a jour automatique ---------------------------------------------

/// Description d'une mise a jour disponible, envoyee au frontend.
#[derive(Clone, serde::Serialize)]
struct UpdateInfo {
    version: String,
    current_version: String,
    notes: String,
}

/// Cherche une mise a jour. `Ok(None)` = deja a jour.
///
/// Une erreur ici n'a rien de dramatique (pas de reseau, cle de signature non
/// configuree) : on la remonte au frontend, qui reste silencieux.
#[tauri::command]
async fn check_update(app: tauri::AppHandle) -> Result<Option<UpdateInfo>, String> {
    let updater = app.updater().map_err(|error| error.to_string())?;
    let update = updater.check().await.map_err(|error| error.to_string())?;
    Ok(update.map(|update| UpdateInfo {
        version: update.version.clone(),
        current_version: update.current_version.clone(),
        notes: update.body.clone().unwrap_or_default(),
    }))
}

/// Telecharge et installe la mise a jour.
///
/// Sous Windows, Tauri lance l'installeur puis quitte l'application : cette
/// fonction ne rend donc pas la main en cas de succes.
#[tauri::command]
async fn install_update(app: tauri::AppHandle) -> Result<(), String> {
    let updater = app.updater().map_err(|error| error.to_string())?;
    let update = updater
        .check()
        .await
        .map_err(|error| error.to_string())?
        .ok_or_else(|| "aucune mise a jour disponible".to_string())?;

    log_line(&format!("installation de la version {}", update.version));
    // Le moteur doit liberer son port avant que l'installeur ne remplace les
    // fichiers, sinon la nouvelle version trouve le port 8787 occupe.
    stop_engine(&app.state::<Engine>());
    update
        .download_and_install(|_chunk, _total| {}, || {})
        .await
        .map_err(|error| error.to_string())
}

/// Verifie les mises a jour au demarrage et previent le frontend s'il y en a une.
fn check_update_on_startup(app: tauri::AppHandle) {
    tauri::async_runtime::spawn(async move {
        match check_update(app.clone()).await {
            Ok(Some(info)) => {
                log_line(&format!("mise a jour disponible : {}", info.version));
                let _ = app.emit("update-available", info);
            }
            Ok(None) => log_line("application a jour"),
            Err(error) => log_line(&format!("verification des mises a jour impossible : {error}")),
        }
    });
}

fn log_line(message: &str) {
    println!("[dashboard-pc] {message}");
}

fn build_tray(app: &tauri::AppHandle) -> tauri::Result<()> {
    let show = MenuItem::with_id(app, "show", "Afficher le dashboard", true, None::<&str>)?;
    let quit = MenuItem::with_id(app, "quit", "Quitter", true, None::<&str>)?;
    let menu = Menu::with_items(app, &[&show, &quit])?;

    let mut tray = TrayIconBuilder::with_id("main").tooltip("Dashboard Phorealc");
    if let Some(icon) = app.default_window_icon().cloned() {
        tray = tray.icon(icon);
    }

    tray.menu(&menu)
        .show_menu_on_left_click(false)
        .on_menu_event(|app, event| match event.id().as_ref() {
            "show" => {
                if let Some(window) = app.get_webview_window("main") {
                    let _ = window.show();
                    let _ = window.set_focus();
                }
            }
            "quit" => {
                stop_engine(&app.state::<Engine>());
                app.exit(0);
            }
            _ => {}
        })
        .build(app)?;
    Ok(())
}

#[cfg_attr(mobile, tauri::mobile_entry_point)]
pub fn run() {
    tauri::Builder::default()
        .plugin(tauri_plugin_shell::init())
        .plugin(tauri_plugin_updater::Builder::new().build())
        .plugin(tauri_plugin_autostart::init(
            tauri_plugin_autostart::MacosLauncher::LaunchAgent,
            None,
        ))
        .manage(Engine::default())
        .invoke_handler(tauri::generate_handler![
            engine_url,
            engine_status,
            check_update,
            install_update
        ])
        .setup(|app| {
            start_engine(app.handle());
            build_tray(app.handle())?;
            check_update_on_startup(app.handle().clone());
            Ok(())
        })
        .on_window_event(|window, event| {
            // Fermer la fenetre replie l'application dans la barre des taches :
            // le dashboard doit continuer a tourner pour alimenter l'ESP32.
            if let WindowEvent::CloseRequested { api, .. } = event {
                api.prevent_close();
                let _ = window.hide();
            }
        })
        .build(tauri::generate_context!())
        .expect("erreur au demarrage de Tauri")
        .run(|app, event| {
            if let RunEvent::ExitRequested { .. } | RunEvent::Exit = event {
                stop_engine(&app.state::<Engine>());
            }
        });
}
