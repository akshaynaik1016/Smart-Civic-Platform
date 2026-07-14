class NotificationModel {
  final String id;
  final String type;
  final String title;
  final String body;
  final String? complaintId;
  final bool isRead;
  final DateTime createdAt;

  const NotificationModel({
    required this.id,
    required this.type,
    required this.title,
    required this.body,
    this.complaintId,
    this.isRead = false,
    required this.createdAt,
  });

  factory NotificationModel.fromJson(Map<String, dynamic> j) =>
      NotificationModel(
        id:          j['id'] as String,
        type:        j['type'] as String,
        title:       j['title'] as String,
        body:        j['body'] as String,
        complaintId: j['complaint_id'] as String?,
        isRead:      j['read_at'] != null,
        createdAt:   DateTime.parse(j['created_at'] as String),
      );
}