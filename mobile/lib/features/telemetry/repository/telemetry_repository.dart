// mobile/lib/features/telemetry/repository/telemetry_repository.dart
// ABM 2.0 — Telemetry Repository
//
// Sends AmbientEventModel instances to the desktop daemon's
// ``ingestAmbientEvent`` API capability via local HTTP.
//
// Local-first by design (Architectural Constitution rule 1). No cloud endpoints.
// The desktop daemon must be reachable on the local network at the configured
// base URL.
//
// Failure handling: all methods return a TelemetryResult rather than throwing
// (Constitution rule 9 — degrade gracefully).

import 'dart:async';
import 'dart:convert';
import 'package:http/http.dart' as http;

import '../models/ambient_event_model.dart';

// ---------------------------------------------------------------------------
// Constants
// ---------------------------------------------------------------------------

/// Default base URL for the ABM desktop daemon API.
/// Adjust this to the local network address of the machine running the daemon.
const String kDefaultDaemonBaseUrl = 'http://127.0.0.1:8765';

/// HTTP endpoint for ambient event ingestion.
const String kIngestEndpoint = '/api/ingest_ambient_event';

/// Request timeout for API calls.
const Duration kRequestTimeout = Duration(seconds: 10);

// ---------------------------------------------------------------------------
// TelemetryResult
// ---------------------------------------------------------------------------

/// Result of a telemetry ingestion attempt.
class TelemetryResult {
  const TelemetryResult({
    required this.success,
    this.docId,
    this.status,
    this.error,
  });

  final bool success;

  /// ChromaDB document ID written (null on failure).
  final String? docId;

  /// Status string from the API response ('ok', 'compressed', 'error', etc.).
  final String? status;

  /// Error description on failure.
  final String? error;

  @override
  String toString() => success
      ? 'TelemetryResult(ok, docId=$docId, status=$status)'
      : 'TelemetryResult(failed, error=$error)';
}

// ---------------------------------------------------------------------------
// TelemetryRepository
// ---------------------------------------------------------------------------

/// Sends [AmbientEventModel] instances to the ABM desktop daemon.
///
/// All methods are async and never throw — failures are returned as
/// [TelemetryResult.success == false].
class TelemetryRepository {
  TelemetryRepository({
    required this.baseUrl,
    http.Client? httpClient,
  }) : _client = httpClient ?? http.Client();

  /// The base URL of the ABM desktop daemon.
  final String baseUrl;

  final http.Client _client;

  /// Construct with the default daemon URL (127.0.0.1:8765).
  factory TelemetryRepository.defaultInstance() =>
      TelemetryRepository(baseUrl: kDefaultDaemonBaseUrl);

  // ------------------------------------------------------------------
  // Public API
  // ------------------------------------------------------------------

  /// Send [event] to the desktop daemon's ``ingestAmbientEvent`` endpoint.
  ///
  /// Returns [TelemetryResult.success == true] if the daemon accepted the event
  /// (HTTP 200 with status 'ok' or 'compressed').  Never throws.
  Future<TelemetryResult> sendEvent(AmbientEventModel event) async {
    final uri = Uri.parse('$baseUrl$kIngestEndpoint');
    try {
      final response = await _client
          .post(
            uri,
            headers: {'Content-Type': 'application/json'},
            body: jsonEncode(event.toJson()),
          )
          .timeout(kRequestTimeout);

      if (response.statusCode == 200) {
        final body = jsonDecode(response.body) as Map<String, dynamic>;
        final status = body['status'] as String? ?? 'unknown';
        return TelemetryResult(
          success: status == 'ok' || status == 'compressed',
          docId: body['doc_id'] as String?,
          status: status,
          error: status == 'error' ? body['reason'] as String? : null,
        );
      } else {
        return TelemetryResult(
          success: false,
          error:
              'Daemon returned HTTP ${response.statusCode}: ${response.body}',
        );
      }
    } on TimeoutException {
      return const TelemetryResult(
        success: false,
        error: 'Request to daemon timed out.',
      );
    } catch (e) {
      return TelemetryResult(
        success: false,
        error: 'HTTP error: $e',
      );
    }
  }

  /// Send multiple events sequentially. Returns one result per event.
  Future<List<TelemetryResult>> sendBatch(
    List<AmbientEventModel> events,
  ) async {
    final results = <TelemetryResult>[];
    for (final event in events) {
      results.add(await sendEvent(event));
    }
    return results;
  }

  /// Release underlying HTTP client resources.
  void dispose() => _client.close();
}
