// mobile/test/features/sync/repository/cross_node_sync_repository_test.dart
import 'package:flutter_test/flutter_test.dart';
import 'package:mocktail/mocktail.dart';
import 'package:http/http.dart' as http;
import 'package:abm_mobile/features/sync/repository/cross_node_sync_repository.dart';
import 'package:abm_mobile/features/sync/crypto/sync_crypto_channel.dart';
import 'package:abm_mobile/features/sync/models/sync_handshake.dart';

class MockHttpClient extends Mock implements http.Client {}
class MockSyncCryptoChannel extends Mock implements SyncCryptoChannel {}

void main() {
  setUpAll(() {
    registerFallbackValue(Uri.parse('http://localhost'));
  });

  test('CrossNodeSyncRepository uses the provided baseUrl, not a hardcoded constant', () async {
    final mockClient = MockHttpClient();
    final mockChannel = MockSyncCryptoChannel();
    const customUrl = 'http://172.24.56.26:8765';
    
    final repo = CrossNodeSyncRepository(
      baseUrl: customUrl,
      channel: mockChannel,
      httpClient: mockClient,
    );
    
    when(() => mockChannel.buildHandshake()).thenAnswer(
      (_) async => const SyncHandshake(
        protocolVersion: 1,
        nodeId: 'test_node',
        keyId: 'test_key',
        algorithm: 'AES-256-GCM',
        createdAtEpoch: 1234567890,
        capabilities: [],
      ),
    );

    when(() => mockClient.post(
      any(),
      headers: any(named: 'headers'),
      body: any(named: 'body'),
    )).thenAnswer((_) async => http.Response('{"status": "ok"}', 200));

    await repo.sendHandshake();

    // Verify the URL actually requested was constructed using customUrl
    final captured = verify(() => mockClient.post(
      captureAny(),
      headers: any(named: 'headers'),
      body: any(named: 'body'),
    )).captured;

    final requestedUri = captured.first as Uri;
    expect(requestedUri.toString(), startsWith(customUrl));
    expect(requestedUri.toString(), equals('$customUrl$kSyncHandshakeEndpoint'));
  });
}
