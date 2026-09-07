//! Coquille PC du Dashboard Phorealc.
//!
//! Le role de cette application est volontairement mince : elle lance le moteur
//! Python en sidecar, affiche l'interface web locale, et vit dans la barre des
//! taches. Toute la logique metier reste cote moteur, partagee avec l'ESP32.

use std::sync::Mutex;

use tauri::{
    menu::{Menu, MenuItem},
    tray::TrayIconBuilder,
    Manager, RunEvent, State, WindowEvent,
};
use tauri_plugin_shell::process::CommandChild;
use tauri_plugin_shell::ShellExt;

/// Nom du binaire sidecar, tel que declare dans `tauri.conf.json`.
const ENGINE_SIDECAR: &str = "binaries/dashboard-engine";

/// Poignee sur le processus moteur, pour pouvoir le terminer proprement.
#[derive(Default)]
struct EngineProcess(Mutex<Option<CommandChild>>);

/// Adresse du moteur, exposee au frontend pour eviter de la coder en dur en JS.
#[tauri::command]
fn engine_url() -> String {
    // Le moteur ecoute en local ; l'ESP32 le joint par l'IP LAN, la coquille
    // par la boucle locale.
    std::env::var("DASHBOARD_ENGINE_URL").unwrap_or_else(|_| "http://127.0.0.1:8787".into())
}

/// Arrete le moteur. Idempotent : appele a la fermeture et au quit du tray.
fn stop_engine(state: &EngineProcess) {
    if let Ok(mut guard) = state.0.lock() {
        if let Some(child) = guard.take() {
            let _ = child.kill();
        }
    }
}

/// Demarre le moteur en sidecar. Un echec n'est pas fatal : l'utilisateur peut
/// deja faire tourner `python -m dashboard_engine` a la main, auquel cas
/// l'interface se connectera au moteur existant.
fn start_engine(app: &tauri::AppHandle) {
    let state = app.state::<EngineProcess>();
    if state.0.lock().map(|g| g.is_some()).unwrap_or(false) {
        return;
    }

    match app.shell().sidecar(ENGINE_SIDECAR) {
        Ok(command) => match command.spawn() {
            Ok((_rx, child)) => {
                if let Ok(mut guard) = state.0.lock() {
                    *guard = Some(child);
                }
                log_line("moteur demarre en sidecar");
            }
            Err(error) => log_line(&format!("echec du demarrage du moteur: {error}")),
        },
        Err(error) => log_line(&format!(
            "sidecar introuvable ({error}) — la coquille se rabattra sur un moteur deja lance"
        )),
    }
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

    tray
        .menu(&menu)
        .show_menu_on_left_click(false)
        .on_menu_event(|app, event| match event.id().as_ref() {
            "show" => {
                if let Some(window) = app.get_webview_window("main") {
                    let _ = window.show();
                    let _ = window.set_focus();
                }
            }
            "quit" => {
                stop_engine(&app.state::<EngineProcess>());
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
        .plugin(tauri_plugin_autostart::init(
            tauri_plugin_autostart::MacosLauncher::LaunchAgent,
            None,
        ))
        .manage(EngineProcess::default())
        .invoke_handler(tauri::generate_handler![engine_url])
        .setup(|app| {
            start_engine(app.handle());
            build_tray(app.handle())?;
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
                stop_engine(&app.state::<EngineProcess>());
            }
        });
}
