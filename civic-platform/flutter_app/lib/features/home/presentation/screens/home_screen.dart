import 'package:flutter/material.dart';
import 'package:flutter_bloc/flutter_bloc.dart';
import 'package:go_router/go_router.dart';

import '../../../../core/router/app_router.dart';
import '../../../../core/theme/app_theme.dart';
import '../../../../shared/widgets/complaint_card.dart';
import '../../../../shared/widgets/shimmer_loader.dart';
import '../../../auth/presentation/bloc/auth_bloc.dart';
import '../../../complaint/presentation/bloc/complaint_bloc.dart';

class HomeScreen extends StatefulWidget {
  const HomeScreen({super.key});

  @override
  State<HomeScreen> createState() => _HomeScreenState();
}

class _HomeScreenState extends State<HomeScreen> {
  @override
  void initState() {
    super.initState();
    context.read<ComplaintBloc>().add(ComplaintsFetchRequested());
  }

  @override
  Widget build(BuildContext context) {
    final auth  = context.watch<AuthBloc>().state;
    final user  = auth is AuthAuthenticated ? auth.user : null;

    return Scaffold(
      body: RefreshIndicator(
        onRefresh: () async {
          context.read<ComplaintBloc>().add(ComplaintsFetchRequested());
        },
        child: CustomScrollView(
          slivers: [
            // ── App Bar ─────────────────────────────────────────────────────
            SliverAppBar(
              expandedHeight: 180,
              floating: false,
              pinned: true,
              backgroundColor: AppColors.primary,
              flexibleSpace: FlexibleSpaceBar(
                background: Container(
                  decoration: const BoxDecoration(
                    gradient: LinearGradient(
                      begin: Alignment.topLeft, end: Alignment.bottomRight,
                      colors: [Color(0xFF1565C0), Color(0xFF0D47A1)],
                    ),
                  ),
                  padding: const EdgeInsets.fromLTRB(20, 60, 20, 16),
                  child: Column(
                    crossAxisAlignment: CrossAxisAlignment.start,
                    mainAxisAlignment: MainAxisAlignment.end,
                    children: [
                      Row(children: [
                        CircleAvatar(
                          radius: 22,
                          backgroundColor: Colors.white24,
                          child: Text(
                            (user?.fullName.isNotEmpty == true)
                                ? user!.fullName[0].toUpperCase()
                                : 'U',
                            style: const TextStyle(
                              color: Colors.white, fontWeight: FontWeight.w700, fontSize: 18,
                            ),
                          ),
                        ),
                        const SizedBox(width: 12),
                        Expanded(
                          child: Column(
                            crossAxisAlignment: CrossAxisAlignment.start,
                            children: [
                              Text(
                                'Good ${_greeting()}, 👋',
                                style: const TextStyle(color: Colors.white70, fontSize: 13),
                              ),
                              Text(
                                user?.fullName ?? 'Citizen',
                                style: const TextStyle(
                                  color: Colors.white, fontSize: 17,
                                  fontWeight: FontWeight.w700,
                                ),
                                overflow: TextOverflow.ellipsis,
                              ),
                            ],
                          ),
                        ),
                        IconButton(
                          icon: const Icon(Icons.notifications_outlined, color: Colors.white),
                          onPressed: () => context.go(AppRoutes.notifications),
                        ),
                      ]),
                    ],
                  ),
                ),
              ),
            ),

            // ── Stats Row ────────────────────────────────────────────────────
            SliverToBoxAdapter(
              child: Transform.translate(
                offset: const Offset(0, -20),
                child: Padding(
                  padding: const EdgeInsets.symmetric(horizontal: 16),
                  child: Row(children: [
                    _StatCard(label: 'My Reports', value: '${user?.totalComplaints ?? 0}',
                        icon: Icons.assignment_rounded, color: AppColors.primary),
                    const SizedBox(width: 12),
                    _StatCard(label: 'Resolved',   value: '${user?.resolvedComplaints ?? 0}',
                        icon: Icons.check_circle_rounded, color: AppColors.statusResolved),
                    const SizedBox(width: 12),
                    _StatCard(label: 'Reputation', value: '${user?.reputationScore?.toStringAsFixed(0) ?? 0}',
                        icon: Icons.star_rounded, color: AppColors.accent),
                  ]),
                ),
              ),
            ),

            // ── Quick Actions ─────────────────────────────────────────────────
            SliverToBoxAdapter(
              child: Padding(
                padding: const EdgeInsets.fromLTRB(20, 0, 20, 0),
                child: Column(
                  crossAxisAlignment: CrossAxisAlignment.start,
                  children: [
                    Text('Quick Actions', style: Theme.of(context).textTheme.titleLarge),
                    const SizedBox(height: 16),
                    GridView.count(
                      crossAxisCount: 4,
                      shrinkWrap: true,
                      physics: const NeverScrollableScrollPhysics(),
                      crossAxisSpacing: 8,
                      mainAxisSpacing: 8,
                      children: [
                        _QuickAction(
                          icon: Icons.camera_alt_rounded, label: 'Report',
                          color: AppColors.primary,
                          onTap: () => context.push(AppRoutes.camera),
                        ),
                        _QuickAction(
                          icon: Icons.map_rounded, label: 'Nearby',
                          color: AppColors.secondary,
                          onTap: () => context.go(AppRoutes.map),
                        ),
                        _QuickAction(
                          icon: Icons.list_alt_rounded, label: 'History',
                          color: AppColors.severityHigh,
                          onTap: () => context.go(AppRoutes.history),
                        ),
                        _QuickAction(
                          icon: Icons.person_rounded, label: 'Profile',
                          color: AppColors.accent,
                          onTap: () => context.go(AppRoutes.profile),
                        ),
                      ],
                    ),
                  ],
                ),
              ),
            ),

            // ── Category Chips ────────────────────────────────────────────────
            SliverToBoxAdapter(
              child: Padding(
                padding: const EdgeInsets.fromLTRB(20, 24, 20, 0),
                child: Column(
                  crossAxisAlignment: CrossAxisAlignment.start,
                  children: [
                    Text('Common Issues', style: Theme.of(context).textTheme.titleLarge),
                    const SizedBox(height: 12),
                    Wrap(
                      spacing: 8, runSpacing: 8,
                      children: [
                        'pothole', 'garbage', 'water_leakage', 'open_manhole',
                        'broken_streetlight', 'fallen_tree',
                      ].map((cat) => ActionChip(
                        avatar: Text(cat.categoryEmoji, style: const TextStyle(fontSize: 14)),
                        label: Text(cat.displayCategory, style: const TextStyle(fontSize: 12)),
                        backgroundColor: cat.categoryColor.withOpacity(0.1),
                        side: BorderSide(color: cat.categoryColor.withOpacity(0.3)),
                        onPressed: () {
                          context.read<ComplaintBloc>().add(
                            ComplaintsFetchRequested(category: cat),
                          );
                        },
                      )).toList(),
                    ),
                  ],
                ),
              ),
            ),

            // ── Recent Complaints ─────────────────────────────────────────────
            SliverToBoxAdapter(
              child: Padding(
                padding: const EdgeInsets.fromLTRB(20, 24, 20, 12),
                child: Row(
                  mainAxisAlignment: MainAxisAlignment.spaceBetween,
                  children: [
                    Text('Recent Reports', style: Theme.of(context).textTheme.titleLarge),
                    TextButton(
                      onPressed: () => context.go(AppRoutes.history),
                      child: const Text('See all'),
                    ),
                  ],
                ),
              ),
            ),

            BlocBuilder<ComplaintBloc, ComplaintState>(
              builder: (context, state) {
                print("STATE = ${state.runtimeType}");
                if (state is ComplaintsLoaded) {

                    print("Complaints count = ${state.complaints.length}");

                  }
                if (state is ComplaintsLoading) {
                  return SliverList(
                    delegate: SliverChildBuilderDelegate(
                      (_, __) => const ShimmerComplaintCard(),
                      childCount: 4,
                    ),
                  );
                }
                if (state is ComplaintsLoaded) {
                  if (state.complaints.isEmpty) {
                    return const SliverToBoxAdapter(child: _EmptyReports());
                  }
                  return SliverList(
                    delegate: SliverChildBuilderDelegate(
                      (_, i) => ComplaintCard(complaint: state.complaints[i]),
                      childCount: state.complaints.take(5).length,
                    ),
                  );
                }
                if (state is ComplaintError) {
                  return SliverToBoxAdapter(
                    child: Center(
                      child: Padding(
                        padding: const EdgeInsets.all(32),
                        child: Column(
                          children: [
                            const Icon(Icons.error_outline, size: 48, color: Colors.red),
                            const SizedBox(height: 12),
                            Text(state.message, textAlign: TextAlign.center),
                            const SizedBox(height: 16),
                            ElevatedButton(
                              onPressed: () => context.read<ComplaintBloc>().add(ComplaintsFetchRequested()),
                              child: const Text('Retry'),
                            ),
                          ],
                        ),
                      ),
                    ),
                  );
                }
                return const SliverToBoxAdapter(child: SizedBox.shrink());
              },
            ),

            const SliverToBoxAdapter(child: SizedBox(height: 100)),
          ],
        ),
      ),
    );
  }

