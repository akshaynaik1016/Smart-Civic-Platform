import 'package:dio/dio.dart';

import '../network/api_client.dart';

/// AI detection service.
///
/// Calls the backend's POST /ai/analyze endpoint. On any failure (model not
/// loaded yet, network error, server cold-start) it returns a safe fallback
/// result so the citizen can still submit the complaint with manual
/// classification — the same graceful-degradation behaviour the backend
/// itself implements when no YOLOv8 weights file is present.
class AiService {
  AiService._();
  static final AiService instance = AiService._();

  final _client = ApiClient.instance.client;

  /// Sends [imagePath] to the backend AI endpoint and returns the analysis
  /// result as a plain map containing at minimum:
  ///   - `category`       (String)
  ///   - `confidence`     (double, 0–1)
  ///   - `severity`       (String: low | medium | high | critical)
  ///   - `description`    (String)
  ///   - `bounding_boxes` (List)
  ///   - `ai_available`   (bool)
  Future<Map<String, dynamic>> analyzeImage(String imagePath) async {
    try {
      final formData = FormData.fromMap({
        'image':    await MultipartFile.fromFile(imagePath, filename: 'capture.jpg'),
        'latitude': 0.0,
        'longitude': 0.0,
      });

      final response = await _client.post(
        '/ai/analyze',
        data: formData,
        options: Options(
          contentType:     'multipart/form-data',
          receiveTimeout:  const Duration(seconds: 45),
        ),
      );

      final data = response.data as Map<String, dynamic>;
      return {
        'category':      data['category']       ?? 'other',
        'confidence':    (data['confidence'] as num?)?.toDouble() ?? 0.0,
        'severity':      data['severity']        ?? 'medium',
        'description':   data['description']     ?? '',
        'bounding_boxes':data['bounding_boxes']  ?? <dynamic>[],
        'ai_available':  data['ai_available']    ?? false,
      };
    } on DioException catch (e) {
      // 503 = model not loaded; any other network failure
      // Return a safe default so the submit flow can continue
      return _fallbackResult();
    } catch (_) {
      return _fallbackResult();
    }
  }

  Map<String, dynamic> _fallbackResult() => {
        'category':       'other',
        'confidence':     0.0,
        'severity':       'medium',
        'description':    '',
        'bounding_boxes': <dynamic>[],
        'ai_available':   false,
      };
}