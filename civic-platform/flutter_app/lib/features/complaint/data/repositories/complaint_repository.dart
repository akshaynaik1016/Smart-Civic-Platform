import 'package:dio/dio.dart';

import '../../../../core/network/api_client.dart';
import '../models/complaint_model.dart';

class ComplaintRepository {
  final _client = ApiClient.instance.client;

  // ── List my complaints ────────────────────────────────────────────────────

  Future<List<ComplaintModel>> fetchComplaints({
    String? status,
    String? category,
    String? search,
    int page = 1,
    int pageSize = 20,
  }) async {
    try {
      final params = <String, dynamic>{
        'page': page, 'page_size': pageSize,
        if (status   != null) 'status':   status,
        if (category != null) 'category': category,
        if (search   != null) 'search':   search,
      };
      final res = await _client.get('/complaints', queryParameters: params);
      final items = res.data['items'] as List<dynamic>? ?? [];
      return items
          .map((e) => ComplaintModel.fromJson(e as Map<String, dynamic>))
          .toList();
          } catch (e, stack) {
        print("REPOSITORY ERROR:");
        print(e);
        print(stack);

        throw Exception(dioErrorMessage(e));
      }
  }

  // ── Get detail ────────────────────────────────────────────────────────────

  Future<ComplaintModel> fetchDetail(String id) async {
    try {
      final res = await _client.get('/complaints/$id');
      return ComplaintModel.fromJson(res.data as Map<String, dynamic>);
    } catch (e) {
      throw Exception(dioErrorMessage(e));
    }
  }

  // ── Nearby ────────────────────────────────────────────────────────────────

  Future<List<ComplaintModel>> fetchNearby({
    required double lat, required double lng, double radiusKm = 5,
  }) async {
    try {
      final res = await _client.get('/complaints/nearby', queryParameters: {
        'lat': lat, 'lng': lng, 'radius_km': radiusKm,
      });
      final items = res.data as List<dynamic>? ?? [];
      return items
          .map((e) => ComplaintModel.fromJson(e as Map<String, dynamic>))
          .toList();
    } catch (e) {
      throw Exception(dioErrorMessage(e));
    }
  }

  // ── Submit ────────────────────────────────────────────────────────────────

  Future<ComplaintModel> submit({
    required String imagePath,
    required String title,
    required String description,
    required String category,
    required String severity,
    required double latitude,
    required double longitude,
    required String address,
    double aiConfidence = 0,
    List<dynamic> boundingBoxes = const [],
  }) async {
    try {
      // 1. Create the complaint
      final res = await _client.post('/complaints', data: {
        'title':       title,
        'description': description,
        'category':    category,
        'severity':    severity,
        'latitude':    latitude,
        'longitude':   longitude,
        'address':     address,
      });
      final complaint = ComplaintModel.fromJson(res.data as Map<String, dynamic>);

      // 2. Upload image
      final formData = FormData.fromMap({
        'files': await MultipartFile.fromFile(imagePath, filename: 'image.jpg'),
      });
      await _client.post(
        '/complaints/${complaint.id}/images',
        data: formData,
        options: Options(contentType: 'multipart/form-data'),
      );

      return complaint;
    } catch (e) {
      throw Exception(dioErrorMessage(e));
    }
  }

  // ── Support toggle ────────────────────────────────────────────────────────

  Future<void> toggleSupport(String id, {required bool currentlySupporting}) async {
    try {
      if (currentlySupporting) {
        await _client.delete('/complaints/$id/support');
      } else {
        await _client.post('/complaints/$id/support');
      }
    } catch (e) {
      throw Exception(dioErrorMessage(e));
    }
  }

  // ── Verify resolution ─────────────────────────────────────────────────────

  Future<ComplaintModel> verifyResolution({
    required String id, required bool isResolved,
  }) async {
    try {
      final res = await _client.post('/complaints/$id/verify', data: {
        'is_resolved': isResolved,
      });
      return ComplaintModel.fromJson(res.data as Map<String, dynamic>);
    } catch (e) {
      throw Exception(dioErrorMessage(e));
    }
  }
}