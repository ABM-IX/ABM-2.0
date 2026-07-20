// mobile/lib/features/sync/models/encrypted_sync_payload.dart
// ABM 2.0 - encrypted cross-node sync payload model.

import 'sync_handshake.dart';

class EncryptedSyncPayload {
  const EncryptedSyncPayload({
    required this.protocolVersion,
    required this.keyId,
    required this.algorithm,
    required this.nodeId,
    required this.createdAtEpoch,
    required this.contentType,
    required this.nonce,
    required this.ciphertext,
    required this.mac,
  });

  final int protocolVersion;
  final String keyId;
  final String algorithm;
  final String nodeId;
  final int createdAtEpoch;
  final String contentType;

  /// Base64 encoded AES-GCM nonce.
  final String nonce;

  /// Base64 encoded ciphertext.
  final String ciphertext;

  /// Base64 encoded AES-GCM authentication tag.
  final String mac;

  Map<String, dynamic> toJson() => {
        'protocol_version': protocolVersion,
        'key_id': keyId,
        'algorithm': algorithm,
        'node_id': nodeId,
        'created_at_epoch': createdAtEpoch,
        'content_type': contentType,
        'nonce': nonce,
        'ciphertext': ciphertext,
        'mac': mac,
      };

  factory EncryptedSyncPayload.fromJson(Map<String, dynamic> json) {
    return EncryptedSyncPayload(
      protocolVersion: json['protocol_version'] as int,
      keyId: json['key_id'] as String,
      algorithm: json['algorithm'] as String? ?? kSyncAlgorithm,
      nodeId: json['node_id'] as String,
      createdAtEpoch: json['created_at_epoch'] as int,
      contentType: json['content_type'] as String? ?? kSyncContentTypeJson,
      nonce: json['nonce'] as String,
      ciphertext: json['ciphertext'] as String,
      mac: json['mac'] as String,
    );
  }
}
