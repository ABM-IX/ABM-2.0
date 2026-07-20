// mobile/lib/features/telemetry/bloc/telemetry_state.dart
part of 'telemetry_bloc.dart';

/// Base class for all telemetry BLoC states.
sealed class TelemetryState extends Equatable {
  const TelemetryState();

  @override
  List<Object?> get props => [];
}

/// No event has been sent yet.
final class TelemetryIdle extends TelemetryState {
  const TelemetryIdle();
}

/// An event is being sent to the desktop daemon.
final class TelemetrySending extends TelemetryState {
  const TelemetrySending({required this.sourceKind});
  final String sourceKind;

  @override
  List<Object?> get props => [sourceKind];
}

/// Event was successfully written or deduplicated.
final class TelemetrySent extends TelemetryState {
  const TelemetrySent({
    required this.docId,
    required this.status,
    required this.sourceKind,
  });

  final String docId;
  final String status;   // 'ok' | 'compressed'
  final String sourceKind;

  @override
  List<Object?> get props => [docId, status, sourceKind];
}

/// Event failed to reach the daemon.
final class TelemetryFailed extends TelemetryState {
  const TelemetryFailed({required this.error, required this.sourceKind});

  final String error;
  final String sourceKind;

  @override
  List<Object?> get props => [error, sourceKind];
}
