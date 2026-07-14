import 'package:flutter/material.dart';

class AppColors {
  AppColors._();

  // Brand
  static const primary     = Color(0xFF1565C0);  // Deep blue
  static const primaryDark = Color(0xFF0D47A1);
  static const secondary   = Color(0xFF00897B);  // Teal
  static const accent      = Color(0xFFFF6F00);  // Amber

  // Severity
  static const severityLow      = Color(0xFF4CAF50);
  static const severityMedium   = Color(0xFFFFC107);
  static const severityHigh     = Color(0xFFFF9800);
  static const severityCritical = Color(0xFFF44336);

  // Status
  static const statusSubmitted    = Color(0xFF9E9E9E);
  static const statusProcessing   = Color(0xFF2196F3);
  static const statusAssigned     = Color(0xFF9C27B0);
  static const statusInProgress   = Color(0xFFFF9800);
  static const statusResolved     = Color(0xFF4CAF50);
  static const statusVerified     = Color(0xFF00BCD4);
  static const statusClosed       = Color(0xFF607D8B);
  static const statusRejected     = Color(0xFFF44336);

  // Category
  static const pothole          = Color(0xFFBF360C);
  static const garbage          = Color(0xFF558B2F);
  static const waterLeakage     = Color(0xFF0277BD);
  static const openManhole      = Color(0xFF4A148C);
  static const brokenStreetlight= Color(0xFFF57F17);
  static const fallenTree       = Color(0xFF1B5E20);
  static const damagedRoadSign  = Color(0xFFB71C1C);
  static const illegalDumping   = Color(0xFF37474F);

  // Neutral
  static const background    = Color(0xFFF5F7FA);
  static const surface       = Color(0xFFFFFFFF);
  static const surfaceVariant= Color(0xFFEEF2F8);
  static const onSurface     = Color(0xFF1A1A2E);
  static const onSurfaceVar  = Color(0xFF64748B);
  static const divider       = Color(0xFFE2E8F0);

  // Dark mode
  static const backgroundDark    = Color(0xFF0F172A);
  static const surfaceDark       = Color(0xFF1E293B);
  static const surfaceVariantDark= Color(0xFF334155);
}

class AppTheme {
  AppTheme._();

  static ThemeData get light => _buildTheme(Brightness.light);
  static ThemeData get dark  => _buildTheme(Brightness.dark);

