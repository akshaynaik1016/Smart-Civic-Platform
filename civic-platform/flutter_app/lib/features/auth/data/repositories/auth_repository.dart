import 'dart:convert';

import 'package:flutter_secure_storage/flutter_secure_storage.dart';

import '../../../../core/constants/app_constants.dart';
import '../../../../core/network/api_client.dart';
import '../models/user_model.dart';

class AuthRepository {
  final _client  = ApiClient.instance.client;
  final _storage = const FlutterSecureStorage();

  String? _pendingEmail;

  // ── Login ─────────────────────────────────────────────────────────────────

  Future<UserModel> login({required String email, required String password}) async {
    try {
      final res = await _client.post(
        '/auth/login',
        data: {'email': email, 'password': password},
      );
      await _saveTokens(res.data);
      return UserModel.fromJson(res.data['user'] as Map<String, dynamic>);
    } catch (e, s) {
  print("========== LOGIN ERROR ==========");
  print(e);
  print(s);
  rethrow;
}
  }

  // ── Register ──────────────────────────────────────────────────────────────

  Future<void> register({
    required String fullName,
    required String email,
    required String phone,
    required String password,
  }) async {
    try {
      await _client.post('/auth/register', data: {
        'full_name': fullName,
        'email':     email,
        'phone':     phone,
        'password':  password,
      });
      _pendingEmail = email;
      await _storage.write(key: AppConstants.pendingEmail, value: email);
    } catch (e) {
      throw Exception(dioErrorMessage(e));
    }
  }

  // ── OTP verify ────────────────────────────────────────────────────────────

  Future<UserModel> verifyOtp({required String otp}) async {
    final email = _pendingEmail ??
        await _storage.read(key: AppConstants.pendingEmail) ??
        '';
    try {
      final res = await _client.post('/auth/otp/verify', data: {
        'email':   email,
        'otp':     otp,
        'purpose': 'verify',
      });
      await _saveTokens(res.data);
      return UserModel.fromJson(res.data['user'] as Map<String, dynamic>);
    } catch (e) {
      throw Exception(dioErrorMessage(e));
    }
  }

  // ── Current user (from cache or server) ──────────────────────────────────

  Future<UserModel?> getCurrentUser() async {
    final token = await _storage.read(key: AppConstants.tokenKey);
    if (token == null) return null;

    // Try cache first
    final cached = await _storage.read(key: AppConstants.userKey);
    if (cached != null) {
      try {
        return UserModel.fromJson(jsonDecode(cached) as Map<String, dynamic>);
      } catch (_) {}
    }

    // Re-fetch from server
    try {
      final res = await _client.get('/auth/me');
      final user = UserModel.fromJson(res.data as Map<String, dynamic>);
      await _storage.write(key: AppConstants.userKey, value: jsonEncode(user.toJson()));
      return user;
    } catch (_) {
      return null;
    }
  }

  // ── Logout ────────────────────────────────────────────────────────────────

  Future<void> logout() async {
    try {
      await _client.post('/auth/logout');
    } catch (_) {}
    await _storage.deleteAll();
  }

  // ── Helpers ───────────────────────────────────────────────────────────────

  Future<void> _saveTokens(Map<String, dynamic> data) async {
    await _storage.write(
        key: AppConstants.tokenKey, value: data['access_token'] as String);
    await _storage.write(
        key: AppConstants.refreshKey, value: data['refresh_token'] as String);
    if (data['user'] != null) {
      await _storage.write(
          key: AppConstants.userKey,
          value: jsonEncode(data['user'] as Map<String, dynamic>));
    }
  }
}