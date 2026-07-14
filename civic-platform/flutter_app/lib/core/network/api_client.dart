import 'dart:io';
import 'package:dio/dio.dart';
import 'package:flutter_secure_storage/flutter_secure_storage.dart';
import 'package:pretty_dio_logger/pretty_dio_logger.dart';

import '../constants/app_constants.dart';

class ApiClient {
  static ApiClient? _instance;
  late final Dio dio;
  final _storage = const FlutterSecureStorage();

  ApiClient._() {
  print("BASE URL = ${AppConstants.baseUrl}");
  () async {
  try {
    final client = HttpClient();
    final request = await client.getUrl(Uri.parse('http://127.0.0.1:8000/docs'));
    final response = await request.close();
    print("HTTP TEST STATUS: ${response.statusCode}");
  } catch (e) {
    print("HTTP TEST ERROR: $e");
  }
}();
  dio = Dio(
    BaseOptions(
      baseUrl: AppConstants.baseUrl,
      connectTimeout: AppConstants.connectTimeout,
      receiveTimeout: AppConstants.receiveTimeout,
      headers: {
        'Content-Type': 'application/json',
        'Accept': 'application/json'
      },
    ),
  );
    dio.interceptors.addAll([
      _AuthInterceptor(dio, _storage),
      PrettyDioLogger(
        requestHeader: false, requestBody: true,
        responseBody: true,   error: true, compact: true,
      ),
    ]);
  }

  static ApiClient get instance {
    _instance ??= ApiClient._();
    return _instance!;
  }

  Dio get client => dio;
}

class _AuthInterceptor extends Interceptor {
  final Dio _dio;
  final FlutterSecureStorage _storage;

  _AuthInterceptor(this._dio, this._storage);

  @override
  Future<void> onRequest(
    RequestOptions options, RequestInterceptorHandler handler,
  ) async {
    final token = await _storage.read(key: AppConstants.tokenKey);
    print("TOKEN FROM STORAGE = $token");
    if (token != null) {
      options.headers['Authorization'] = 'Bearer $token';
    }
    print("AUTH HEADER = ${options.headers['Authorization']}");
    handler.next(options);
  }

  @override
  Future<void> onError(
    DioException err, ErrorInterceptorHandler handler,
  ) async {
    if (err.response?.statusCode == 401) {
      try {
        final refreshToken = await _storage.read(key: AppConstants.refreshKey);
        if (refreshToken == null) {
          await _clearTokens();
          return handler.reject(err);
        }

        final response = await Dio().post(
          '${AppConstants.baseUrl}/auth/refresh',
          data: {'refresh_token': refreshToken},
          options: Options(headers: {'Content-Type': 'application/json'}),
        );

        final newToken = response.data['access_token'] as String?;
        final newRefresh = response.data['refresh_token'] as String?;

        if (newToken != null) {
          await _storage.write(key: AppConstants.tokenKey, value: newToken);
          if (newRefresh != null) {
            await _storage.write(key: AppConstants.refreshKey, value: newRefresh);
          }

          err.requestOptions.headers['Authorization'] = 'Bearer $newToken';
          final retryResponse = await _dio.fetch(err.requestOptions);
          return handler.resolve(retryResponse);
        }
      } catch (_) {
        await _clearTokens();
      }
    }
    handler.reject(err);
  }

  Future<void> _clearTokens() async {
    await _storage.delete(key: AppConstants.tokenKey);
    await _storage.delete(key: AppConstants.refreshKey);
  }
}

// Helper to convert Dio errors to friendly messages
String dioErrorMessage(Object error) {
  if (error is DioException) {
    final data = error.response?.data;

    if (data is Map<String, dynamic>) {
      return data['detail'] as String? ??
          data['message'] as String? ??
          'Request failed (${error.response?.statusCode})';
    }

    if (error.type == DioExceptionType.connectionTimeout)
      return 'Connection timeout';

    if (error.type == DioExceptionType.receiveTimeout)
      return 'Server took too long to respond';

    if (error.type == DioExceptionType.connectionError) {
      print("========== DIO CONNECTION ERROR ==========");
      print("URI: ${error.requestOptions.uri}");
      print("MESSAGE: ${error.message}");
      print("ERROR: ${error.error}");
      print("TYPE: ${error.type}");
      return 'No internet connection';
    }

    return 'Network error: ${error.message}';
  }

  return error.toString();
}