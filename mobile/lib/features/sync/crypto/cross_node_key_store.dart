// mobile/lib/features/sync/crypto/cross_node_key_store.dart
// ABM 2.0 - AES-GCM key storage for cross-node sync.
//
// Uses flutter_secure_storage for persistence and cryptography for key
// generation / hashing. No hand-rolled crypto.

import 'dart:convert';

import 'package:cryptography/cryptography.dart';
import 'package:flutter_secure_storage/flutter_secure_storage.dart';

const String kCrossNodeSyncKeyStorageKey = 'abm_cross_node_sync_aes_gcm_key';
const String kCrossNodeSyncKeyIdStorageKey = 'abm_cross_node_sync_key_id';

class CrossNodeKeyMaterial {
  const CrossNodeKeyMaterial({
    required this.secretKey,
    required this.keyId,
  });

  final SecretKey secretKey;
  final String keyId;
}

class CrossNodeKeyStore {
  CrossNodeKeyStore({
    FlutterSecureStorage? storage,
    AesGcm? algorithm,
  })  : _storage = storage ?? const FlutterSecureStorage(),
        _algorithm = algorithm ?? AesGcm.with256bits();

  final FlutterSecureStorage _storage;
  final AesGcm _algorithm;

  Future<CrossNodeKeyMaterial> ensureKey() async {
    final existingKey = await readKey();
    if (existingKey != null) {
      return existingKey;
    }

    final secretKey = await _algorithm.newSecretKey();
    final keyBytes = await secretKey.extractBytes();
    final keyId = await _deriveKeyId(keyBytes);

    await _storage.write(
      key: kCrossNodeSyncKeyStorageKey,
      value: base64Encode(keyBytes),
    );
    await _storage.write(key: kCrossNodeSyncKeyIdStorageKey, value: keyId);

    return CrossNodeKeyMaterial(
      secretKey: SecretKey(keyBytes),
      keyId: keyId,
    );
  }

  Future<CrossNodeKeyMaterial?> readKey() async {
    final encodedKey = await _storage.read(key: kCrossNodeSyncKeyStorageKey);
    final keyId = await _storage.read(key: kCrossNodeSyncKeyIdStorageKey);

    if (encodedKey == null || keyId == null) {
      return null;
    }

    return CrossNodeKeyMaterial(
      secretKey: SecretKey(base64Decode(encodedKey)),
      keyId: keyId,
    );
  }

  Future<CrossNodeKeyMaterial> rotateKey() async {
    await clearKey();
    return ensureKey();
  }

  Future<void> clearKey() async {
    await _storage.delete(key: kCrossNodeSyncKeyStorageKey);
    await _storage.delete(key: kCrossNodeSyncKeyIdStorageKey);
  }

  Future<String> _deriveKeyId(List<int> keyBytes) async {
    final digest = await Sha256().hash(keyBytes);
    return base64UrlEncode(digest.bytes.take(16).toList()).replaceAll('=', '');
  }
}
