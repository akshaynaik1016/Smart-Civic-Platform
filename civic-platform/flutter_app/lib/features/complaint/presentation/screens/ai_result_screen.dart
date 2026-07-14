import 'dart:io';
import 'package:flutter/material.dart';
import 'package:go_router/go_router.dart';

import '../../../../core/router/app_router.dart';
import '../../../../core/theme/app_theme.dart';
import '../../../../shared/widgets/severity_badge.dart';

class AiResultScreen extends StatefulWidget {
  final String imagePath;
  final Map<String, dynamic>? analysisResult;

  const AiResultScreen({
    super.key,
    required this.imagePath,
    required this.analysisResult,
  });

  @override
  State<AiResultScreen> createState() => _AiResultScreenState();
}

class _AiResultScreenState extends State<AiResultScreen>
    with SingleTickerProviderStateMixin {
  late AnimationController _animCtrl;
  late Animation<double>    _slideAnim;

  @override
  void initState() {
    super.initState();
    _animCtrl = AnimationController(
        vsync: this, duration: const Duration(milliseconds: 500));
    _slideAnim = Tween<double>(begin: 60, end: 0).animate(
        CurvedAnimation(parent: _animCtrl, curve: Curves.easeOut));
    _animCtrl.forward();
  }

  @override
  void dispose() {
    _animCtrl.dispose();
    super.dispose();
  }

  Map<String, dynamic> get _result =>
      widget.analysisResult ?? {'category': 'other', 'confidence': 0.0, 'severity': 'medium'};

  bool get _hasDetection => widget.analysisResult != null;

  @override
  Widget build(BuildContext context) {
    final category  = _result['category'] as String? ?? 'other';
    final confidence= (_result['confidence'] as num?)?.toDouble() ?? 0.0;
    final severity  = _result['severity']  as String? ?? 'medium';
    final desc      = _result['description'] as String? ?? '';
    final bboxes    = _result['bounding_boxes'] as List<dynamic>? ?? [];

    return Scaffold(
      body: Stack(
        children: [
          // ── Full image background ────────────────────────────────────
          Positioned.fill(
            child: Image.file(
              File(widget.imagePath),
              fit: BoxFit.cover,
            ),
          ),

          // ── Bounding Box overlay ─────────────────────────────────────
          if (bboxes.isNotEmpty)
            Positioned.fill(
              child: CustomPaint(
                painter: _BBoxPainter(bboxes: bboxes, category: category),
              ),
            ),

          // ── Gradient for readability ─────────────────────────────────
          Positioned(
            left: 0, right: 0, bottom: 0,
            height: MediaQuery.of(context).size.height * 0.6,
            child: Container(
              decoration: const BoxDecoration(
                gradient: LinearGradient(
                  begin: Alignment.bottomCenter,
                  end: Alignment.topCenter,
                  colors: [Colors.black87, Colors.black45, Colors.transparent],
                ),
              ),
            ),
          ),

          // ── Top back / retake bar ────────────────────────────────────
          SafeArea(
            child: Padding(
              padding: const EdgeInsets.symmetric(horizontal: 16, vertical: 8),
              child: Row(children: [
                _GlassButton(
                  icon: Icons.arrow_back_rounded,
                  onTap: () => context.pop(),
                ),
                const Spacer(),
                _GlassButton(
                  icon: Icons.camera_alt_rounded,
                  onTap: () {
                    context.pop();
                    context.push(AppRoutes.camera);
                  },
                ),
              ]),
            ),
          ),

          // ── Bottom Result Sheet ──────────────────────────────────────
          AnimatedBuilder(
            animation: _slideAnim,
            builder: (_, child) => Positioned(
              left: 0, right: 0,
              bottom: _slideAnim.value - 60,
              child: child!,
            ),
            child: SafeArea(
              top: false,
              child: Padding(
                padding: const EdgeInsets.all(16),
                child: Column(
                  crossAxisAlignment: CrossAxisAlignment.start,
                  mainAxisSize: MainAxisSize.min,
                  children: [

                    // AI detection badge
                    if (_hasDetection)
                      Container(
                        padding: const EdgeInsets.symmetric(horizontal: 12, vertical: 6),
                        decoration: BoxDecoration(
                          color: Colors.green.shade700,
                          borderRadius: BorderRadius.circular(20),
                        ),
                        child: Row(mainAxisSize: MainAxisSize.min, children: [
                          const Icon(Icons.auto_awesome, color: Colors.white, size: 14),
                          const SizedBox(width: 6),
                          Text(
                            'AI Detected (${(confidence * 100).toStringAsFixed(0)}% confidence)',
                            style: const TextStyle(color: Colors.white, fontSize: 12, fontWeight: FontWeight.w600),
                          ),
                        ]),
                      )
                    else
                      Container(
                        padding: const EdgeInsets.symmetric(horizontal: 12, vertical: 6),
                        decoration: BoxDecoration(
                          color: Colors.orange.shade800,
                          borderRadius: BorderRadius.circular(20),
                        ),
                        child: const Row(mainAxisSize: MainAxisSize.min, children: [
                          Icon(Icons.warning_amber_rounded, color: Colors.white, size: 14),
                          SizedBox(width: 6),
                          Text('Manual Classification', style: TextStyle(color: Colors.white, fontSize: 12, fontWeight: FontWeight.w600)),
                        ]),
                      ),
                    const SizedBox(height: 12),

                    // Category + severity row
                    Row(children: [
                      Expanded(
                        child: Text(
                          category.displayCategory,
                          style: const TextStyle(
                            color: Colors.white, fontSize: 26, fontWeight: FontWeight.w700,
                          ),
                        ),
                      ),
                      SeverityBadge(severity: severity),
                    ]),
                    const SizedBox(height: 8),

                    // Category emoji + color dot
                    Row(children: [
                      Container(
                        width: 10, height: 10,
                        decoration: BoxDecoration(
                          shape: BoxShape.circle,
                          color: category.categoryColor,
                        ),
                      ),
                      const SizedBox(width: 8),
                      Text(
                        '${category.categoryEmoji}  ${category.categoryColor.toString()}',
                        style: const TextStyle(color: Colors.white70, fontSize: 13),
                      ),
                    ]),
                    const SizedBox(height: 16),

                    // AI description
                    if (desc.isNotEmpty)
                      Container(
                        padding: const EdgeInsets.all(14),
                        decoration: BoxDecoration(
                          color: Colors.white12,
                          borderRadius: BorderRadius.circular(14),
                          border: Border.all(color: Colors.white24),
                        ),
                        child: Row(
                          crossAxisAlignment: CrossAxisAlignment.start,
                          children: [
                            const Icon(Icons.format_quote_rounded,
                                color: Colors.white54, size: 18),
                            const SizedBox(width: 8),
                            Expanded(
                              child: Text(
                                desc,
                                style: const TextStyle(
                                  color: Colors.white, fontSize: 13, height: 1.6,
                                ),
                              ),
                            ),
                          ],
                        ),
                      ),
                    const SizedBox(height: 20),

                    // Action buttons
                    Row(children: [
                      Expanded(
                        child: OutlinedButton.icon(
                          style: OutlinedButton.styleFrom(
                            foregroundColor: Colors.white,
                            side: const BorderSide(color: Colors.white54),
                            minimumSize: const Size(0, 50),
                            shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(14)),
                          ),
                          onPressed: () => _showCategoryPicker(context, category),
                          icon: const Icon(Icons.edit_rounded, size: 18),
                          label: const Text('Change'),
                        ),
                      ),
                      const SizedBox(width: 12),
                      Expanded(
                        flex: 2,
                        child: ElevatedButton.icon(
                          style: ElevatedButton.styleFrom(
                            backgroundColor: AppColors.primary,
                            minimumSize: const Size(0, 50),
                            shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(14)),
                          ),
                          onPressed: () => context.push(AppRoutes.submitComplaint, extra: {
                            'imagePath': widget.imagePath,
                            'category':  category,
                            'severity':  severity,
                            'description': desc,
                            'confidence': confidence,
                            'bounding_boxes': bboxes,
                          }),
                          icon: const Icon(Icons.send_rounded, size: 18),
                          label: const Text('Submit Report'),
                        ),
                      ),
                    ]),
                    const SizedBox(height: 8),
                  ],
                ),
              ),
            ),
          ),
        ],
      ),
    );
  }

  void _showCategoryPicker(BuildContext context, String current) {
    const categories = [
      'pothole', 'garbage', 'water_leakage', 'open_manhole',
      'broken_streetlight', 'fallen_tree', 'damaged_road_sign', 'illegal_dumping', 'other',
    ];
    showModalBottomSheet(
      context: context,
      shape: const RoundedRectangleBorder(
          borderRadius: BorderRadius.vertical(top: Radius.circular(20))),
      builder: (_) => Padding(
        padding: const EdgeInsets.symmetric(vertical: 16),
        child: Column(
          mainAxisSize: MainAxisSize.min,
          children: [
            Container(width: 40, height: 4, decoration: BoxDecoration(
                color: AppColors.divider, borderRadius: BorderRadius.circular(2))),
            const SizedBox(height: 16),
            const Text('Select Issue Category',
                style: TextStyle(fontSize: 16, fontWeight: FontWeight.w700)),
            const SizedBox(height: 8),
            ...categories.map((cat) => ListTile(
              leading: Text(cat.categoryEmoji, style: const TextStyle(fontSize: 20)),
              title: Text(cat.displayCategory),
              trailing: cat == current
                  ? const Icon(Icons.check_circle_rounded, color: AppColors.primary)
                  : null,
              onTap: () {
                // Update state and pop
                Navigator.pop(context);
                // In a real app, call setState or BLoC event
              },
            )),
          ],
        ),
      ),
    );
  }
}