  String _greeting() {
    final h = DateTime.now().hour;
    if (h < 12) return 'morning';
    if (h < 17) return 'afternoon';
    return 'evening';
  }
}

// ─── Sub-widgets ─────────────────────────────────────────────────────────────

class _StatCard extends StatelessWidget {
  final String label, value;
  final IconData icon;
  final Color color;
  const _StatCard({required this.label, required this.value, required this.icon, required this.color});

  @override
  Widget build(BuildContext context) {
    return Expanded(
      child: Container(
        padding: const EdgeInsets.symmetric(vertical: 14, horizontal: 12),
        decoration: BoxDecoration(
          color: Theme.of(context).colorScheme.surface,
          borderRadius: BorderRadius.circular(16),
          boxShadow: [BoxShadow(color: Colors.black.withOpacity(0.07), blurRadius: 12, offset: const Offset(0, 4))],
        ),
        child: Column(
          children: [
            Icon(icon, color: color, size: 24),
            const SizedBox(height: 6),
            Text(value, style: TextStyle(fontSize: 20, fontWeight: FontWeight.w700, color: color)),
            const SizedBox(height: 2),
            Text(label, style: const TextStyle(fontSize: 10, color: AppColors.onSurfaceVar), textAlign: TextAlign.center),
          ],
        ),
      ),
    );
  }
}

