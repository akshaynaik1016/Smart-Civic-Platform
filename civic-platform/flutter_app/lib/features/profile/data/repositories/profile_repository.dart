import 'dart:io';

import 'package:dio/dio.dart';

import '../../../../core/network/api_client.dart';
import '../../../auth/data/models/user_model.dart';

class ProfileRepository {
  final _client = ApiClient.instance.client;

  Future<UserModel> updateProfile({String? fullName, String? phone}) async {
    try {
      final data = <String, dynamic>{
        if (fullName != null) 'full_name': fullName,
        if (phone    != null) 'phone':     phone,
      };
      final res = await _client.patch('/users/me', data: data);
      return UserModel.fromJson(res.data as Map<String, dynamic>);
    } catch (e) {
      throw Exception(dioErrorMessage(e));
    }
  }

  Future<UserModel> uploadAvatar(String imagePath) async {
    try {
      final formData = FormData.fromMap({
        'image': await MultipartFile.fromFile(imagePath, filename: 'avatar.jpg'),
      });
      final res = await _client.post(
        '/users/me/avatar',
        data: formData,
        options: Options(contentType: 'multipart/form-data'),
      );
      // Re-fetch current user to get updated avatar_url
      final meRes = await _client.get('/users/me');
      return UserModel.fromJson(meRes.data as Map<String, dynamic>);
    } catch (e) {
      throw Exception(dioErrorMessage(e));
    }
  }

  Future<Map<String, dynamic>> getActivitySummary() async {
    try {
      final res = await _client.get('/users/me/activity');
      return res.data as Map<String, dynamic>;
    } catch (e) {
      throw Exception(dioErrorMessage(e));
    }
  }
}