  static ThemeData _buildTheme(Brightness brightness) {
    final isDark = brightness == Brightness.dark;

    final colorScheme = ColorScheme.fromSeed(
      seedColor: AppColors.primary,
      brightness: brightness,
      primary:          AppColors.primary,
      secondary:        AppColors.secondary,
      tertiary:         AppColors.accent,
      background:       isDark ? AppColors.backgroundDark    : AppColors.background,
      surface:          isDark ? AppColors.surfaceDark       : AppColors.surface,
      surfaceVariant:   isDark ? AppColors.surfaceVariantDark: AppColors.surfaceVariant,
      onBackground:     isDark ? Colors.white                : AppColors.onSurface,
      onSurface:        isDark ? Colors.white                : AppColors.onSurface,
    );

    return ThemeData(
      useMaterial3:    true,
      colorScheme:     colorScheme,
      fontFamily:      'Poppins',

      // AppBar
      appBarTheme: AppBarTheme(
        elevation:           0,
        centerTitle:         true,
        backgroundColor:     isDark ? AppColors.surfaceDark : AppColors.surface,
        foregroundColor:     isDark ? Colors.white          : AppColors.onSurface,
        surfaceTintColor:    Colors.transparent,
        titleTextStyle: TextStyle(
          fontFamily:  'Poppins',
          fontSize:    18,
          fontWeight:  FontWeight.w600,
          color:       isDark ? Colors.white : AppColors.onSurface,
        ),
        iconTheme: IconThemeData(
          color: isDark ? Colors.white : AppColors.onSurface,
        ),
      ),

      // Cards
      cardTheme: CardThemeData(
        elevation:        0,
        shape:            RoundedRectangleBorder(borderRadius: BorderRadius.circular(16)),
        color:            isDark ? AppColors.surfaceDark : AppColors.surface,
        surfaceTintColor: Colors.transparent,
        margin:           const EdgeInsets.symmetric(horizontal: 16, vertical: 8),
      ),

      // Elevated Button
      elevatedButtonTheme: ElevatedButtonThemeData(
        style: ElevatedButton.styleFrom(
          backgroundColor:  AppColors.primary,
          foregroundColor:  Colors.white,
          minimumSize:      const Size(double.infinity, 52),
          shape:            RoundedRectangleBorder(borderRadius: BorderRadius.circular(14)),
          elevation:        0,
          textStyle: const TextStyle(
            fontFamily:  'Poppins',
            fontSize:    16,
            fontWeight:  FontWeight.w600,
            letterSpacing: 0.5,
          ),
        ),
      ),

      // Outlined Button
      outlinedButtonTheme: OutlinedButtonThemeData(
        style: OutlinedButton.styleFrom(
          foregroundColor: AppColors.primary,
          minimumSize:     const Size(double.infinity, 52),
          shape:           RoundedRectangleBorder(borderRadius: BorderRadius.circular(14)),
          side: const BorderSide(color: AppColors.primary, width: 1.5),
          textStyle: const TextStyle(
            fontFamily: 'Poppins', fontSize: 16, fontWeight: FontWeight.w600,
          ),
        ),
      ),

      // Text Button
      textButtonTheme: TextButtonThemeData(
        style: TextButton.styleFrom(
          foregroundColor: AppColors.primary,
          textStyle: const TextStyle(
            fontFamily: 'Poppins', fontSize: 14, fontWeight: FontWeight.w600,
          ),
        ),
      ),

      // Input Decoration
      inputDecorationTheme: InputDecorationTheme(
        filled:              true,
        fillColor:           isDark ? AppColors.surfaceVariantDark : AppColors.surfaceVariant,
        border:              OutlineInputBorder(
          borderRadius: BorderRadius.circular(14),
          borderSide:   BorderSide.none,
        ),
        enabledBorder:       OutlineInputBorder(
          borderRadius: BorderRadius.circular(14),
          borderSide:   BorderSide.none,
        ),
        focusedBorder:       OutlineInputBorder(
          borderRadius: BorderRadius.circular(14),
          borderSide:   const BorderSide(color: AppColors.primary, width: 2),
        ),
        errorBorder:         OutlineInputBorder(
          borderRadius: BorderRadius.circular(14),
          borderSide:   const BorderSide(color: Colors.red, width: 1.5),
        ),
        contentPadding:      const EdgeInsets.symmetric(horizontal: 18, vertical: 16),
        hintStyle: TextStyle(
          color: isDark ? Colors.white38 : AppColors.onSurfaceVar,
          fontSize: 14,
        ),
        labelStyle: const TextStyle(
          fontFamily: 'Poppins', fontSize: 14, fontWeight: FontWeight.w500,
        ),
      ),

      // Bottom Nav Bar
      bottomNavigationBarTheme: BottomNavigationBarThemeData(
        type:             BottomNavigationBarType.fixed,
        backgroundColor: isDark ? AppColors.surfaceDark : AppColors.surface,
        selectedItemColor:   AppColors.primary,
        unselectedItemColor: AppColors.onSurfaceVar,
        elevation:           8,
        selectedLabelStyle:  const TextStyle(fontFamily: 'Poppins', fontSize: 12, fontWeight: FontWeight.w600),
        unselectedLabelStyle:const TextStyle(fontFamily: 'Poppins', fontSize: 12),
      ),

      // Floating Action Button
      floatingActionButtonTheme: const FloatingActionButtonThemeData(
        backgroundColor: AppColors.primary,
        foregroundColor: Colors.white,
        elevation:       4,
        shape:           CircleBorder(),
      ),

      // Chip
      chipTheme: ChipThemeData(
        backgroundColor:      isDark ? AppColors.surfaceVariantDark : AppColors.surfaceVariant,
        selectedColor:        AppColors.primary.withOpacity(0.15),
        labelStyle:           const TextStyle(fontFamily: 'Poppins', fontSize: 12, fontWeight: FontWeight.w500),
        shape:                RoundedRectangleBorder(borderRadius: BorderRadius.circular(8)),
        padding:              const EdgeInsets.symmetric(horizontal: 12, vertical: 4),
      ),

      // Divider
      dividerTheme: const DividerThemeData(
        color:   AppColors.divider,
        thickness: 1,
        space:   1,
      ),

      // Text Theme
      textTheme: const TextTheme(
        displayLarge:  TextStyle(fontFamily: 'Poppins', fontSize: 32, fontWeight: FontWeight.w700),
        displayMedium: TextStyle(fontFamily: 'Poppins', fontSize: 28, fontWeight: FontWeight.w700),
        headlineLarge: TextStyle(fontFamily: 'Poppins', fontSize: 24, fontWeight: FontWeight.w700),
        headlineMedium:TextStyle(fontFamily: 'Poppins', fontSize: 20, fontWeight: FontWeight.w600),
        headlineSmall: TextStyle(fontFamily: 'Poppins', fontSize: 18, fontWeight: FontWeight.w600),
        titleLarge:    TextStyle(fontFamily: 'Poppins', fontSize: 16, fontWeight: FontWeight.w600),
        titleMedium:   TextStyle(fontFamily: 'Poppins', fontSize: 14, fontWeight: FontWeight.w600),
        titleSmall:    TextStyle(fontFamily: 'Poppins', fontSize: 12, fontWeight: FontWeight.w600),
        bodyLarge:     TextStyle(fontFamily: 'Poppins', fontSize: 16, fontWeight: FontWeight.w400),
        bodyMedium:    TextStyle(fontFamily: 'Poppins', fontSize: 14, fontWeight: FontWeight.w400),
        bodySmall:     TextStyle(fontFamily: 'Poppins', fontSize: 12, fontWeight: FontWeight.w400),
        labelLarge:    TextStyle(fontFamily: 'Poppins', fontSize: 14, fontWeight: FontWeight.w500),
        labelSmall:    TextStyle(fontFamily: 'Poppins', fontSize: 11, fontWeight: FontWeight.w500),
      ),

      scaffoldBackgroundColor: isDark ? AppColors.backgroundDark : AppColors.background,
      visualDensity: VisualDensity.adaptivePlatformDensity,
    );
  }
}

