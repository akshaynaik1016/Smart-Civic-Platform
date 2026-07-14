import '../../../../core/network/api_client.dart';
import '../models/notification_model.dart';

class NotificationRepository {
  final _client = ApiClient.instance.client;

  Future<List<NotificationModel>> fetchNotifications({
    int page = 1,
    int pageSize = 20,
    bool unreadOnly = false,
  }) async {
    try {
      final res = await _client.get(
        '/notifications/me',
        queryParameters: {
          'page':       page,
          'page_size':  pageSize,
          if (unreadOnly) 'unread_only': true,
        },
      );
      final items = res.data['items'] as List<dynamic>? ?? [];
      return items
          .map((e) => NotificationModel.fromJson(e as Map<String, dynamic>))
          .toList();
    } catch (e) {
      throw Exception(dioErrorMessage(e));
    }
  }

  Future<int> fetchUnreadCount() async {
    try {
      final res = await _client.get('/notifications/me/unread-count');
      return (res.data['unread_count'] as num?)?.toInt() ?? 0;
    } catch (_) {
      return 0;
    }
  }

  Future<void> markRead(String notificationId) async {
    try {
      await _client.patch('/notifications/$notificationId/read');
    } catch (e) {
      throw Exception(dioErrorMessage(e));
    }
  }

  Future<void> markAllRead() async {
    try {
      await _client.post('/notifications/me/read-all');
    } catch (e) {
      throw Exception(dioErrorMessage(e));
    }
  }
}