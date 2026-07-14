import 'package:flutter/material.dart';
import 'package:flutter_bloc/flutter_bloc.dart';
import 'package:go_router/go_router.dart';

import '../../../../core/theme/app_theme.dart';
import '../../../../shared/widgets/complaint_card.dart';
import '../../../../shared/widgets/shimmer_loader.dart';
import '../bloc/complaint_bloc.dart';

class ComplaintHistoryScreen extends StatefulWidget {
  const ComplaintHistoryScreen({super.key});

  @override
  State<ComplaintHistoryScreen> createState() => _ComplaintHistoryScreenState();
}

class _ComplaintHistoryScreenState extends State<ComplaintHistoryScreen> {
  final _searchCtrl   = TextEditingController();
  final _scrollCtrl   = ScrollController();
  String? _filterStatus;
  String? _filterCategory;
  bool    _isSearching = false;

  final _statuses = [
    'all', 'submitted', 'in_progress', 'resolved', 'closed', 'rejected',
  ];

  @override
  void initState() {
    super.initState();
    _fetchComplaints();
    _scrollCtrl.addListener(_onScroll);
  }

  @override
  void dispose() {
    _searchCtrl.dispose();
    _scrollCtrl.dispose();
    super.dispose();
  }

  void _fetchComplaints({bool refresh = false}) {
    context.read<ComplaintBloc>().add(ComplaintsFetchRequested(
      status:   _filterStatus,
      category: _filterCategory,
      search:   _searchCtrl.text.isNotEmpty ? _searchCtrl.text : null,
      refresh:  refresh,
    ));
  }

