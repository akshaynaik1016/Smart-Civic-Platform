import 'package:flutter/material.dart';
import 'package:shimmer/shimmer.dart';

import '../../core/theme/app_theme.dart';

class ShimmerComplaintCard extends StatelessWidget {
  const ShimmerComplaintCard({super.key});

  @override
  Widget build(BuildContext context) {
    final isDark = Theme.of(context).brightness == Brightness.dark;
    final baseColor  = isDark ? const Color(0xFF1E293B) : const Color(0xFFEEF2F8);
    final highlight  = isDark ? const Color(0xFF334155) : const Color(0xFFF8FAFC);

    return Shimmer.fromColors(
      baseColor:      baseColor,
      highlightColor: highlight,
      child: Card(
        margin: const EdgeInsets.symmetric(horizontal: 16, vertical: 8),
        child: Padding(
          padding: const EdgeInsets.all(16),
          child: Column(
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              // Top row: category chip + severity badge
              Row(
                children: [
                  _ShimmerBox(width: 110, height: 24, radius: 8),
                  const Spacer(),
                  _ShimmerBox(width: 70,  height: 24, radius: 20),
                ],
              ),
              const SizedBox(height: 12),
              // Title
              _ShimmerBox(width: double.infinity, height: 16, radius: 6),
              const SizedBox(height: 6),
              _ShimmerBox(width: 200, height: 16, radius: 6),
              const SizedBox(height: 8),
              // Address
              _ShimmerBox(width: 160, height: 12, radius: 4),
              const SizedBox(height: 14),
              // Bottom row
              Row(
                children: [
                  _ShimmerBox(width: 90,  height: 22, radius: 20),
                  const Spacer(),
                  _ShimmerBox(width: 60,  height: 12, radius: 4),
                ],
              ),
            ],
          ),
        ),
      ),
    );
  }
}

class _ShimmerBox extends StatelessWidget {
  final double width;
  final double height;
  final double radius;

  const _ShimmerBox({
    required this.width,
    required this.height,
    this.radius = 4,
  });

  @override
  Widget build(BuildContext context) {
    return Container(
      width:  width,
      height: height,
      decoration: BoxDecoration(
        color:        AppColors.surfaceVariant,
        borderRadius: BorderRadius.circular(radius),
      ),
    );
  }
}