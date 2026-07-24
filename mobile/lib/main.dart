// mobile/lib/main.dart
// ABM 2.0 — Phase v1.0 Flutter Mobile Node
//
// Entry point. Initialises flutter_foreground_task before runApp so the
// task handler is registered at the earliest possible moment (required by
// the plugin for correct Android Foreground Service lifecycle management).

import 'package:flutter/material.dart';
import 'package:flutter_foreground_task/flutter_foreground_task.dart';

import 'app.dart';
import 'features/foreground/service/abm_foreground_service.dart';

import 'features/sync/crypto/cross_node_key_store.dart';
import 'features/sync/crypto/sync_crypto_channel.dart';
import 'features/sync/repository/cross_node_sync_repository.dart';
import 'features/sync/settings/sync_settings_service.dart';

/// Top-level task handler callback — must be a top-level function, not a
/// closure or instance method, per flutter_foreground_task requirements.
@pragma('vm:entry-point')
void startCallback() {
  FlutterForegroundTask.setTaskHandler(AbmTaskHandler());
}

Future<void> main() async {
  WidgetsFlutterBinding.ensureInitialized();

  // Register the task handler before the Flutter engine starts rendering.
  // This is required for the foreground service to survive app restarts.
  FlutterForegroundTask.initCommunicationPort();

  final settingsService = SyncSettingsService();
  final baseUrl = await settingsService.getBaseUrl();
  final keyStore = CrossNodeKeyStore();
  final channel = SyncCryptoChannel(keyStore: keyStore, nodeId: 'flutter_node');
  final syncRepo = CrossNodeSyncRepository(baseUrl: baseUrl, channel: channel);

  runApp(AbmMobileApp(syncRepository: syncRepo));
}
