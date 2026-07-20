// mobile/lib/features/foreground/ui/foreground_status_widget.dart
// ABM 2.0 — Foreground Service Status Widget
//
// BlocBuilder widget that renders the current foreground service state.
// Provides start/stop controls. Zero business logic — all state management
// lives in ForegroundBloc.

import 'package:flutter/material.dart';
import 'package:flutter_bloc/flutter_bloc.dart';

import '../bloc/foreground_bloc.dart';

class ForegroundStatusWidget extends StatelessWidget {
  const ForegroundStatusWidget({super.key});

  @override
  Widget build(BuildContext context) {
    return BlocBuilder<ForegroundBloc, ForegroundState>(
      builder: (context, state) {
        return Card(
          color: const Color(0xFF161B22),
          shape: RoundedRectangleBorder(
            borderRadius: BorderRadius.circular(12),
            side: BorderSide(
              color: _borderColor(state),
              width: 1.5,
            ),
          ),
          child: Padding(
            padding: const EdgeInsets.all(20.0),
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                Row(
                  children: [
                    _StatusIndicator(state: state),
                    const SizedBox(width: 12),
                    Text(
                      'Foreground Service',
                      style: Theme.of(context).textTheme.titleMedium?.copyWith(
                            color: Colors.white,
                            fontWeight: FontWeight.w600,
                          ),
                    ),
                  ],
                ),
                const SizedBox(height: 8),
                Text(
                  _statusLabel(state),
                  style: TextStyle(
                    color: _labelColor(state),
                    fontSize: 13,
                  ),
                ),
                if (state is ForegroundError) ...[
                  const SizedBox(height: 6),
                  Text(
                    state.message,
                    style: const TextStyle(
                      color: Color(0xFFFF7B72),
                      fontSize: 12,
                    ),
                  ),
                ],
                const SizedBox(height: 16),
                Row(
                  children: [
                    _ActionButton(
                      label: 'Start',
                      icon: Icons.play_arrow_rounded,
                      color: const Color(0xFF3FB950),
                      enabled: state is! ForegroundRunning,
                      onPressed: () => context
                          .read<ForegroundBloc>()
                          .add(const StartForegroundService()),
                    ),
                    const SizedBox(width: 10),
                    _ActionButton(
                      label: 'Stop',
                      icon: Icons.stop_rounded,
                      color: const Color(0xFFFF7B72),
                      enabled: state is ForegroundRunning,
                      onPressed: () => context
                          .read<ForegroundBloc>()
                          .add(const StopForegroundService()),
                    ),
                  ],
                ),
              ],
            ),
          ),
        );
      },
    );
  }

  Color _borderColor(ForegroundState state) => switch (state) {
        ForegroundRunning() => const Color(0xFF3FB950),
        ForegroundError() => const Color(0xFFFF7B72),
        _ => const Color(0xFF30363D),
      };

  String _statusLabel(ForegroundState state) => switch (state) {
        ForegroundInitial() => 'Not started',
        ForegroundRunning() => 'Running — ambient monitoring active',
        ForegroundStopped() => 'Stopped',
        ForegroundError() => 'Error',
      };

  Color _labelColor(ForegroundState state) => switch (state) {
        ForegroundRunning() => const Color(0xFF3FB950),
        ForegroundError() => const Color(0xFFFF7B72),
        _ => const Color(0xFF8B949E),
      };
}

class _StatusIndicator extends StatelessWidget {
  const _StatusIndicator({required this.state});
  final ForegroundState state;

  @override
  Widget build(BuildContext context) {
    final color = switch (state) {
      ForegroundRunning() => const Color(0xFF3FB950),
      ForegroundError() => const Color(0xFFFF7B72),
      _ => const Color(0xFF8B949E),
    };
    return Container(
      width: 10,
      height: 10,
      decoration: BoxDecoration(
        color: color,
        shape: BoxShape.circle,
        boxShadow: state is ForegroundRunning
            ? [BoxShadow(color: color.withValues(alpha: 0.5), blurRadius: 8)]
            : null,
      ),
    );
  }
}

class _ActionButton extends StatelessWidget {
  const _ActionButton({
    required this.label,
    required this.icon,
    required this.color,
    required this.enabled,
    required this.onPressed,
  });

  final String label;
  final IconData icon;
  final Color color;
  final bool enabled;
  final VoidCallback onPressed;

  @override
  Widget build(BuildContext context) {
    return ElevatedButton.icon(
      onPressed: enabled ? onPressed : null,
      icon: Icon(icon, size: 18),
      label: Text(label),
      style: ElevatedButton.styleFrom(
        backgroundColor: enabled ? color.withValues(alpha: 0.15) : const Color(0xFF21262D),
        foregroundColor: enabled ? color : const Color(0xFF8B949E),
        side: BorderSide(color: enabled ? color : const Color(0xFF30363D)),
        shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(8)),
      ),
    );
  }
}
