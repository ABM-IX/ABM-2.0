// mobile/lib/features/telemetry/bloc/telemetry_bloc.dart
// ABM 2.0 — Telemetry BLoC
//
// Manages ambient telemetry event dispatch from the Flutter mobile node
// to the ABM desktop daemon. Converts typed BLoC events into
// AmbientEventModel instances and delegates to TelemetryRepository.
//
// Source kinds enforced here at the Dart type level — no event type
// exists for clipboard, voice, or browser (Phase v1.0 scope guardrail).

import 'package:bloc/bloc.dart';
import 'package:equatable/equatable.dart';

import '../models/ambient_event_model.dart';
import '../../sync/repository/cross_node_sync_repository.dart';

part 'telemetry_event.dart';
part 'telemetry_state.dart';

class TelemetryBloc extends Bloc<TelemetryEvent, TelemetryState> {
  TelemetryBloc({required CrossNodeSyncRepository repository})
      : _repository = repository,
        super(const TelemetryIdle()) {
    on<ObserveWorkspaceFile>(_onWorkspaceFile);
    on<RecordGitActivity>(_onGitActivity);
    on<ObserveDesignDoc>(_onDesignDoc);
  }

  final CrossNodeSyncRepository _repository;

  Future<void> _onWorkspaceFile(
    ObserveWorkspaceFile event,
    Emitter<TelemetryState> emit,
  ) async {
    emit(const TelemetrySending(sourceKind: 'workspace_file'));
    final model = AmbientEventModel(
      sourceKind: AmbientSourceKind.workspaceFile,
      activeRepository: event.repository,
      sourcePath: event.filePath,
      text:
          'workspace file change: ${event.filePath}\nrepo=${event.repository}',
      epochTimestamp: event.epochTimestamp,
    );
    final result = await _repository.sendEncryptedJson(model.toJson());
    if (result.success) {
      emit(TelemetrySent(
        docId: '',
        status: result.status ?? 'ok',
        sourceKind: 'workspace_file',
      ));
    } else {
      emit(TelemetryFailed(
        error: result.error ?? 'Unknown error',
        sourceKind: 'workspace_file',
      ));
    }
  }

  Future<void> _onGitActivity(
    RecordGitActivity event,
    Emitter<TelemetryState> emit,
  ) async {
    emit(const TelemetrySending(sourceKind: 'git_commit'));
    final model = AmbientEventModel(
      sourceKind: AmbientSourceKind.gitCommit,
      activeRepository: event.repository,
      sourcePath: event.commitSha,
      text:
          'git commit ${event.commitSha.substring(0, 8)}: ${event.message}\n'
          'repo=${event.repository}',
      epochTimestamp: event.epochTimestamp,
    );
    final result = await _repository.sendEncryptedJson(model.toJson());
    if (result.success) {
      emit(TelemetrySent(
        docId: '',
        status: result.status ?? 'ok',
        sourceKind: 'git_commit',
      ));
    } else {
      emit(TelemetryFailed(
        error: result.error ?? 'Unknown error',
        sourceKind: 'git_commit',
      ));
    }
  }

  Future<void> _onDesignDoc(
    ObserveDesignDoc event,
    Emitter<TelemetryState> emit,
  ) async {
    emit(const TelemetrySending(sourceKind: 'design_doc'));
    final model = AmbientEventModel(
      sourceKind: AmbientSourceKind.designDoc,
      activeRepository: event.repository,
      sourcePath: event.docPath,
      text: 'design doc: ${event.docPath}\n\n${event.docPreview}',
      epochTimestamp: event.epochTimestamp,
    );
    final result = await _repository.sendEncryptedJson(model.toJson());
    if (result.success) {
      emit(TelemetrySent(
        docId: '',
        status: result.status ?? 'ok',
        sourceKind: 'design_doc',
      ));
    } else {
      emit(TelemetryFailed(
        error: result.error ?? 'Unknown error',
        sourceKind: 'design_doc',
      ));
    }
  }

  @override
  Future<void> close() {
    return super.close();
  }
}
