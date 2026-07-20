// mobile/lib/features/telemetry/models/ambient_event_model.dart
// ABM 2.0 — Dart model mirroring the Python AmbientEvent schema.
//
// This model is serialised to JSON when the Flutter foreground service
// calls the desktop API's ``ingestAmbientEvent`` capability.
// Field names match the Python AmbientEvent dataclass exactly to avoid
// any serialisation mismatch.

/// Permitted source kinds for Phase v1.0.
/// Mirrors Python ``PERMITTED_SOURCE_KINDS``.
enum AmbientSourceKind {
  gitCommit('git_commit'),
  workspaceFile('workspace_file'),
  designDoc('design_doc');

  const AmbientSourceKind(this.value);

  /// Wire value used in JSON serialisation.
  final String value;
}

/// Dart representation of an ambient interaction event.
///
/// Constructed by the foreground service task handler and sent to the
/// desktop daemon via [TelemetryRepository].
class AmbientEventModel {
  const AmbientEventModel({
    required this.sourceKind,
    required this.activeRepository,
    required this.sourcePath,
    required this.text,
    required this.epochTimestamp,
    this.deviceSource = 'dynamic_mobile_node',
  });

  final AmbientSourceKind sourceKind;
  final String activeRepository;
  final String sourcePath;
  final String text;
  final int epochTimestamp;

  /// Always ``"dynamic_mobile_node"`` — spec section 10 addendum.
  final String deviceSource;

  /// Serialise to the JSON shape expected by the Python API.
  Map<String, dynamic> toJson() => {
        'source_kind': sourceKind.value,
        'active_repository': activeRepository,
        'source_path': sourcePath,
        'text': text,
        'epoch_timestamp': epochTimestamp,
        'device_source': deviceSource,
      };

  factory AmbientEventModel.fromJson(Map<String, dynamic> json) {
    final kindStr = json['source_kind'] as String;
    final kind = AmbientSourceKind.values.firstWhere(
      (k) => k.value == kindStr,
      orElse: () => throw ArgumentError('Unknown source_kind: $kindStr'),
    );
    return AmbientEventModel(
      sourceKind: kind,
      activeRepository: json['active_repository'] as String,
      sourcePath: json['source_path'] as String,
      text: json['text'] as String,
      epochTimestamp: json['epoch_timestamp'] as int,
      deviceSource: json['device_source'] as String? ?? 'dynamic_mobile_node',
    );
  }

  @override
  String toString() =>
      'AmbientEventModel(kind=${sourceKind.value}, repo=$activeRepository, '
      'ts=$epochTimestamp)';
}
