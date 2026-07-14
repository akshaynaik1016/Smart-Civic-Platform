import 'package:equatable/equatable.dart';
import 'package:flutter_bloc/flutter_bloc.dart';

import '../../data/models/notification_model.dart';
import '../../data/repositories/notification_repository.dart';
// ─── Events ───────────────────────────────────────────────────────────────────

abstract class NotificationEvent extends Equatable {
  const NotificationEvent();
  @override
  List<Object?> get props => [];
}

/// Called on app start from main.dart — subscribes to FCM and loads initial
/// unread count. Name must match exactly: main.dart uses NotificationInitRequested().
class NotificationInitRequested extends NotificationEvent {}

class NotificationsFetchRequested extends NotificationEvent {
  final bool unreadOnly;
  const NotificationsFetchRequested({this.unreadOnly = false});
  @override
  List<Object?> get props => [unreadOnly];
}

class NotificationMarkReadRequested extends NotificationEvent {
  final String notificationId;
  const NotificationMarkReadRequested(this.notificationId);
  @override
  List<Object?> get props => [notificationId];
}

class NotificationMarkAllReadRequested extends NotificationEvent {}

class NotificationReceivedPush extends NotificationEvent {
  final Map<String, dynamic> payload;
  const NotificationReceivedPush(this.payload);
  @override
  List<Object?> get props => [payload];
}

// ─── States ───────────────────────────────────────────────────────────────────

abstract class NotificationState extends Equatable {
  const NotificationState();
  @override
  List<Object?> get props => [];
}

class NotificationInitial extends NotificationState {}
class NotificationLoading extends NotificationState {}

class NotificationsLoaded extends NotificationState {
  final List<NotificationModel> notifications;
  final int unreadCount;
  const NotificationsLoaded({
    required this.notifications,
    this.unreadCount = 0,
  });
  @override
  List<Object?> get props => [notifications, unreadCount];
}

class NotificationError extends NotificationState {
  final String message;
  const NotificationError(this.message);
  @override
  List<Object?> get props => [message];
}

// ─── BLoC ─────────────────────────────────────────────────────────────────────

class NotificationBloc extends Bloc<NotificationEvent, NotificationState> {
  final NotificationRepository _repo;

  NotificationBloc(this._repo) : super(NotificationInitial()) {
    on<NotificationInitRequested>(_onInit);
    on<NotificationsFetchRequested>(_onFetch);
    on<NotificationMarkReadRequested>(_onMarkRead);
    on<NotificationMarkAllReadRequested>(_onMarkAllRead);
    on<NotificationReceivedPush>(_onPushReceived);
  }

  Future<void> _onInit(
    NotificationInitRequested event,
    Emitter<NotificationState> emit,
  ) async {
    try {
      // Silently fetch unread count on startup — don't block the app
      final notifications = await _repo.fetchNotifications(page: 1, pageSize: 20);
      final unread = notifications.where((n) => !n.isRead).length;
      emit(NotificationsLoaded(notifications: notifications, unreadCount: unread));
    } catch (_) {
      // Fail silently on init — notifications are non-critical
      emit(const NotificationsLoaded(notifications: [], unreadCount: 0));
    }
  }

  Future<void> _onFetch(
    NotificationsFetchRequested event,
    Emitter<NotificationState> emit,
  ) async {
    emit(NotificationLoading());
    try {
      final notifications = await _repo.fetchNotifications(
        page:       1,
        pageSize:   50,
        unreadOnly: event.unreadOnly,
      );
      final unread = notifications.where((n) => !n.isRead).length;
      emit(NotificationsLoaded(notifications: notifications, unreadCount: unread));
    } catch (e) {
      emit(NotificationError(e.toString().replaceFirst('Exception: ', '')));
    }
  }

  Future<void> _onMarkRead(
    NotificationMarkReadRequested event,
    Emitter<NotificationState> emit,
  ) async {
    try {
      await _repo.markRead(event.notificationId);
      add(const NotificationsFetchRequested());
    } catch (_) {}
  }

  Future<void> _onMarkAllRead(
    NotificationMarkAllReadRequested event,
    Emitter<NotificationState> emit,
  ) async {
    try {
      await _repo.markAllRead();
      add(const NotificationsFetchRequested());
    } catch (_) {}
  }

  Future<void> _onPushReceived(
    NotificationReceivedPush event,
    Emitter<NotificationState> emit,
  ) async {
    // Re-fetch to include the newly arrived notification
    add(const NotificationsFetchRequested());
  }
}