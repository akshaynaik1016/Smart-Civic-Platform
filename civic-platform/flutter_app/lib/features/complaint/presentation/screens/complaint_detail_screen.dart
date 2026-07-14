import 'package:flutter/material.dart';
import 'package:flutter_bloc/flutter_bloc.dart';
import 'package:google_maps_flutter/google_maps_flutter.dart';
import 'package:timeline_tile/timeline_tile.dart';

import '../../../../core/theme/app_theme.dart';
import '../../../../shared/widgets/severity_badge.dart';
import '../bloc/complaint_bloc.dart';

class ComplaintDetailScreen extends StatefulWidget {
  final String complaintId;
  const ComplaintDetailScreen({super.key, required this.complaintId});

  @override
  State<ComplaintDetailScreen> createState() => _ComplaintDetailScreenState();
}

class _ComplaintDetailScreenState extends State<ComplaintDetailScreen> {
  @override
  void initState() {
    super.initState();
    context.read<ComplaintBloc>().add(
        ComplaintDetailRequested(complaintId: widget.complaintId));
  }

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      appBar: AppBar(
        title: const Text('Complaint Detail'),
        actions: [
          IconButton(icon: const Icon(Icons.share_rounded), onPressed: () {}),
        ],
      ),
      body: BlocBuilder<ComplaintBloc, ComplaintState>(
        builder: (context, state) {
          if (state is ComplaintDetailLoading) {
            return const Center(child: CircularProgressIndicator());
          }

          if (state is ComplaintDetailLoaded) {
            final c = state.complaint;
            return SingleChildScrollView(
              padding: const EdgeInsets.only(bottom: 100),
              child: Column(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [

                  // ── Image carousel ───────────────────────────────────
                  SizedBox(
                    height: 220,
                    child: PageView.builder(
                      itemCount: c.images.isEmpty ? 1 : c.images.length,
                      itemBuilder: (_, i) {
                        if (c.images.isEmpty) {
                          return Container(
                            color: AppColors.surfaceVariant,
                            child: const Icon(Icons.image_not_supported_rounded,
                                size: 64, color: AppColors.onSurfaceVar),
                          );
                        }
                        return Image.network(
                          c.images[i].cdnUrl ?? '',
                          fit: BoxFit.cover,
                          errorBuilder: (_, __, ___) => const Icon(Icons.broken_image),
                        );
                      },
                    ),
                  ),

                  Padding(
                    padding: const EdgeInsets.all(20),
                    child: Column(
                      crossAxisAlignment: CrossAxisAlignment.start,
                      children: [

                        // ── Header ──────────────────────────────────────
                        Row(children: [
                          Expanded(
                            child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
                              Text(c.complaintNumber,
                                  style: const TextStyle(
                                    fontSize: 12, color: AppColors.onSurfaceVar,
                                    fontWeight: FontWeight.w600,
                                  )),
                              const SizedBox(height: 4),
                              Text(c.title,
                                  style: Theme.of(context).textTheme.headlineSmall),
                            ]),
                          ),
                          SeverityBadge(severity: c.severity),
                        ]),
                        const SizedBox(height: 12),

                        // ── Status chip ─────────────────────────────────
                        Container(
                          padding: const EdgeInsets.symmetric(horizontal: 12, vertical: 6),
                          decoration: BoxDecoration(
                            color: c.status.statusColor.withOpacity(0.12),
                            borderRadius: BorderRadius.circular(20),
                            border: Border.all(color: c.status.statusColor.withOpacity(0.4)),
                          ),
                          child: Text(
                            c.status.displayStatus,
                            style: TextStyle(
                              color: c.status.statusColor,
                              fontWeight: FontWeight.w600, fontSize: 13,
                            ),
                          ),
                        ),
                        const SizedBox(height: 20),

                        // ── Info rows ────────────────────────────────────
                        _InfoRow(Icons.category_rounded,    'Category',  c.category.displayCategory),
                        _InfoRow(Icons.location_on_rounded, 'Location',  c.address ?? 'Unknown'),
                        _InfoRow(Icons.calendar_today_rounded,'Reported', _formatDate(c.createdAt)),
                        if (c.resolvedAt != null)
                          _InfoRow(Icons.check_circle_rounded, 'Resolved', _formatDate(c.resolvedAt!)),

                        const Divider(height: 32),

                        // ── Description ─────────────────────────────────
                        Text('Description', style: Theme.of(context).textTheme.titleMedium),
                        const SizedBox(height: 8),
                        Text(c.description,
                            style: const TextStyle(height: 1.6, color: AppColors.onSurfaceVar)),

                        if (c.aiDescription != null && c.aiDescription!.isNotEmpty) ...[
                          const SizedBox(height: 12),
                          Container(
                            padding: const EdgeInsets.all(14),
                            decoration: BoxDecoration(
                              color: AppColors.primary.withOpacity(0.05),
                              borderRadius: BorderRadius.circular(14),
                              border: Border.all(color: AppColors.primary.withOpacity(0.2)),
                            ),
                            child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
                              const Row(children: [
                                Icon(Icons.auto_awesome, color: AppColors.primary, size: 14),
                                SizedBox(width: 6),
                                Text('AI Description',
                                    style: TextStyle(color: AppColors.primary,
                                        fontSize: 12, fontWeight: FontWeight.w700)),
                              ]),
                              const SizedBox(height: 6),
                              Text(c.aiDescription!, style: const TextStyle(fontSize: 13, height: 1.6)),
                            ]),
                          ),
                        ],

                        const Divider(height: 32),

                        // ── Mini map ────────────────────────────────────
                        Text('Location', style: Theme.of(context).textTheme.titleMedium),
                        const SizedBox(height: 12),
                        Container(
  width: double.infinity,
  height: 160,
  decoration: BoxDecoration(
    color: AppColors.surfaceVariant,
    borderRadius: BorderRadius.circular(16),
  ),
  child: const Center(
    child: Column(
      mainAxisAlignment: MainAxisAlignment.center,
      children: [
        Icon(
          Icons.map_rounded,
          size: 40,
          color: AppColors.onSurfaceVar,
        ),
        SizedBox(height: 8),
        Text(
          'Map Preview',
          style: TextStyle(
            color: AppColors.onSurfaceVar,
            fontWeight: FontWeight.w600,
          ),
        ),
      ],
    ),
  ),
),

                        const Divider(height: 32),

                        // ── Status timeline ─────────────────────────────
                        Text('Progress Timeline', style: Theme.of(context).textTheme.titleMedium),
                        const SizedBox(height: 12),
                        ...c.statusHistory.asMap().entries.map((entry) {
                          final i = entry.key;
                          final h = entry.value;
                          final isLast = i == c.statusHistory.length - 1;
                          return TimelineTile(
                            isFirst: i == 0,
                            isLast:  isLast,
                            indicatorStyle: IndicatorStyle(
                              color:  h.toStatus.statusColor,
                              width:  20, height: 20,
                              indicator: Container(
                                decoration: BoxDecoration(
                                  color:  h.toStatus.statusColor,
                                  shape: BoxShape.circle,
                                ),
                                child: const Icon(Icons.check, color: Colors.white, size: 12),
                              ),
                            ),
                            beforeLineStyle: LineStyle(color: h.toStatus.statusColor.withOpacity(0.3)),
                            endChild: Padding(
                              padding: const EdgeInsets.fromLTRB(12, 8, 16, 8),
                              child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
                                Text(h.toStatus.displayStatus,
                                    style: const TextStyle(fontWeight: FontWeight.w700, fontSize: 14)),
                                if (h.notes != null)
                                  Text(h.notes!, style: const TextStyle(
                                      color: AppColors.onSurfaceVar, fontSize: 12)),
                                Text(_formatDate(h.createdAt),
                                    style: const TextStyle(color: AppColors.onSurfaceVar, fontSize: 11)),
                              ]),
                            ),
                          );
                        }),

                        // ── Support count ───────────────────────────────
                        const SizedBox(height: 16),
                        Row(children: [
                          OutlinedButton.icon(
                            icon: const Icon(Icons.thumb_up_outlined, size: 18),
                            label: Text('Support (${c.supportCount})'),
                            onPressed: () {
                              context.read<ComplaintBloc>().add(
                                  ComplaintSupportToggled(complaintId: c.id));
                            },
                          ),
                          const SizedBox(width: 12),
                          OutlinedButton.icon(
                            icon: const Icon(Icons.share_rounded, size: 18),
                            label: const Text('Share'),
                            onPressed: () {},
                          ),
                        ]),
                      ],
                    ),
                  ),
                ],
              ),
            );
          }

          return const Center(child: Text('Something went wrong'));
        },
      ),

      // ── Verify Resolution Button ──────────────────────────────────────
      bottomNavigationBar: BlocBuilder<ComplaintBloc, ComplaintState>(
        builder: (context, state) {
          if (state is! ComplaintDetailLoaded) return const SizedBox.shrink();
          final c = state.complaint;
          if (c.status != 'resolved' || c.citizenVerified == true) {
            return const SizedBox.shrink();
          }
          return SafeArea(
            child: Padding(
              padding: const EdgeInsets.all(16),
              child: Column(mainAxisSize: MainAxisSize.min, children: [
                const Text('Please verify if your issue has been resolved.',
                    textAlign: TextAlign.center,
                    style: TextStyle(color: AppColors.onSurfaceVar, fontSize: 12)),
                const SizedBox(height: 12),
                Row(children: [
                  Expanded(
                    child: OutlinedButton(
                      onPressed: () {
                        context.read<ComplaintBloc>().add(
                            ComplaintVerifyRequested(complaintId: c.id, isResolved: false));
                      },
                      child: const Text('Not Resolved'),
                    ),
                  ),
                  const SizedBox(width: 12),
                  Expanded(
                    child: ElevatedButton(
                      onPressed: () {
                        context.read<ComplaintBloc>().add(
                            ComplaintVerifyRequested(complaintId: c.id, isResolved: true));
                      },
                      child: const Text('✅ Verified'),
                    ),
                  ),
                ]),
              ]),
            ),
          );
        },
      ),
    );
  }

  String _formatDate(DateTime d) =>
      '${d.day}/${d.month}/${d.year}  ${d.hour.toString().padLeft(2,'0')}:${d.minute.toString().padLeft(2,'0')}';
}

class _InfoRow extends StatelessWidget {
  final IconData icon;
  final String label, value;
  const _InfoRow(this.icon, this.label, this.value);

  @override
Widget build(BuildContext context) => Padding(
  padding: const EdgeInsets.symmetric(vertical: 6),
  child: Row(
    crossAxisAlignment: CrossAxisAlignment.start,
    children: [
      Icon(icon, size: 18, color: AppColors.primary),
      const SizedBox(width: 10),

      SizedBox(
        width: 85,
        child: Text(
          '$label:',
          style: const TextStyle(
            fontWeight: FontWeight.w600,
            fontSize: 13,
          ),
        ),
      ),

      Flexible(
        child: Text(
          value,
          softWrap: true,
          style: const TextStyle(
            fontSize: 13,
            color: AppColors.onSurfaceVar,
          ),
        ),
      ),
    ],
  ),
);
}
