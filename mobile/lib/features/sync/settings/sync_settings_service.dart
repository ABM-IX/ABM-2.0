// mobile/lib/features/sync/settings/sync_settings_service.dart
// ABM 2.0 — Sync settings persistence.
//
// Stores the desktop sync base URL in SharedPreferences so users can
// change the address at runtime without rebuilding the app.
// This is non-secret configuration; secrets (AES key) stay in
// flutter_secure_storage via CrossNodeKeyStore.

import 'package:shared_preferences/shared_preferences.dart';

/// Default desktop sync daemon address.
/// Change only here (or via the settings screen); never inline elsewhere.
const String kDefaultSyncBaseUrl = 'http://172.24.56.26:8765';

/// SharedPreferences key used to persist the user-configured URL.
const String kSyncBaseUrlPrefKey = 'abm_sync_base_url';

/// Light-weight service that reads / writes the desktop sync URL.
///
/// All callers that need the active base URL should call [getBaseUrl].
/// [CrossNodeSyncRepository] is constructed with this value at boot and
/// rebuilt whenever the user saves a new address in [SyncSettingsScreen].
class SyncSettingsService {
  SyncSettingsService({SharedPreferences? prefs}) : _prefs = prefs;

  SharedPreferences? _prefs;

  /// Returns the currently persisted base URL, or [kDefaultSyncBaseUrl] if
  /// no value has been saved yet.
  Future<String> getBaseUrl() async {
    await _ensurePrefs();
    return _prefs!.getString(kSyncBaseUrlPrefKey) ?? kDefaultSyncBaseUrl;
  }

  /// Persists [url] so it survives app restarts.
  /// Does NOT validate the URL format — callers (e.g. [SyncSettingsScreen])
  /// are responsible for basic validation before calling this.
  Future<void> setBaseUrl(String url) async {
    await _ensurePrefs();
    await _prefs!.setString(kSyncBaseUrlPrefKey, url);
  }

  /// Clears any saved URL, reverting to [kDefaultSyncBaseUrl] on next read.
  Future<void> resetToDefault() async {
    await _ensurePrefs();
    await _prefs!.remove(kSyncBaseUrlPrefKey);
  }

  Future<void> _ensurePrefs() async {
    _prefs ??= await SharedPreferences.getInstance();
  }
}
