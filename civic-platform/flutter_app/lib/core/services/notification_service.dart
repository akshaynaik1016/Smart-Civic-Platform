import 'package:firebase_messaging/firebase_messaging.dart';
import 'package:flutter_local_notifications/flutter_local_notifications.dart';

class NotificationService {
  NotificationService._();
  static final NotificationService instance = NotificationService._();

  final _localNotifications = FlutterLocalNotificationsPlugin();
  final _fcm = FirebaseMessaging.instance;

  static const _channelId   = 'smart_civic_channel';
  static const _channelName = 'Smart Civic Alerts';
  static const _channelDesc = 'Civic complaint status and system alerts';

  Future<void> initialise() async {
    // ── Local notifications setup ─────────────────────────────────────────────
    const androidSettings =
        AndroidInitializationSettings('@mipmap/ic_launcher');
    const iosSettings = DarwinInitializationSettings(
      requestAlertPermission: true,
      requestBadgePermission: true,
      requestSoundPermission: true,
    );

    await _localNotifications.initialize(
      const InitializationSettings(
        android: androidSettings,
        iOS:     iosSettings,
      ),
      onDidReceiveNotificationResponse: _onNotificationTap,
    );

    // Create Android notification channel
    const channel = AndroidNotificationChannel(
      _channelId, _channelName,
      description: _channelDesc,
      importance: Importance.high,
    );
    await _localNotifications
        .resolvePlatformSpecificImplementation<
            AndroidFlutterLocalNotificationsPlugin>()
        ?.createNotificationChannel(channel);

    // ── FCM permission + token ────────────────────────────────────────────────
    await _fcm.requestPermission(
      alert:      true,
      badge:      true,
      sound:      true,
      provisional: false,
    );

    // Handle foreground FCM messages
    FirebaseMessaging.onMessage.listen(_onForegroundMessage);

    // Handle notification tap when app is in background (opened from notification)
    FirebaseMessaging.onMessageOpenedApp.listen(_onMessageOpenedApp);
  }

  Future<String?> getFcmToken() => _fcm.getToken();

  Future<void> showLocalNotification(RemoteMessage message) async {
    final notification = message.notification;
    if (notification == null) return;

    await _localNotifications.show(
      notification.hashCode,
      notification.title ?? 'Smart Civic',
      notification.body  ?? '',
      NotificationDetails(
        android: AndroidNotificationDetails(
          _channelId,
          _channelName,
          channelDescription: _channelDesc,
          importance: Importance.high,
          priority:   Priority.high,
          icon:       '@mipmap/ic_launcher',
          styleInformation: BigTextStyleInformation(
            notification.body ?? '',
          ),
        ),
        iOS: const DarwinNotificationDetails(
          presentAlert: true,
          presentBadge: true,
          presentSound: true,
        ),
      ),
    );
  }

  void _onForegroundMessage(RemoteMessage message) {
    showLocalNotification(message);
  }

  void _onMessageOpenedApp(RemoteMessage message) {
    // Navigation on tap is handled at router level via
    // the 'complaint_id' key in message.data, if present.
  }

  void _onNotificationTap(NotificationResponse response) {
    // Deep-link handling can be added here
  }
}