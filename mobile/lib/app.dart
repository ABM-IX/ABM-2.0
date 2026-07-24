// mobile/lib/app.dart
// ABM 2.0 — Phase v1.0 Flutter Mobile Node
//
// Root application widget. Provides all BLoC instances at the top of the
// widget tree via MultiBlocProvider. Architectural Constitution rule 6:
// BLoC for all state management.

import 'package:flutter/material.dart';
import 'package:flutter_bloc/flutter_bloc.dart';

import 'features/foreground/bloc/foreground_bloc.dart';
import 'features/foreground/service/abm_foreground_service.dart';
import 'features/foreground/ui/foreground_status_widget.dart';
import 'features/telemetry/bloc/telemetry_bloc.dart';
import 'features/sync/repository/cross_node_sync_repository.dart';
import 'features/sync/ui/sync_settings_screen.dart';

class AbmMobileApp extends StatelessWidget {
  const AbmMobileApp({super.key, required this.syncRepository});

  final CrossNodeSyncRepository syncRepository;

  @override
  Widget build(BuildContext context) {
    return MultiBlocProvider(
      providers: [
        BlocProvider<ForegroundBloc>(
          create: (_) => ForegroundBloc(service: AbmForegroundService.instance),
        ),
        BlocProvider<TelemetryBloc>(
          create: (_) => TelemetryBloc(
            repository: syncRepository,
          ),
        ),
      ],
      child: MaterialApp(
        title: 'ABM 2.0 — Cognitive OS',
        debugShowCheckedModeBanner: false,
        theme: ThemeData(
          colorScheme: ColorScheme.fromSeed(
            seedColor: const Color(0xFF1A1F36),
            brightness: Brightness.dark,
          ),
          useMaterial3: true,
        ),
        home: const _AbmHome(),
      ),
    );
  }
}

class _AbmHome extends StatelessWidget {
  const _AbmHome();

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      backgroundColor: const Color(0xFF0D1117),
      appBar: AppBar(
        backgroundColor: const Color(0xFF161B22),
        title: const Text(
          'ABM 2.0 — Cognitive OS',
          style: TextStyle(
            color: Color(0xFF58A6FF),
            fontWeight: FontWeight.w600,
            letterSpacing: 0.5,
          ),
        ),
        centerTitle: true,
        actions: [
          IconButton(
            icon: const Icon(Icons.settings),
            onPressed: () {
              Navigator.push(
                context,
                MaterialPageRoute(
                  builder: (context) => const SyncSettingsScreen(),
                ),
              );
            },
          ),
        ],
      ),
      body: SafeArea(
        child: Padding(
          padding: const EdgeInsets.all(16.0),
          child: Column(
            crossAxisAlignment: CrossAxisAlignment.stretch,
            children: [
              const ForegroundStatusWidget(),
              const SizedBox(height: 16),
              ElevatedButton(
                onPressed: () {
                  context.read<TelemetryBloc>().add(
                        ObserveWorkspaceFile(
                          repository: 'test_repo',
                          filePath: 'test/path.dart',
                          epochTimestamp: DateTime.now().millisecondsSinceEpoch ~/ 1000,
                        ),
                      );
                },
                child: const Text('Sync Now (Test)'),
              ),
            ],
          ),
        ),
      ),
    );
  }
}
