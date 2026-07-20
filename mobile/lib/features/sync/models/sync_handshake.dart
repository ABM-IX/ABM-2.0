// mobile/lib/features/sync/models/sync_handshake.dart
// ABM 2.0 - encrypted cross-node sync handshake model.
//
// This handshake advertises protocol and key identity only. It does not perform
// a custom key exchange; the AES-GCM key is provisioned and stored through
// CrossNodeKeyStore using flutter_secure_storage.

const int kSyncProtocolVersion = 1;
const String kSyncAlgorithm = 'AES-256-GCM';
const String kSyncContentTypeJson = 'application/json';

class SyncHandshake {
  const SyncHandshake({
    required this.protocolVersion,
    required this.nodeId,
    required this.keyId,
    required this.algorithm,
    required this.createdAtEpoch,
    required this.capabilities,
  });

  final int protocolVersion;
  final String nodeId;
  final String keyId;
  final String algorithm;
  final int createdAtEpoch;
  final List<String> capabilities;

  Map<String, dynamic> toJson() => {
        'protocol_version': protocolVersion,
        'node_id': nodeId,
        'key_id': keyId,
        'algorithm': algorithm,
        'created_at_epoch': createdAtEpoch,
        'capabilities': capabilities,
      };

  factory SyncHandshake.fromJson(Map<String, dynamic> json) {
    return SyncHandshake(
      protocolVersion: json['protocol_version'] as int,
      nodeId: json['node_id'] as String,
      keyId: json['key_id'] as String,
      algorithm: json['algorithm'] as String,
      createdAtEpoch: json['created_at_epoch'] as int,
      capabilities: List<String>.from(json['capabilities'] as List),
    );
  }
}
