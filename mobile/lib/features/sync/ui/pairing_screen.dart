// mobile/lib/features/sync/ui/pairing_screen.dart
// ABM 2.0 — Sync Pairing Screen
//
// Simple text screen displaying the base64 AES key and ID for one-time
// manual pairing with the desktop daemon.

import 'dart:convert';

import 'package:flutter/material.dart';

import '../crypto/cross_node_key_store.dart';

class PairingScreen extends StatefulWidget {
  const PairingScreen({super.key});

  @override
  State<PairingScreen> createState() => _PairingScreenState();
}

class _PairingScreenState extends State<PairingScreen> {
  final _keyStore = CrossNodeKeyStore();
  CrossNodeKeyMaterial? _keyMaterial;
  String? _base64Key;

  @override
  void initState() {
    super.initState();
    _loadKey();
  }

  Future<void> _loadKey() async {
    final material = await _keyStore.ensureKey();
    final bytes = await material.secretKey.extractBytes();
    setState(() {
      _keyMaterial = material;
      _base64Key = base64Encode(bytes);
    });
  }

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      backgroundColor: const Color(0xFF0D1117),
      appBar: AppBar(
        title: const Text('Pairing Info'),
        backgroundColor: const Color(0xFF161B22),
      ),
      body: Center(
        child: Padding(
          padding: const EdgeInsets.all(24.0),
          child: _keyMaterial == null
              ? const CircularProgressIndicator()
              : Column(
                  mainAxisSize: MainAxisSize.min,
                  crossAxisAlignment: CrossAxisAlignment.stretch,
                  children: [
                    const Text(
                      'Desktop Pairing Info',
                      style: TextStyle(
                        fontSize: 20,
                        fontWeight: FontWeight.bold,
                        color: Colors.white,
                      ),
                      textAlign: TextAlign.center,
                    ),
                    const SizedBox(height: 16),
                    const Text(
                      'Run this command on your desktop to pair this device:',
                      style: TextStyle(color: Colors.white70),
                      textAlign: TextAlign.center,
                    ),
                    const SizedBox(height: 24),
                    Container(
                      padding: const EdgeInsets.all(16),
                      decoration: BoxDecoration(
                        color: const Color(0xFF21262D),
                        borderRadius: BorderRadius.circular(8),
                        border: Border.all(color: const Color(0xFF30363D)),
                      ),
                      child: SelectableText(
                        'python -m abm.mobile.pair \\\n  --key $_base64Key \\\n  --key-id ${_keyMaterial!.keyId}',
                        style: const TextStyle(
                          fontFamily: 'monospace',
                          color: Color(0xFF58A6FF),
                          height: 1.5,
                        ),
                      ),
                    ),
                  ],
                ),
        ),
      ),
    );
  }
}
