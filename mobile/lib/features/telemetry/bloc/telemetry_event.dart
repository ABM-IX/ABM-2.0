// mobile/lib/features/telemetry/bloc/telemetry_event.dart
part of 'telemetry_bloc.dart';

/// Base class for all telemetry BLoC events.
sealed class TelemetryEvent extends Equatable {
  const TelemetryEvent();

  @override
  List<Object?> get props => [];
}

/// Observe a workspace file change — emits a workspace_file event.
final class ObserveWorkspaceFile extends TelemetryEvent {
  const ObserveWorkspaceFile({
    required this.filePath,
    required this.repository,
    required this.epochTimestamp,
  });

  final String filePath;
  final String repository;
  final int epochTimestamp;

  @override
  List<Object?> get props => [filePath, repository, epochTimestamp];
}

/// Record a Git commit event — emits a git_commit event.
final class RecordGitActivity extends TelemetryEvent {
  const RecordGitActivity({
    required this.commitSha,
    required this.message,
    required this.repository,
    required this.epochTimestamp,
  });

  final String commitSha;
  final String message;
  final String repository;
  final int epochTimestamp;

  @override
  List<Object?> get props => [commitSha, repository, epochTimestamp];
}

/// Observe a design document — emits a design_doc event.
final class ObserveDesignDoc extends TelemetryEvent {
  const ObserveDesignDoc({
    required this.docPath,
    required this.docPreview,
    required this.repository,
    required this.epochTimestamp,
  });

  final String docPath;
  final String docPreview;
  final String repository;
  final int epochTimestamp;

  @override
  List<Object?> get props => [docPath, repository, epochTimestamp];
}
