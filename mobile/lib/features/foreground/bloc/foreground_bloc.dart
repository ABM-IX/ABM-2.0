// mobile/lib/features/foreground/bloc/foreground_bloc.dart
// ABM 2.0 — Foreground Service BLoC
//
// Manages the lifecycle of the ABM Android Foreground Service.
// BLoC pattern per PROJECT_BRIEF.md ground rule 6.
//
// State transitions:
//   ForegroundInitial
//     ─StartForegroundService──► ForegroundRunning
//     ─StartForegroundService──► ForegroundError (if start fails)
//   ForegroundRunning
//     ─StopForegroundService───► ForegroundStopped
//     ─StopForegroundService───► ForegroundError (if stop fails)
//   ForegroundStopped
//     ─StartForegroundService──► ForegroundRunning

import 'package:bloc/bloc.dart';
import 'package:equatable/equatable.dart';

import '../service/abm_foreground_service.dart';

part 'foreground_event.dart';
part 'foreground_state.dart';

class ForegroundBloc extends Bloc<ForegroundEvent, ForegroundState> {
  ForegroundBloc({required AbmForegroundService service})
      : _service = service,
        super(const ForegroundInitial()) {
    on<StartForegroundService>(_onStart);
    on<StopForegroundService>(_onStop);
    on<ForegroundServiceStatusUpdated>(_onStatusUpdated);
  }

  final AbmForegroundService _service;

  Future<void> _onStart(
    StartForegroundService event,
    Emitter<ForegroundState> emit,
  ) async {
    try {
      await _service.start();
      emit(const ForegroundRunning());
    } catch (e) {
      emit(ForegroundError(message: 'Failed to start foreground service: $e'));
    }
  }

  Future<void> _onStop(
    StopForegroundService event,
    Emitter<ForegroundState> emit,
  ) async {
    try {
      await _service.stop();
      emit(const ForegroundStopped());
    } catch (e) {
      emit(ForegroundError(message: 'Failed to stop foreground service: $e'));
    }
  }

  void _onStatusUpdated(
    ForegroundServiceStatusUpdated event,
    Emitter<ForegroundState> emit,
  ) {
    if (event.isRunning) {
      emit(const ForegroundRunning());
    } else {
      emit(const ForegroundStopped());
    }
  }
}
