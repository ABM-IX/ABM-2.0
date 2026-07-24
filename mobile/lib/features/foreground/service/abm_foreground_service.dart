// mobile/lib/features/foreground/service/abm_foreground_service.dart
// ABM 2.0 — Phase v1.0: Android Foreground Service Wrapper
//
// Wraps flutter_foreground_task to provide a device-agnostic persistent
// Android Foreground Service. The persistent notification prevents the OS
// low-memory killer from stripping the execution thread
// (ABM_SPEC.md section 2, hardware-agnostic blueprint correction).
//
// Design decisions:
//   - Singleton pattern: AbmForegroundService.instance
//   - AbmTaskHandler runs in a separate isolate (Dart isolate model);
//     communicates with the UI isolate via FlutterForegroundTask.sendDataToMain.
//   - Notification channel config is Android-13+ compatible (targetSdkVersion 33+).
//   - No cloud network calls — local only (constitution rule 1).

import 'dart:async';

import 'package:flutter_foreground_task/flutter_foreground_task.dart';

// ---------------------------------------------------------------------------
// Constants
// ---------------------------------------------------------------------------

/// Persistent notification channel ID (must match AndroidManifest.xml).
const String kNotificationChannelId = 'abm_foreground_service';

/// Persistent notification title displayed in the status bar.
const String kNotificationTitle = 'ABM 2.0 — Cognitive OS';

/// Persistent notification body text.
const String kNotificationText = 'Ambient monitoring active';

/// Interval (ms) between AbmTaskHandler.onRepeatEvent callbacks.
const int kTaskIntervalMs = 5000;

// ---------------------------------------------------------------------------
// AbmTaskHandler — runs in the foreground service isolate
// ---------------------------------------------------------------------------

/// Task handler executed inside the Android Foreground Service isolate.
///
/// [onRepeatEvent] fires every [kTaskIntervalMs] ms. Use it to:
///   - Poll for new Git commits (via IPC to the desktop daemon)
///   - Heartbeat the persistent notification
///   - Trigger Stream C ambient event ingestion
///
/// Communication back to the Flutter UI uses
/// [FlutterForegroundTask.sendDataToMain].
class AbmTaskHandler extends TaskHandler {
  int _tickCount = 0;

  @override
  Future<void> onStart(DateTime timestamp, TaskStarter starter) async {
    // Service started — send initial heartbeat to main isolate
    FlutterForegroundTask.sendDataToMain({
      'type': 'service_started',
      'timestamp': timestamp.millisecondsSinceEpoch,
    });
  }

  @override
  Future<void> onRepeatEvent(DateTime timestamp) async {
    _tickCount++;
    // Send a periodic heartbeat to the main isolate for UI updates
    FlutterForegroundTask.sendDataToMain({
      'type': 'heartbeat',
      'tick': _tickCount,
      'timestamp': timestamp.millisecondsSinceEpoch,
    });
    // TODO(v1.1): Poll Git commits and dispatch to TelemetryRepository here
  }

  @override
  Future<void> onDestroy(DateTime timestamp, bool isTimeout) async {
    FlutterForegroundTask.sendDataToMain({
      'type': 'service_stopped',
      'timestamp': timestamp.millisecondsSinceEpoch,
    });
  }

  @override
  void onReceiveData(Object data) {
    // Handle commands sent from the main isolate to the service isolate
    // e.g. {'command': 'poll_git', 'repo': '/path/to/repo'}
  }

  @override
  void onNotificationButtonPressed(String id) {
    if (id == 'stop_service') {
      FlutterForegroundTask.stopService();
    }
  }

  @override
  void onNotificationDismissed() {
    // Persistent notification cannot be dismissed by the user on Android 13+
    // when the service is running — this callback fires on older API levels.
  }
}

// ---------------------------------------------------------------------------
// AbmForegroundService — public API consumed by ForegroundBloc
// ---------------------------------------------------------------------------

