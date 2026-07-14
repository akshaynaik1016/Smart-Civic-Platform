// ignore_for_file: constant_identifier_names
class AppConstants {
  AppConstants._();

  // Change to your machine's IP when running on a physical device
  // e.g. 'http://192.168.1.100:8000/api/v1'
  static const String baseUrl = 'http://localhost:8000/api/v1';

  static const Duration connectTimeout = Duration(seconds: 30);
  static const Duration receiveTimeout = Duration(seconds: 60);

  static const String tokenKey     = 'access_token';
  static const String refreshKey   = 'refresh_token';
  static const String userKey      = 'cached_user';
  static const String pendingEmail = 'pending_otp_email';

  static const int defaultPageSize = 20;
}