// ─── Bounding box painter ─────────────────────────────────────────────────────

class _BBoxPainter extends CustomPainter {
  final List<dynamic> bboxes;
  final String category;
  const _BBoxPainter({required this.bboxes, required this.category});

  @override
  void paint(Canvas canvas, Size size) {
    final paint = Paint()
      ..color = category.categoryColor
      ..style = PaintingStyle.stroke
      ..strokeWidth = 3;

    for (final bbox in bboxes) {
      if (bbox is List && bbox.length >= 4) {
        final x1 = (bbox[0] as num).toDouble() * size.width;
        final y1 = (bbox[1] as num).toDouble() * size.height;
        final x2 = (bbox[2] as num).toDouble() * size.width;
        final y2 = (bbox[3] as num).toDouble() * size.height;
        final rect = Rect.fromLTRB(x1, y1, x2, y2);
        canvas.drawRRect(RRect.fromRectAndRadius(rect, const Radius.circular(4)), paint);

        // Label
        final tp = TextPainter(
          text: TextSpan(
            text: ' ${category.displayCategory} ',
            style: TextStyle(
              color: Colors.white,
              fontSize: 12,
              fontWeight: FontWeight.w700,
              background: Paint()..color = category.categoryColor,
            ),
          ),
          textDirection: TextDirection.ltr,
        )..layout();
        tp.paint(canvas, Offset(x1, y1 - 20));
      }
    }
  }

  @override
  bool shouldRepaint(covariant CustomPainter oldDelegate) => false;
}

class _GlassButton extends StatelessWidget {
  final IconData icon;
  final VoidCallback onTap;
  const _GlassButton({required this.icon, required this.onTap});

  @override
  Widget build(BuildContext context) => GestureDetector(
    onTap: onTap,
    child: Container(
      width: 44, height: 44,
      decoration: BoxDecoration(
        color: Colors.white24,
        shape: BoxShape.circle,
        border: Border.all(color: Colors.white38),
      ),
      child: Icon(icon, color: Colors.white, size: 22),
    ),
  );
}