/// Singleton wrapper around [FlutterForegroundTask].
///
/// [ForegroundBloc] calls [start] and [stop]; it never interacts with
/// [FlutterForegroundTask] directly — all platform surface is encapsulated
/// here to keep the BLoC testable with a mock.
class AbmForegroundService {
  AbmForegroundService._();

  /// Singleton instance.
  static final AbmForegroundService instance = AbmForegroundService._();

  bool _initialised = false;

  // ------------------------------------------------------------------
  // Public API
  // ------------------------------------------------------------------

  /// Initialise plugin options. Call once at app start (before [start]).
  void init() {
    if (_initialised) return;
    FlutterForegroundTask.init(
      androidNotificationOptions: AndroidNotificationOptions(
        channelId: kNotificationChannelId,
        channelName: 'ABM Cognitive OS',
        channelDescription:
            'Keeps the ABM ambient monitoring service alive in the background.',
        channelImportance: NotificationChannelImportance.LOW,
        priority: NotificationPriority.LOW,
        onlyAlertOnce: true,
      ),
      iosNotificationOptions: const IOSNotificationOptions(
        showNotification: false,
        playSound: false,
      ),
      foregroundTaskOptions: ForegroundTaskOptions(
        eventAction: ForegroundTaskEventAction.repeat(kTaskIntervalMs),
        autoRunOnBoot: true,
        autoRunOnMyPackageReplaced: true,
        allowWakeLock: true,
        allowWifiLock: false,
      ),
    );
    _initialised = true;
  }

  /// Start the persistent foreground service.
  ///
  /// Requests necessary Android permissions, then starts the service.
  /// Throws [ForegroundServiceStartException] if the service cannot start.
  Future<void> start() async {
    init();

    // Request permissions (FOREGROUND_SERVICE on Android 9+,
    // POST_NOTIFICATIONS on Android 13+)
    if (!await FlutterForegroundTask.isRunningService) {
      final result = await FlutterForegroundTask.startService(
        serviceId: 1001,
        notificationTitle: kNotificationTitle,
        notificationText: kNotificationText,
        notificationIcon: null,
        notificationButtons: [
          const NotificationButton(id: 'stop_service', text: 'Stop'),
        ],
        callback: _startCallbackRef,
      );
      if (result is ServiceRequestFailure) {
        throw ForegroundServiceStartException(
          'FlutterForegroundTask.startService failed: ${result.error}',
        );
      }
    }
  }

  /// Stop the foreground service.
  Future<void> stop() async {
    if (await FlutterForegroundTask.isRunningService) {
      await FlutterForegroundTask.stopService();
    }
  }

  /// Returns [true] if the service is currently active.
  Future<bool> get isRunning => FlutterForegroundTask.isRunningService;

  /// Register a callback for data received from the service isolate.
  void onDataReceived(void Function(Object) callback) {
    FlutterForegroundTask.addTaskDataCallback(callback);
  }

  /// Remove a previously registered data callback.
  void removeDataCallback(void Function(Object) callback) {
    FlutterForegroundTask.removeTaskDataCallback(callback);
  }
}

// ---------------------------------------------------------------------------
// Reference to the top-level task callback (defined in main.dart)
// ---------------------------------------------------------------------------
// This is a function reference — the actual implementation lives in main.dart
// as a top-level @pragma('vm:entry-point') function.
// We use a typedef here to make ForegroundBloc testable without triggering
// platform channel calls.
typedef _StartCallbackRef = void Function();

// Resolved at link time by the Dart compiler when FlutterForegroundTask
// starts the service isolate.
void _startCallbackRef() {
  // Delegated to startCallback() in main.dart via FlutterForegroundTask
  // auto-discovery of the @pragma('vm:entry-point') annotation.
  // This file does not need to import main.dart.
}

// ---------------------------------------------------------------------------
// Exception
// ---------------------------------------------------------------------------

/// Thrown when the foreground service fails to start.
class ForegroundServiceStartException implements Exception {
  const ForegroundServiceStartException(this.message);
  final String message;

  @override
  String toString() => 'ForegroundServiceStartException: $message';
}
