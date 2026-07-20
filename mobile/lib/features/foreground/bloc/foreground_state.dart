// mobile/lib/features/foreground/bloc/foreground_state.dart
// ABM 2.0 — Foreground Service BLoC States

part of 'foreground_bloc.dart';

/// Base class for all foreground service states.
sealed class ForegroundState extends Equatable {
  const ForegroundState();

  @override
  List<Object?> get props => [];
}

/// Service has not yet been started or checked.
final class ForegroundInitial extends ForegroundState {
  const ForegroundInitial();
}

/// Service is actively running (persistent notification visible).
final class ForegroundRunning extends ForegroundState {
  const ForegroundRunning();
}

/// Service has been explicitly stopped.
final class ForegroundStopped extends ForegroundState {
  const ForegroundStopped();
}

/// Service encountered an error during start or stop.
final class ForegroundError extends ForegroundState {
  const ForegroundError({required this.message});

  final String message;

  @override
  List<Object?> get props => [message];
}