// ─── Semantic color helpers ─────────────────────────────────────────────────

extension SeverityColor on String {
  Color get severityColor => switch (toLowerCase()) {
    'critical' => AppColors.severityCritical,
    'high'     => AppColors.severityHigh,
    'medium'   => AppColors.severityMedium,
    'low'      => AppColors.severityLow,
    _          => AppColors.severityMedium,
  };

  Color get statusColor => switch (toLowerCase()) {
    'submitted'      => AppColors.statusSubmitted,
    'ai_processing'  => AppColors.statusProcessing,
    'pending_review' => AppColors.statusProcessing,
    'assigned'       => AppColors.statusAssigned,
    'in_progress'    => AppColors.statusInProgress,
    'resolved'       => AppColors.statusResolved,
    'verified'       => AppColors.statusVerified,
    'closed'         => AppColors.statusClosed,
    'rejected'       => AppColors.statusRejected,
    _                => AppColors.statusSubmitted,
  };

  Color get categoryColor => switch (toLowerCase()) {
    'pothole'           => AppColors.pothole,
    'garbage'           => AppColors.garbage,
    'water_leakage'     => AppColors.waterLeakage,
    'open_manhole'      => AppColors.openManhole,
    'broken_streetlight'=> AppColors.brokenStreetlight,
    'fallen_tree'       => AppColors.fallenTree,
    'damaged_road_sign' => AppColors.damagedRoadSign,
    'illegal_dumping'   => AppColors.illegalDumping,
    _                   => AppColors.primary,
  };

  String get displayStatus => switch (toLowerCase()) {
    'submitted'      => 'Submitted',
    'ai_processing'  => 'AI Processing',
    'pending_review' => 'Pending Review',
    'assigned'       => 'Assigned',
    'in_progress'    => 'In Progress',
    'resolved'       => 'Resolved',
    'verified'       => 'Verified',
    'closed'         => 'Closed',
    'rejected'       => 'Rejected',
    _                => 'Unknown',
  };

  String get displayCategory => switch (toLowerCase()) {
    'pothole'           => 'Pothole',
    'garbage'           => 'Garbage Dump',
    'water_leakage'     => 'Water Leakage',
    'open_manhole'      => 'Open Manhole',
    'broken_streetlight'=> 'Broken Streetlight',
    'fallen_tree'       => 'Fallen Tree',
    'damaged_road_sign' => 'Damaged Road Sign',
    'illegal_dumping'   => 'Illegal Dumping',
    'other'             => 'Other',
    _                   => 'Unknown',
  };

  String get categoryEmoji => switch (toLowerCase()) {
    'pothole'           => '🕳️',
    'garbage'           => '🗑️',
    'water_leakage'     => '💧',
    'open_manhole'      => '🔓',
    'broken_streetlight'=> '💡',
    'fallen_tree'       => '🌳',
    'damaged_road_sign' => '🚧',
    'illegal_dumping'   => '⚠️',
    _                   => '📍',
  };
}
