import 'package:flutter/material.dart';

import '../../core/theme/app_theme.dart';

class SeverityBadge extends StatelessWidget {
  final String severity;
  final bool compact;

  const SeverityBadge({
    super.key,
    required this.severity,
    this.compact = false,
  });

  @override
  Widget build(BuildContext context) {
    final color = severity.severityColor;
    final label = _label(severity);
    final emoji = _emoji(severity);

    return Container(
      padding: EdgeInsets.symmetric(
        horizontal: compact ? 8 : 10,
        vertical:   compact ? 3 : 5,
      ),
      decoration: BoxDecoration(
        color:        color.withOpacity(0.15),
        borderRadius: BorderRadius.circular(20),
        border:       Border.all(color: color.withOpacity(0.4)),
      ),
      child: Row(
        mainAxisSize: MainAxisSize.min,
        children: [
          Text(emoji, style: TextStyle(fontSize: compact ? 10 : 12)),
          const SizedBox(width: 4),
          Text(
            label,
            style: TextStyle(
              color:      color,
              fontSize:   compact ? 10 : 12,
              fontWeight: FontWeight.w700,
              letterSpacing: 0.3,
            ),
          ),
        ],
      ),
    );
  }

  String _label(String s) => switch (s.toLowerCase()) {
        'critical' => 'CRITICAL',
        'high'     => 'HIGH',
        'medium'   => 'MEDIUM',
        'low'      => 'LOW',
        _          => s.toUpperCase(),
      };

  String _emoji(String s) => switch (s.toLowerCase()) {
        'critical' => '🔴',
        'high'     => '🟠',
        'medium'   => '🟡',
        'low'      => '🟢',
        _          => '⚪',
      };
}