  void _onScroll() {
    if (_scrollCtrl.position.pixels >= _scrollCtrl.position.maxScrollExtent - 200) {
      final state = context.read<ComplaintBloc>().state;
      if (state is ComplaintsLoaded && state.hasMore && !state.isLoadingMore) {
        context.read<ComplaintBloc>().add(ComplaintsLoadMoreRequested());
      }
    }
  }

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      appBar: AppBar(
        title: _isSearching
            ? TextField(
                controller: _searchCtrl,
                autofocus: true,
                decoration: const InputDecoration(
                  hintText: 'Search complaints…',
                  border: InputBorder.none,
                ),
                onChanged: (_) => _fetchComplaints(),
              )
            : const Text('My Reports'),
        actions: [
          IconButton(
            icon: Icon(_isSearching ? Icons.close : Icons.search_rounded),
            onPressed: () {
              setState(() => _isSearching = !_isSearching);
              if (!_isSearching) {
                _searchCtrl.clear();
                _fetchComplaints(refresh: true);
              }
            },
          ),
          IconButton(
            icon: const Icon(Icons.filter_list_rounded),
            onPressed: _showFilterSheet,
          ),
        ],
      ),
      body: Column(
        children: [
          // ── Status filter tabs ──────────────────────────────────────
          SizedBox(
            height: 44,
            child: ListView.separated(
              scrollDirection: Axis.horizontal,
              padding: const EdgeInsets.symmetric(horizontal: 16, vertical: 6),
              itemCount: _statuses.length,
              separatorBuilder: (_, __) => const SizedBox(width: 8),
              itemBuilder: (_, i) {
                final s = _statuses[i];
                final selected = (s == 'all' && _filterStatus == null) ||
                    s == _filterStatus;
                return ChoiceChip(
                  label: Text(
                    s == 'all' ? 'All' : s.displayStatus,
                    style: const TextStyle(fontSize: 12),
                  ),
                  selected: selected,
                  selectedColor: s == 'all'
                      ? AppColors.primary.withOpacity(0.15)
                      : s.statusColor.withOpacity(0.15),
                  onSelected: (_) {
                    setState(() => _filterStatus = s == 'all' ? null : s);
                    _fetchComplaints(refresh: true);
                  },
                );
              },
            ),
          ),

          // ── List ────────────────────────────────────────────────────
          Expanded(
            child: BlocBuilder<ComplaintBloc, ComplaintState>(
              builder: (context, state) {
                if (state is ComplaintsLoading) {
                  return ListView.builder(
                    itemCount: 5,
                    itemBuilder: (_, __) => const ShimmerComplaintCard(),
                  );
                }

                if (state is ComplaintsLoaded) {
                  if (state.complaints.isEmpty) {
                    return _EmptyState(filterStatus: _filterStatus);
                  }
                  return RefreshIndicator(
                    onRefresh: () async => _fetchComplaints(refresh: true),
                    child: ListView.builder(
                      controller: _scrollCtrl,
                      padding: const EdgeInsets.only(bottom: 100),
                      itemCount: state.complaints.length + (state.hasMore ? 1 : 0),
                      itemBuilder: (_, i) {
                        if (i == state.complaints.length) {
                          return const Padding(
                            padding: EdgeInsets.all(24),
                            child: Center(child: CircularProgressIndicator()),
                          );
                        }
                        return ComplaintCard(
                          complaint: state.complaints[i],
                          onTap: () => context.push(
                            '/history/detail/${state.complaints[i].id}',
                          ),
                        );
                      },
                    ),
                  );
                }

                if (state is ComplaintError) {
                  return Center(
                    child: Column(mainAxisAlignment: MainAxisAlignment.center, children: [
                      const Icon(Icons.error_outline, size: 48, color: Colors.red),
                      const SizedBox(height: 12),
                      Text(state.message, textAlign: TextAlign.center),
                      const SizedBox(height: 16),
                      ElevatedButton(
                          onPressed: () => _fetchComplaints(refresh: true),
                          child: const Text('Retry')),
                    ]),
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

  void _showFilterSheet() {
    showModalBottomSheet(
      context: context,
      shape: const RoundedRectangleBorder(
          borderRadius: BorderRadius.vertical(top: Radius.circular(20))),
      builder: (_) => _FilterSheet(
        currentStatus: _filterStatus,
        currentCategory: _filterCategory,
        onApply: (status, category) {
          setState(() {
            _filterStatus   = status;
            _filterCategory = category;
          });
          _fetchComplaints(refresh: true);
        },
      ),
    );
  }
}

class _EmptyState extends StatelessWidget {
  final String? filterStatus;
  const _EmptyState({this.filterStatus});

  @override
  Widget build(BuildContext context) => Center(
    child: Column(mainAxisAlignment: MainAxisAlignment.center, children: [
      const Icon(Icons.assignment_outlined, size: 64, color: AppColors.onSurfaceVar),
      const SizedBox(height: 16),
      Text(
        filterStatus == null ? 'No complaints yet' : 'No ${filterStatus!.displayStatus} complaints',
        style: Theme.of(context).textTheme.titleMedium,
      ),
      const SizedBox(height: 8),
      const Text('Tap the camera button to report an issue',
          style: TextStyle(color: AppColors.onSurfaceVar)),
    ]),
  );
}

class _FilterSheet extends StatefulWidget {
  final String? currentStatus, currentCategory;
  final void Function(String? status, String? category) onApply;
  const _FilterSheet({this.currentStatus, this.currentCategory, required this.onApply});

  @override
  State<_FilterSheet> createState() => _FilterSheetState();
}

class _FilterSheetState extends State<_FilterSheet> {
  String? _status, _category;

  @override
  void initState() {
    super.initState();
    _status   = widget.currentStatus;
    _category = widget.currentCategory;
  }

  @override
  Widget build(BuildContext context) {
    return Padding(
      padding: const EdgeInsets.all(24),
      child: Column(
        mainAxisSize: MainAxisSize.min,
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Row(children: [
            Text('Filter', style: Theme.of(context).textTheme.titleLarge),
            const Spacer(),
            TextButton(
              onPressed: () {
                setState(() { _status = null; _category = null; });
              },
              child: const Text('Clear all'),
            ),
          ]),
          const SizedBox(height: 16),
          Text('Status', style: Theme.of(context).textTheme.titleMedium),
          const SizedBox(height: 10),
          Wrap(
            spacing: 8, runSpacing: 8,
            children: ['submitted', 'in_progress', 'resolved', 'closed', 'rejected']
                .map((s) => FilterChip(
                  label: Text(s.displayStatus, style: const TextStyle(fontSize: 12)),
                  selected: _status == s,
                  selectedColor: s.statusColor.withOpacity(0.2),
                  onSelected: (_) => setState(() => _status = _status == s ? null : s),
                )).toList(),
          ),
          const SizedBox(height: 20),
          SizedBox(
            width: double.infinity,
            child: ElevatedButton(
              onPressed: () {
                Navigator.pop(context);
                widget.onApply(_status, _category);
              },
              child: const Text('Apply Filters'),
            ),
          ),
          const SizedBox(height: 8),
        ],
      ),
    );
  }
}
