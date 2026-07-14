import 'package:flutter/material.dart';
import 'package:flutter_bloc/flutter_bloc.dart';

import '../../../../core/theme/app_theme.dart';
import '../../../complaint/presentation/bloc/complaint_bloc.dart';
import '../../../../shared/widgets/complaint_card.dart';
import '../../../../shared/widgets/shimmer_loader.dart';

class NearbyMapScreen extends StatefulWidget {
  const NearbyMapScreen({super.key});

  @override
  State<NearbyMapScreen> createState() => _NearbyMapScreenState();
}

class _NearbyMapScreenState extends State<NearbyMapScreen> {
  double _radiusKm = 5.0;

  @override
  void initState() {
    super.initState();
    // Fetch unfiltered list as a proxy for nearby — full geo query requires
    // location permission which is handled separately. The list shown here
    // is sorted by recency; a map tile would replace this in the next release.
    context.read<ComplaintBloc>().add(const ComplaintsFetchRequested());
  }

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      appBar: AppBar(
        title: const Text('Nearby Issues'),
        actions: [
          IconButton(
            icon: const Icon(Icons.tune_rounded),
            onPressed: _showRadiusPicker,
            tooltip: 'Change radius',
          ),
        ],
      ),
      body: Column(
        children: [
          // ── Map placeholder ──────────────────────────────────────────────
          Container(
            height: 220,
            width:  double.infinity,
            decoration: BoxDecoration(
              gradient: LinearGradient(
                colors: [
                  AppColors.primary.withOpacity(0.12),
                  AppColors.secondary.withOpacity(0.12),
                ],
                begin: Alignment.topLeft,
                end:   Alignment.bottomRight,
              ),
            ),
            child: Stack(
              children: [
                // Decorative grid lines to suggest a map
                CustomPaint(
                  size: const Size(double.infinity, 220),
                  painter: _MapGridPainter(),
                ),
                Center(
                  child: Column(
                    mainAxisAlignment: MainAxisAlignment.center,
                    children: [
                      Container(
                        padding: const EdgeInsets.all(16),
                        decoration: BoxDecoration(
                          color:        AppColors.primary.withOpacity(0.9),
                          shape:        BoxShape.circle,
                          boxShadow: [
                            BoxShadow(
                              color:      AppColors.primary.withOpacity(0.4),
                              blurRadius: 20,
                              spreadRadius: 4,
                            ),
                          ],
                        ),
                        child: const Icon(
                          Icons.my_location_rounded,
                          color: Colors.white,
                          size:  28,
                        ),
                      ),
                      const SizedBox(height: 12),
                      Container(
                        padding: const EdgeInsets.symmetric(
                            horizontal: 16, vertical: 6),
                        decoration: BoxDecoration(
                          color:        Colors.white.withOpacity(0.9),
                          borderRadius: BorderRadius.circular(20),
                        ),
                        child: Text(
                          'Showing issues within ${_radiusKm.toStringAsFixed(0)} km',
                          style: const TextStyle(
                            color:      AppColors.primary,
                            fontWeight: FontWeight.w600,
                            fontSize:   13,
                          ),
                        ),
                      ),
                      const SizedBox(height: 6),
                      const Text(
                        'Interactive map requires Google Maps SDK',
                        style: TextStyle(
                            fontSize: 11, color: AppColors.onSurfaceVar),
                      ),
                    ],
                  ),
                ),
              ],
            ),
          ),

          // ── Issue list ───────────────────────────────────────────────────
          Expanded(
            child: BlocBuilder<ComplaintBloc, ComplaintState>(
              builder: (context, state) {
                if (state is ComplaintsLoading) {
                  return ListView.builder(
                    itemCount:   4,
                    itemBuilder: (_, __) => const ShimmerComplaintCard(),
                  );
                }

                if (state is ComplaintsLoaded) {
                  if (state.complaints.isEmpty) {
                    return const Center(
                      child: Column(
                        mainAxisAlignment: MainAxisAlignment.center,
                        children: [
                          Icon(Icons.location_off_rounded,
                              size: 56, color: AppColors.onSurfaceVar),
                          SizedBox(height: 16),
                          Text(
                            'No issues found nearby',
                            style: TextStyle(
                                fontWeight: FontWeight.w600, fontSize: 16),
                          ),
                          SizedBox(height: 8),
                          Text(
                            'Try increasing the search radius',
                            style:
                                TextStyle(color: AppColors.onSurfaceVar),
                          ),
                        ],
                      ),
                    );
                  }

                  return RefreshIndicator(
                    onRefresh: () async => context
                        .read<ComplaintBloc>()
                        .add(const ComplaintsFetchRequested()),
                    child: ListView.builder(
                      padding:     const EdgeInsets.only(bottom: 100),
                      itemCount:   state.complaints.length,
                      itemBuilder: (_, i) =>
                          ComplaintCard(complaint: state.complaints[i]),
                    ),
                  );
                }

                if (state is ComplaintError) {
                  return Center(
                    child: Column(
                      mainAxisAlignment: MainAxisAlignment.center,
                      children: [
                        const Icon(Icons.error_outline,
                            size: 48, color: Colors.red),
                        const SizedBox(height: 12),
                        Text(state.message, textAlign: TextAlign.center),
                        const SizedBox(height: 16),
                        ElevatedButton(
                          onPressed: () => context
                              .read<ComplaintBloc>()
                              .add(const ComplaintsFetchRequested()),
                          child: const Text('Retry'),
                        ),
                      ],
                    ),
                  );
                }

                return const SizedBox.shrink();
              },
            ),
          ),
        ],
      ),
    );
  }

  void _showRadiusPicker() {
    showModalBottomSheet<void>(
      context: context,
      shape: const RoundedRectangleBorder(
        borderRadius: BorderRadius.vertical(top: Radius.circular(20)),
      ),
      builder: (_) => StatefulBuilder(
        builder: (context, setModalState) => Padding(
          padding: const EdgeInsets.all(24),
          child: Column(
            mainAxisSize: MainAxisSize.min,
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              Text('Search Radius',
                  style: Theme.of(context).textTheme.titleLarge),
              const SizedBox(height: 8),
              Text(
                '${_radiusKm.toStringAsFixed(0)} km',
                style: const TextStyle(
                  fontSize:   28,
                  fontWeight: FontWeight.w700,
                  color:      AppColors.primary,
                ),
              ),
              Slider(
                value:    _radiusKm,
                min:      1,
                max:      20,
                divisions: 19,
                onChanged: (v) {
                  setModalState(() => _radiusKm = v);
                  setState(() => _radiusKm = v);
                },
              ),
              const SizedBox(height: 8),
              SizedBox(
                width: double.infinity,
                child: ElevatedButton(
                  onPressed: () {
                    Navigator.pop(context);
                    context
                        .read<ComplaintBloc>()
                        .add(const ComplaintsFetchRequested());
                  },
                  child: const Text('Apply'),
                ),
              ),
              const SizedBox(height: 8),
            ],
          ),
        ),
      ),
    );
  }
}

class _MapGridPainter extends CustomPainter {
  @override
  void paint(Canvas canvas, Size size) {
    final paint = Paint()
      ..color = AppColors.primary.withOpacity(0.08)
      ..strokeWidth = 1;

    const spacing = 40.0;
    for (double x = 0; x < size.width; x += spacing) {
      canvas.drawLine(Offset(x, 0), Offset(x, size.height), paint);
    }
    for (double y = 0; y < size.height; y += spacing) {
      canvas.drawLine(Offset(0, y), Offset(size.width, y), paint);
    }
  }

  @override
  bool shouldRepaint(covariant CustomPainter oldDelegate) => false;
}