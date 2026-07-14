class UserModel {
  final String id;
  final String email;
  final String fullName;
  final String? phone;
  final String role;
  final String status;
  final int totalComplaints;
  final int resolvedComplaints;
  final double? reputationScore;
  final String? avatarUrl;
  final bool emailVerified;

  const UserModel({
    required this.id,
    required this.email,
    required this.fullName,
    this.phone,
    required this.role,
    required this.status,
    this.totalComplaints = 0,
    this.resolvedComplaints = 0,
    this.reputationScore,
    this.avatarUrl,
    this.emailVerified = false,
  });

  factory UserModel.fromJson(Map<String, dynamic> json) => UserModel(
        id:                json['id'] as String,
        email:             json['email'] as String,
        fullName:          json['full_name'] as String,
        phone:             json['phone'] as String?,
        role:              json['role'] as String,
        status:            json['status'] as String,
        totalComplaints:   (json['total_complaints'] as num?)?.toInt() ?? 0,
        resolvedComplaints:(json['resolved_complaints'] as num?)?.toInt() ?? 0,
        reputationScore:   (json['reputation_score'] as num?)?.toDouble(),
        avatarUrl:         json['avatar_url'] as String?,
        emailVerified:     json['email_verified'] as bool? ?? false,
      );

  Map<String, dynamic> toJson() => {
        'id':                 id,
        'email':              email,
        'full_name':          fullName,
        'phone':              phone,
        'role':               role,
        'status':             status,
        'total_complaints':   totalComplaints,
        'resolved_complaints':resolvedComplaints,
        'reputation_score':   reputationScore,
        'avatar_url':         avatarUrl,
        'email_verified':     emailVerified,
      };

  UserModel copyWith({
    String? id, String? email, String? fullName, String? phone,
    String? role, String? status, int? totalComplaints, int? resolvedComplaints,
    double? reputationScore, String? avatarUrl, bool? emailVerified,
  }) =>
      UserModel(
        id:                id                ?? this.id,
        email:             email             ?? this.email,
        fullName:          fullName          ?? this.fullName,
        phone:             phone             ?? this.phone,
        role:              role              ?? this.role,
        status:            status            ?? this.status,
        totalComplaints:   totalComplaints   ?? this.totalComplaints,
        resolvedComplaints:resolvedComplaints?? this.resolvedComplaints,
        reputationScore:   reputationScore   ?? this.reputationScore,
        avatarUrl:         avatarUrl         ?? this.avatarUrl,
        emailVerified:     emailVerified     ?? this.emailVerified,
      );
}