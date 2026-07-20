// mobile/lib/features/foreground/bloc/foreground_event.dart
// ABM 2.0 — Foreground Service BLoC Events

part of 'foreground_bloc.dart';

/// Base class for all foreground service events.
sealed class ForegroundEvent extends Equatable {
  const ForegroundEvent();

  @override
  List<Object?> get props => [];
}

/// Request to start the ABM Android Foreground Service.
final class StartForegroundService extends ForegroundEvent {
  const StartForegroundService();
}

/// Request to stop the ABM Android Foreground Service.
final class StopForegroundService extends ForegroundEvent {
  const StopForegroundService();
}

/// Internal event: foreground service reported a status update.
final class ForegroundServiceStatusUpdated extends ForegroundEvent {
  const ForegroundServiceStatusUpdated({required this.isRunning});

  final bool isRunning;

  @override
  List<Object?> get props => [isRunning];
}
