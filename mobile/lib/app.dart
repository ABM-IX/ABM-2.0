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
import 'features/telemetry/repository/telemetry_repository.dart';

class AbmMobileApp extends StatelessWidget {
  const AbmMobileApp({super.key});

  @override
  Widget build(BuildContext context) {
    return MultiBlocProvider(
      providers: [
        BlocProvider<ForegroundBloc>(
          create: (_) => ForegroundBloc(service: AbmForegroundService.instance),
        ),
        BlocProvider<TelemetryBloc>(
          create: (_) => TelemetryBloc(
            repository: TelemetryRepository.defaultInstance(),
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
      ),
      body: const SafeArea(
        child: Padding(
          padding: EdgeInsets.all(16.0),
          child: Column(
            crossAxisAlignment: CrossAxisAlignment.stretch,
            children: [
              ForegroundStatusWidget(),
            ],
          ),
        ),
      ),
    );
  }
}
