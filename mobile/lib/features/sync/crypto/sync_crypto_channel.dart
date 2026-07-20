// mobile/lib/features/sync/crypto/sync_crypto_channel.dart
// ABM 2.0 - encrypted cross-node sync channel.
//
// AES-GCM encryption is delegated to package:cryptography. This file only
// orchestrates vetted primitives and wire-format models.

import 'dart:convert';

import 'package:cryptography/cryptography.dart';

import '../models/encrypted_sync_payload.dart';
import '../models/sync_handshake.dart';
import 'cross_node_key_store.dart';

const List<String> kSyncCapabilities = <String>[
  'ambient_event_ingest',
  'state_snapshot',
  'encrypted_payload_v1',
];

class SyncCryptoChannel {
  SyncCryptoChannel({
    required CrossNodeKeyStore keyStore,
    required this.nodeId,
    AesGcm? algorithm,
  })  : _keyStore = keyStore,
        _algorithm = algorithm ?? AesGcm.with256bits();

  final CrossNodeKeyStore _keyStore;
  final String nodeId;
  final AesGcm _algorithm;

  Future<SyncHandshake> buildHandshake({int? createdAtEpoch}) async {
    final keyMaterial = await _keyStore.ensureKey();
    return SyncHandshake(
      protocolVersion: kSyncProtocolVersion,
      nodeId: nodeId,
      keyId: keyMaterial.keyId,
      algorithm: kSyncAlgorithm,
      createdAtEpoch: createdAtEpoch ?? _nowEpoch(),
      capabilities: kSyncCapabilities,
    );
  }

  Future<EncryptedSyncPayload> encryptJson(
    Map<String, dynamic> json, {
    int? createdAtEpoch,
    String contentType = kSyncContentTypeJson,
  }) async {
    final keyMaterial = await _keyStore.ensureKey();
    final epoch = createdAtEpoch ?? _nowEpoch();
    final plainText = utf8.encode(jsonEncode(json));
    final nonce = _algorithm.newNonce();
    final aad = _associatedData(
      protocolVersion: kSyncProtocolVersion,
      keyId: keyMaterial.keyId,
      nodeId: nodeId,
      createdAtEpoch: epoch,
      contentType: contentType,
    );

    final box = await _algorithm.encrypt(
      plainText,
      secretKey: keyMaterial.secretKey,
      nonce: nonce,
      aad: aad,
    );

    return EncryptedSyncPayload(
      protocolVersion: kSyncProtocolVersion,
      keyId: keyMaterial.keyId,
      algorithm: kSyncAlgorithm,
      nodeId: nodeId,
      createdAtEpoch: epoch,
      contentType: contentType,
      nonce: base64Encode(box.nonce),
      ciphertext: base64Encode(box.cipherText),
      mac: base64Encode(box.mac.bytes),
    );
  }

  Future<Map<String, dynamic>> decryptJson(EncryptedSyncPayload payload) async {
    if (payload.protocolVersion != kSyncProtocolVersion) {
      throw ArgumentError(
        'Unsupported sync protocol version: ${payload.protocolVersion}',
      );
    }
    if (payload.algorithm != kSyncAlgorithm) {
      throw ArgumentError('Unsupported sync algorithm: ${payload.algorithm}');
    }

    final keyMaterial = await _keyStore.ensureKey();
    if (payload.keyId != keyMaterial.keyId) {
      throw ArgumentError('Encrypted payload key_id does not match local key.');
    }

    final aad = _associatedData(
      protocolVersion: payload.protocolVersion,
      keyId: payload.keyId,
      nodeId: payload.nodeId,
      createdAtEpoch: payload.createdAtEpoch,
      contentType: payload.contentType,
    );

    final plainText = await _algorithm.decrypt(
      SecretBox(
        base64Decode(payload.ciphertext),
        nonce: base64Decode(payload.nonce),
        mac: Mac(base64Decode(payload.mac)),
      ),
      secretKey: keyMaterial.secretKey,
      aad: aad,
    );

    return jsonDecode(utf8.decode(plainText)) as Map<String, dynamic>;
  }

  List<int> _associatedData({
    required int protocolVersion,
    required String keyId,
    required String nodeId,
    required int createdAtEpoch,
    required String contentType,
  }) {
    return utf8.encode(
      [
        'abm-sync',
        protocolVersion.toString(),
        keyId,
        nodeId,
        createdAtEpoch.toString(),
        contentType,
      ].join('|'),
    );
  }

  int _nowEpoch() => DateTime.now().millisecondsSinceEpoch ~/ 1000;
}
