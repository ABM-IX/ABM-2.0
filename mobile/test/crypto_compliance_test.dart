import 'dart:io';
import 'package:flutter_test/flutter_test.dart';

void main() {
  test('No plaintext telemetry routes or unencrypted ingest paths exist in lib', () {
    final libDir = Directory('lib');
    expect(libDir.existsSync(), isTrue, reason: 'Test must be run from the mobile/ directory');

    final dartFiles = libDir
        .listSync(recursive: true)
        .whereType<File>()
        .where((file) => file.path.endsWith('.dart'));

    for (final file in dartFiles) {
      final content = file.readAsStringSync();
      
      expect(
        content.contains('/api/ingest_ambient_event'),
        isFalse,
        reason: 'Found unencrypted /api/ingest_ambient_event in ${file.path}. '
            'Rule 7 mandates all telemetry must route through the encrypted CrossNodeSyncRepository.',
      );

      expect(
        content.contains('telemetry_repository.dart'),
        isFalse,
        reason: 'Found reference to plaintext telemetry_repository.dart in ${file.path}',
      );
    }
  });
}