class _QuickAction extends StatelessWidget {
  final IconData icon;
  final String label;
  final Color color;
  final VoidCallback onTap;
  const _QuickAction({required this.icon, required this.label, required this.color, required this.onTap});

  @override
  Widget build(BuildContext context) {
    return GestureDetector(
      onTap: onTap,
      child: Column(
        mainAxisSize: MainAxisSize.min,
        children: [
          Container(
            width: 56, height: 56,
            decoration: BoxDecoration(
              color: color.withOpacity(0.12),
              borderRadius: BorderRadius.circular(16),
            ),
            child: Icon(icon, color: color, size: 28),
          ),
          const SizedBox(height: 6),
          Text(label, style: const TextStyle(fontSize: 11, fontWeight: FontWeight.w600)),
        ],
      ),
    );
  }
}

class _EmptyReports extends StatelessWidget {
  const _EmptyReports();
  @override
  Widget build(BuildContext context) {
    return Padding(
      padding: const EdgeInsets.all(40),
      child: Column(
        children: [
          const Icon(Icons.inbox_rounded, size: 64, color: AppColors.onSurfaceVar),
          const SizedBox(height: 16),
          Text('No reports yet', style: Theme.of(context).textTheme.titleMedium),
          const SizedBox(height: 8),
          const Text(
            'Be the first to report a civic issue in your area.',
            textAlign: TextAlign.center,
            style: TextStyle(color: AppColors.onSurfaceVar),
          ),
        ],
      ),
    );
  }
}
