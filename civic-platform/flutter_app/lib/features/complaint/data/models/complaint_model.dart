class ComplaintImageModel {
  final String id;
  final String? cdnUrl;
  final String? thumbnailUrl;
  final bool isPrimary;

  const ComplaintImageModel({
    required this.id,
    this.cdnUrl,
    this.thumbnailUrl,
    this.isPrimary = false,
  });

  factory ComplaintImageModel.fromJson(Map<String, dynamic> j) =>
      ComplaintImageModel(
        id:           j['id'] as String,
        cdnUrl:       j['cdn_url'] as String?,
        thumbnailUrl: j['thumbnail_url'] as String?,
        isPrimary:    j['is_primary'] as bool? ?? false,
      );
}

class StatusHistoryModel {
  final String toStatus;
  final String? notes;
  final DateTime createdAt;

  const StatusHistoryModel({
    required this.toStatus,
    this.notes,
    required this.createdAt,
  });

  factory StatusHistoryModel.fromJson(Map<String, dynamic> j) =>
      StatusHistoryModel(
        toStatus:  j['to_status'] as String,
        notes:     j['notes'] as String?,
        createdAt: DateTime.parse(j['created_at'] as String),
      );
}

class ComplaintModel {
  final String id;
  final String complaintNumber;
  final String title;
  final String description;
  final String category;
  final String severity;
  final String status;
  final double latitude;
  final double longitude;
  final String? address;
  final int supportCount;
  final bool isSupported;
  final bool isSupporting;
  final bool? citizenVerified;
  final String? aiDescription;
  final double? aiConfidence;
  final List<ComplaintImageModel> images;
  final List<StatusHistoryModel> statusHistory;
  final DateTime createdAt;
  final DateTime? resolvedAt;

  const ComplaintModel({
    required this.id,
    required this.complaintNumber,
    required this.title,
    required this.description,
    required this.category,
    required this.severity,
    required this.status,
    required this.latitude,
    required this.longitude,
    this.address,
    this.supportCount = 0,
    this.isSupported = false,
    this.isSupporting = false,
    this.citizenVerified,
    this.aiDescription,
    this.aiConfidence,
    this.images = const [],
    this.statusHistory = const [],
    required this.createdAt,
    this.resolvedAt,
  });

  factory ComplaintModel.fromJson(Map<String, dynamic> j) => ComplaintModel(
      id: j['id'] as String,
      complaintNumber: j['complaint_number'] as String,
      title: j['title'] as String,

      description: j['description']?.toString() ?? '',

      category: j['category']?.toString() ?? 'other',
      severity: j['severity']?.toString() ?? 'medium',
      status: j['status']?.toString() ?? 'submitted',

      latitude: (j['latitude'] as num?)?.toDouble() ?? 0.0,
      longitude: (j['longitude'] as num?)?.toDouble() ?? 0.0,

      address: j['address']?.toString(),

      supportCount: (j['support_count'] as num?)?.toInt() ?? 0,

      isSupported: j['is_supported'] as bool? ?? false,
      isSupporting: j['is_supporting'] as bool? ?? false,
      citizenVerified: j['citizen_verified'] as bool?,

      aiDescription: j['ai_description']?.toString(),
      aiConfidence: (j['ai_confidence'] as num?)?.toDouble(),

      images: (j['images'] as List<dynamic>? ?? [])
          .map((e) => ComplaintImageModel.fromJson(e))
          .toList(),

      statusHistory: (j['status_history'] as List<dynamic>? ?? [])
          .map((e) => StatusHistoryModel.fromJson(e))
          .toList(),

      createdAt: DateTime.parse(j['created_at']),

      resolvedAt: j['resolved_at'] != null
          ? DateTime.parse(j['resolved_at'])
          : null,
    );
}