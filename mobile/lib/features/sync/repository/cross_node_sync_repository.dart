// mobile/lib/features/sync/repository/cross_node_sync_repository.dart
// ABM 2.0 - encrypted cross-node sync repository.
//
// Sends SyncHandshake and EncryptedSyncPayload objects to the desktop daemon.
// Failures are returned as SyncSendResult instead of thrown.

import 'dart:async';
import 'dart:convert';

import 'package:http/http.dart' as http;

import '../crypto/sync_crypto_channel.dart';
import '../models/encrypted_sync_payload.dart';


const String kSyncHandshakeEndpoint = '/api/sync/handshake';
const String kSyncPayloadEndpoint = '/api/sync/payload';
const Duration kSyncRequestTimeout = Duration(seconds: 10);

class SyncSendResult {
  const SyncSendResult({
    required this.success,
    this.status,
    this.error,
  });

  final bool success;
  final String? status;
  final String? error;
}

class CrossNodeSyncRepository {
  CrossNodeSyncRepository({
    required this.baseUrl,
    required SyncCryptoChannel channel,
    http.Client? httpClient,
  })  : _channel = channel,
        _client = httpClient ?? http.Client();

  final String baseUrl;
  final SyncCryptoChannel _channel;
  final http.Client _client;

  Future<SyncSendResult> sendHandshake() async {
    try {
      final handshake = await _channel.buildHandshake();
      final response = await _postJson(
        endpoint: kSyncHandshakeEndpoint,
        body: handshake.toJson(),
      );
      return _resultFromResponse(response);
    } on TimeoutException {
      return const SyncSendResult(
        success: false,
        error: 'Sync handshake timed out.',
      );
    } catch (e) {
      return SyncSendResult(success: false, error: 'Sync handshake error: $e');
    }
  }

  Future<SyncSendResult> sendEncryptedJson(Map<String, dynamic> json) async {
    try {
      final payload = await _channel.encryptJson(json);
      final response = await _postJson(
        endpoint: kSyncPayloadEndpoint,
        body: payload.toJson(),
      );
      return _resultFromResponse(response);
    } on TimeoutException {
      return const SyncSendResult(
        success: false,
        error: 'Encrypted sync payload timed out.',
      );
    } catch (e) {
      return SyncSendResult(success: false, error: 'Encrypted sync error: $e');
    }
  }

  Future<Map<String, dynamic>> decryptPayload(
    EncryptedSyncPayload payload,
  ) {
    return _channel.decryptJson(payload);
  }

  Future<http.Response> _postJson({
    required String endpoint,
    required Map<String, dynamic> body,
  }) {
    final uri = Uri.parse('$baseUrl$endpoint');
    return _client
        .post(
          uri,
          headers: {'Content-Type': 'application/json'},
          body: jsonEncode(body),
        )
        .timeout(kSyncRequestTimeout);
  }

  SyncSendResult _resultFromResponse(http.Response response) {
    if (response.statusCode != 200) {
      return SyncSendResult(
        success: false,
        error: 'Daemon returned HTTP ${response.statusCode}: ${response.body}',
      );
    }

    final body = jsonDecode(response.body) as Map<String, dynamic>;
    final status = body['status'] as String? ?? 'unknown';
    return SyncSendResult(
      success: status == 'ok' || status == 'accepted',
      status: status,
      error: status == 'error' ? body['reason'] as String? : null,
    );
  }

  void dispose() => _client.close();
}
