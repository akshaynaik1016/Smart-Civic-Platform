import 'package:flutter/material.dart';
import 'package:flutter_bloc/flutter_bloc.dart';
import 'package:go_router/go_router.dart';
import 'package:intl/intl.dart';

import '../../../../core/theme/app_theme.dart';
import '../../data/models/notification_model.dart';
import '../bloc/notification_bloc.dart';

class NotificationsScreen extends StatefulWidget {
  const NotificationsScreen({super.key});

  @override
  State<NotificationsScreen> createState() => _NotificationsScreenState();
}

class _NotificationsScreenState extends State<NotificationsScreen> {
  @override
  void initState() {
    super.initState();
    context
        .read<NotificationBloc>()
        .add(const NotificationsFetchRequested());
  }

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      appBar: AppBar(
        title: const Text('Notifications'),
        actions: [
          BlocBuilder<NotificationBloc, NotificationState>(
            builder: (context, state) {
              if (state is NotificationsLoaded && state.unreadCount > 0) {
                return TextButton(
                  onPressed: () => context
                      .read<NotificationBloc>()
                      .add(NotificationMarkAllReadRequested()),
                  child: const Text('Mark all read'),
                );
              }
              return const SizedBox.shrink();
            },
          ),
        ],
      ),
      body: BlocBuilder<NotificationBloc, NotificationState>(
        builder: (context, state) {
          if (state is NotificationLoading) {
            return const Center(child: CircularProgressIndicator());
          }

          if (state is NotificationsLoaded) {
            if (state.notifications.isEmpty) {
              return const _EmptyNotifications();
            }
            return RefreshIndicator(
              onRefresh: () async => context
                  .read<NotificationBloc>()
                  .add(const NotificationsFetchRequested()),
              child: ListView.separated(
                itemCount:   state.notifications.length,
                separatorBuilder: (_, __) =>
                    const Divider(height: 1, indent: 72),
                itemBuilder: (_, i) => _NotificationTile(
                  notification: state.notifications[i],
                  onTap: () {
                    final n = state.notifications[i];
                    if (!n.isRead) {
                      context
                          .read<NotificationBloc>()
                          .add(NotificationMarkReadRequested(n.id));
                    }
                    if (n.complaintId != null) {
                      context.push('/history/detail/${n.complaintId}');
                    }
                  },
                ),
              ),
            );
          }

          if (state is NotificationError) {
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
                        .read<NotificationBloc>()
                        .add(const NotificationsFetchRequested()),
                    child: const Text('Retry'),
                  ),
                ],
              ),
            );
          }

          return const SizedBox.shrink();
        },
      ),
    );
  }
}

class _NotificationTile extends StatelessWidget {
  final NotificationModel notification;
  final VoidCallback onTap;

  const _NotificationTile({
    required this.notification,
    required this.onTap,
  });

  @override
  Widget build(BuildContext context) {
    final n        = notification;
    final isUnread = !n.isRead;

    return InkWell(
      onTap: onTap,
      child: Container(
        color: isUnread
            ? AppColors.primary.withOpacity(0.05)
            : Colors.transparent,
        padding: const EdgeInsets.symmetric(horizontal: 16, vertical: 14),
        child: Row(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            // Icon
            Container(
              width:  44,
              height: 44,
              decoration: BoxDecoration(
                color:  _iconColor(n.type).withOpacity(0.12),
                shape: BoxShape.circle,
              ),
              child: Icon(
                _iconData(n.type),
                color: _iconColor(n.type),
                size:  22,
              ),
            ),
            const SizedBox(width: 12),

            // Content
            Expanded(
              child: Column(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  Text(
                    n.title,
                    style: TextStyle(
                      fontWeight:
                          isUnread ? FontWeight.w700 : FontWeight.w500,
                      fontSize: 14,
                    ),
                  ),
                  const SizedBox(height: 3),
                  Text(
                    n.body,
                    style: const TextStyle(
                      fontSize: 13,
                      color:    AppColors.onSurfaceVar,
                      height:   1.4,
                    ),
                    maxLines: 2,
                    overflow: TextOverflow.ellipsis,
                  ),
                  const SizedBox(height: 6),
                  Text(
                    _formatDate(n.createdAt),
                    style: const TextStyle(
                      fontSize: 11,
                      color:    AppColors.onSurfaceVar,
                    ),
                  ),
                ],
              ),
            ),

            // Unread dot
            if (isUnread)
              Container(
                width:  8,
                height: 8,
                margin: const EdgeInsets.only(top: 4, left: 8),
                decoration: const BoxDecoration(
                  color:  AppColors.primary,
                  shape: BoxShape.circle,
                ),
              ),
          ],
        ),
      ),
    );
  }

  IconData _iconData(String type) => switch (type) {
        'complaint_submitted'      => Icons.assignment_turned_in_rounded,
        'complaint_assigned'       => Icons.person_pin_rounded,
        'complaint_status_changed' => Icons.update_rounded,
        'complaint_resolved'       => Icons.check_circle_rounded,
        'verification_required'    => Icons.verified_rounded,
        'duplicate_detected'       => Icons.copy_rounded,
        _                          => Icons.notifications_rounded,
      };

  Color _iconColor(String type) => switch (type) {
        'complaint_submitted'      => AppColors.statusSubmitted,
        'complaint_assigned'       => AppColors.statusAssigned,
        'complaint_status_changed' => AppColors.statusInProgress,
        'complaint_resolved'       => AppColors.statusResolved,
        'verification_required'    => AppColors.accent,
        'duplicate_detected'       => AppColors.secondary,
        _                          => AppColors.primary,
      };

  String _formatDate(DateTime d) {
    final now  = DateTime.now();
    final diff = now.difference(d);
    if (diff.inMinutes < 60) return '${diff.inMinutes}m ago';
    if (diff.inHours   < 24) return '${diff.inHours}h ago';
    if (diff.inDays    <  7) return '${diff.inDays}d ago';
    return DateFormat('d MMM y').format(d);
  }
}

class _EmptyNotifications extends StatelessWidget {
  const _EmptyNotifications();

  @override
  Widget build(BuildContext context) {
    return Center(
      child: Column(
        mainAxisAlignment: MainAxisAlignment.center,
        children: [
          Container(
            padding: const EdgeInsets.all(24),
            decoration: BoxDecoration(
              color:  AppColors.surfaceVariant,
              shape: BoxShape.circle,
            ),
            child: const Icon(
              Icons.notifications_none_rounded,
              size:  48,
              color: AppColors.onSurfaceVar,
            ),
          ),
          const SizedBox(height: 20),
          Text(
            'No notifications yet',
            style: Theme.of(context).textTheme.titleMedium,
          ),
          const SizedBox(height: 8),
          const Text(
            'You\'ll be notified about complaint\nupdates and status changes here.',
            textAlign: TextAlign.center,
            style:     TextStyle(color: AppColors.onSurfaceVar, height: 1.5),
          ),
        ],
      ),
    );
  }
}