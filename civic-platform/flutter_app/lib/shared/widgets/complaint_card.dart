import 'package:flutter/material.dart';

import '../../core/theme/app_theme.dart';
import '../../features/complaint/data/models/complaint_model.dart';
import 'severity_badge.dart';

class ComplaintCard extends StatelessWidget {
  final ComplaintModel complaint;
  final VoidCallback? onTap;

  const ComplaintCard({
    super.key,
    required this.complaint,
    this.onTap,
  });

  @override
  Widget build(BuildContext context) {
    final c = complaint;
    return Card(
      child: InkWell(
        onTap:        onTap,
        borderRadius: BorderRadius.circular(16),
        child: Padding(
          padding: const EdgeInsets.all(16),
          child: Column(
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              // ── Top row: category chip + severity badge ────────────────
              Row(
                children: [
                  // Category chip
                  Container(
                    padding: const EdgeInsets.symmetric(horizontal: 10, vertical: 4),
                    decoration: BoxDecoration(
                      color:        c.category.categoryColor.withOpacity(0.12),
                      borderRadius: BorderRadius.circular(8),
                    ),
                    child: Row(
                      mainAxisSize: MainAxisSize.min,
                      children: [
                        Text(
                          c.category.categoryEmoji,
                          style: const TextStyle(fontSize: 12),
                        ),
                        const SizedBox(width: 5),
                        Text(
                          c.category.displayCategory,
                          style: TextStyle(
                            fontSize:   11,
                            fontWeight: FontWeight.w600,
                            color:      c.category.categoryColor,
                          ),
                        ),
                      ],
                    ),
                  ),
                  const Spacer(),
                  SeverityBadge(severity: c.severity, compact: true),
                ],
              ),
              const SizedBox(height: 10),

              // ── Title ──────────────────────────────────────────────────
              Text(
                c.title,
                style: Theme.of(context).textTheme.titleMedium,
                maxLines:  2,
                overflow:  TextOverflow.ellipsis,
              ),
              const SizedBox(height: 6),

              // ── Address ────────────────────────────────────────────────
              if (c.address != null && c.address!.isNotEmpty)
                Row(
                  children: [
                    const Icon(
                      Icons.location_on_rounded,
                      size:  13,
                      color: AppColors.onSurfaceVar,
                    ),
                    const SizedBox(width: 4),
                    Expanded(
                      child: Text(
                        c.address!,
                        style: const TextStyle(
                          fontSize: 12,
                          color:    AppColors.onSurfaceVar,
                        ),
                        maxLines: 1,
                        overflow: TextOverflow.ellipsis,
                      ),
                    ),
                  ],
                ),
              const SizedBox(height: 12),

              // ── Bottom row: status + date + support ────────────────────
              Row(
                children: [
                  // Status badge
                  Container(
                    padding: const EdgeInsets.symmetric(horizontal: 9, vertical: 3),
                    decoration: BoxDecoration(
                      color:        c.status.statusColor.withOpacity(0.12),
                      borderRadius: BorderRadius.circular(20),
                      border: Border.all(
                        color: c.status.statusColor.withOpacity(0.35),
                      ),
                    ),
                    child: Text(
                      c.status.displayStatus,
                      style: TextStyle(
                        fontSize:   11,
                        fontWeight: FontWeight.w600,
                        color:      c.status.statusColor,
                      ),
                    ),
                  ),
                  const Spacer(),

                  // Support count
                  if (c.supportCount > 0) ...[
                    const Icon(
                      Icons.thumb_up_outlined,
                      size:  13,
                      color: AppColors.onSurfaceVar,
                    ),
                    const SizedBox(width: 3),
                    Text(
                      '${c.supportCount}',
                      style: const TextStyle(
                        fontSize: 12,
                        color:    AppColors.onSurfaceVar,
                      ),
                    ),
                    const SizedBox(width: 10),
                  ],

                  // Date
                  Text(
                    _formatDate(c.createdAt),
                    style: const TextStyle(
                      fontSize: 11,
                      color:    AppColors.onSurfaceVar,
                    ),
                  ),

                  // Chevron
                  if (onTap != null)
                    const Icon(
                      Icons.chevron_right_rounded,
                      size:  18,
                      color: AppColors.onSurfaceVar,
                    ),
                ],
              ),
            ],
          ),
        ),
      ),
    );
  }

  String _formatDate(DateTime d) {
    final now = DateTime.now();
    final diff = now.difference(d);
    if (diff.inDays == 0) {
      if (diff.inHours == 0)    return '${diff.inMinutes}m ago';
      return '${diff.inHours}h ago';
    }
    if (diff.inDays < 7) return '${diff.inDays}d ago';
    return '${d.day}/${d.month}/${d.year}';
  }
}