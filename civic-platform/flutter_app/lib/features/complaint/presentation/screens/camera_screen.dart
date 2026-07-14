import 'dart:io';
import 'package:camera/camera.dart';
import 'package:flutter/material.dart';
import 'package:geolocator/geolocator.dart';
import 'package:go_router/go_router.dart';
import 'package:image_picker/image_picker.dart';
import 'package:permission_handler/permission_handler.dart';

import '../../../../core/router/app_router.dart';
import '../../../../core/theme/app_theme.dart';
import '../../../../core/services/ai_service.dart';

class CameraScreen extends StatefulWidget {
  const CameraScreen({super.key});

  @override
  State<CameraScreen> createState() => _CameraScreenState();
}

class _CameraScreenState extends State<CameraScreen>
    with WidgetsBindingObserver {
  CameraController? _controller;
  List<CameraDescription> _cameras = [];
  int _selectedCamera = 0;
  FlashMode _flashMode = FlashMode.auto;
  bool _isTakingPhoto = false;
  bool _isInitialised = false;
  Position? _currentPosition;

  @override
  void initState() {
    super.initState();
    WidgetsBinding.instance.addObserver(this);
    _initCamera();
    _fetchLocation();
  }

  @override
  void dispose() {
    WidgetsBinding.instance.removeObserver(this);
    _controller?.dispose();
    super.dispose();
  }

  @override
  void didChangeAppLifecycleState(AppLifecycleState state) {
    if (_controller == null || !_controller!.value.isInitialized) return;
    if (state == AppLifecycleState.inactive) {
      _controller!.dispose();
    } else if (state == AppLifecycleState.resumed) {
      _initCamera();
    }
  }

  Future<void> _initCamera() async {
    final status = await Permission.camera.request();
    if (!status.isGranted) {
      if (mounted) context.pop();
      return;
    }
    _cameras = await availableCameras();
    if (_cameras.isEmpty) {
      if (mounted) context.pop();
      return;
    }
    await _startCamera(_cameras[_selectedCamera]);
  }

  Future<void> _startCamera(CameraDescription desc) async {
    await _controller?.dispose();
    _controller = CameraController(
      desc,
      ResolutionPreset.high,
      enableAudio: false,
      imageFormatGroup: ImageFormatGroup.jpeg,
    );
    try {
      await _controller!.initialize();
      await _controller!.setFlashMode(_flashMode);
      if (mounted) setState(() => _isInitialised = true);
    } catch (e) {
      debugPrint('Camera init error: $e');
    }
  }

  Future<void> _fetchLocation() async {
    final perm = await Geolocator.checkPermission();
    if (perm == LocationPermission.denied) {
      await Geolocator.requestPermission();
    }
    try {
      _currentPosition = await Geolocator.getCurrentPosition(
        desiredAccuracy: LocationAccuracy.high,
      );
    } catch (_) {}
  }

  Future<void> _capture() async {
    if (_controller == null || !_controller!.value.isInitialized || _isTakingPhoto) return;
    setState(() => _isTakingPhoto = true);

    try {
      final xFile = await _controller!.takePicture();
      await _processImage(xFile.path);
    } catch (e) {
      _showError('Failed to capture photo. Please try again.');
    } finally {
      if (mounted) setState(() => _isTakingPhoto = false);
    }
  }

  Future<void> _pickFromGallery() async {
    final picker = ImagePicker();
    final xFile = await picker.pickImage(
      source: ImageSource.gallery,
      imageQuality: 90,
    );
    if (xFile != null) await _processImage(xFile.path);
  }

  Future<void> _processImage(String imagePath) async {
    if (!mounted) return;

    // Show processing overlay
    showDialog(
      context: context,
      barrierDismissible: false,
      builder: (_) => const _ProcessingDialog(),
    );

    try {
      // Call AI service
      final result = await AiService.instance.analyzeImage(imagePath);

      if (mounted) {
        Navigator.of(context).pop(); // close dialog
        context.push(AppRoutes.aiResult, extra: {
          'imagePath': imagePath,
          'analysis': result,
          'latitude':  _currentPosition?.latitude,
          'longitude': _currentPosition?.longitude,
        });
      }
    } catch (e) {
      if (mounted) {
        Navigator.of(context).pop();
        // Even on AI failure, allow manual submission
        context.push(AppRoutes.aiResult, extra: {
          'imagePath': imagePath,
          'analysis': null,
          'latitude':  _currentPosition?.latitude,
          'longitude': _currentPosition?.longitude,
        });
      }
    }
  }

  void _toggleFlash() {
    final modes = [FlashMode.auto, FlashMode.always, FlashMode.off];
    final idx = modes.indexOf(_flashMode);
    final next = modes[(idx + 1) % modes.length];
    setState(() => _flashMode = next);
    _controller?.setFlashMode(next);
  }

  void _flipCamera() {
    if (_cameras.length < 2) return;
    _selectedCamera = (_selectedCamera + 1) % _cameras.length;
    _startCamera(_cameras[_selectedCamera]);
  }

  void _showError(String msg) {
    ScaffoldMessenger.of(context).showSnackBar(
      SnackBar(content: Text(msg), backgroundColor: Colors.red.shade700),
    );
  }

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      backgroundColor: Colors.black,
      body: SafeArea(
        child: Stack(
          fit: StackFit.expand,
          children: [
            // ── Camera Preview ───────────────────────────────────────────
            if (_isInitialised && _controller != null)
              ClipRRect(
                borderRadius: BorderRadius.circular(0),
                child: CameraPreview(_controller!),
              )
            else
              const Center(child: CircularProgressIndicator(color: Colors.white)),

            // ── Guide Overlay ────────────────────────────────────────────
            CustomPaint(painter: _GuideOverlayPainter()),

            // ── Top Bar ──────────────────────────────────────────────────
            Positioned(
              top: 0, left: 0, right: 0,
              child: Container(
                padding: const EdgeInsets.symmetric(horizontal: 16, vertical: 12),
                decoration: const BoxDecoration(
                  gradient: LinearGradient(
                    begin: Alignment.topCenter, end: Alignment.bottomCenter,
                    colors: [Colors.black54, Colors.transparent],
                  ),
                ),
                child: Row(
                  mainAxisAlignment: MainAxisAlignment.spaceBetween,
                  children: [
                    IconButton(
                      icon: const Icon(Icons.close, color: Colors.white, size: 28),
                      onPressed: () => context.pop(),
                    ),
                    _FlashButton(mode: _flashMode, onTap: _toggleFlash),
                    IconButton(
                      icon: const Icon(Icons.flip_camera_ios_rounded, color: Colors.white, size: 28),
                      onPressed: _flipCamera,
                    ),
                  ],
                ),
              ),
            ),

            // ── GPS indicator ────────────────────────────────────────────
            Positioned(
              top: 70, left: 0, right: 0,
              child: Center(
                child: Container(
                  padding: const EdgeInsets.symmetric(horizontal: 12, vertical: 6),
                  decoration: BoxDecoration(
                    color: Colors.black45,
                    borderRadius: BorderRadius.circular(20),
                  ),
                  child: Row(
                    mainAxisSize: MainAxisSize.min,
                    children: [
                      Icon(
                        _currentPosition != null
                            ? Icons.gps_fixed_rounded
                            : Icons.gps_not_fixed_rounded,
                        color: _currentPosition != null ? Colors.greenAccent : Colors.orange,
                        size: 14,
                      ),
                      const SizedBox(width: 6),
                      Text(
                        _currentPosition != null
                            ? 'GPS: ${_currentPosition!.latitude.toStringAsFixed(4)}, '
                              '${_currentPosition!.longitude.toStringAsFixed(4)}'
                            : 'Acquiring GPS...',
                        style: const TextStyle(color: Colors.white, fontSize: 11),
                      ),
                    ],
                  ),
                ),
              ),
            ),

            // ── Hint text ────────────────────────────────────────────────
            Positioned(
              bottom: 140,
              left: 0, right: 0,
              child: Center(
                child: Container(
                  padding: const EdgeInsets.symmetric(horizontal: 16, vertical: 8),
                  decoration: BoxDecoration(
                    color: Colors.black45,
                    borderRadius: BorderRadius.circular(20),
                  ),
                  child: const Text(
                    'Point camera at the civic issue',
                    style: TextStyle(color: Colors.white70, fontSize: 13),
                  ),
                ),
              ),
            ),

            // ── Bottom Controls ──────────────────────────────────────────
            Positioned(
              bottom: 0, left: 0, right: 0,
              child: Container(
                height: 130,
                decoration: const BoxDecoration(
                  gradient: LinearGradient(
                    begin: Alignment.bottomCenter, end: Alignment.topCenter,
                    colors: [Colors.black87, Colors.transparent],
                  ),
                ),
                child: Row(
                  mainAxisAlignment: MainAxisAlignment.spaceEvenly,
                  children: [
                    // Gallery picker
                    GestureDetector(
                      onTap: _pickFromGallery,
                      child: Container(
                        width: 52, height: 52,
                        decoration: BoxDecoration(
                          color: Colors.white24,
                          borderRadius: BorderRadius.circular(14),
                          border: Border.all(color: Colors.white38),
                        ),
                        child: const Icon(Icons.photo_library_rounded, color: Colors.white, size: 26),
                      ),
                    ),

                    // Capture button
                    GestureDetector(
                      onTap: _capture,
                      child: AnimatedContainer(
                        duration: const Duration(milliseconds: 150),
                        width: _isTakingPhoto ? 70 : 76,
                        height: _isTakingPhoto ? 70 : 76,
                        decoration: BoxDecoration(
                          shape: BoxShape.circle,
                          color: Colors.white,
                          border: Border.all(color: Colors.white, width: 4),
                          boxShadow: [
                            BoxShadow(
                              color: Colors.white.withOpacity(0.4),
                              blurRadius: 12, spreadRadius: 2,
                            ),
                          ],
                        ),
                        child: _isTakingPhoto
                            ? const Padding(
                                padding: EdgeInsets.all(16),
                                child: CircularProgressIndicator(
                                    color: AppColors.primary, strokeWidth: 3),
                              )
                            : Container(
                                margin: const EdgeInsets.all(8),
                                decoration: BoxDecoration(
                                  shape: BoxShape.circle,
                                  color: AppColors.primary.withOpacity(0.15),
                                ),
                                child: const Icon(Icons.camera_alt_rounded,
                                    color: AppColors.primary, size: 32),
                              ),
                      ),
                    ),

                    // Settings / placeholder
                    Container(
                      width: 52, height: 52,
                      decoration: BoxDecoration(
                        color: Colors.white24,
                        borderRadius: BorderRadius.circular(14),
                        border: Border.all(color: Colors.white38),
                      ),
                      child: const Icon(Icons.settings_rounded, color: Colors.white, size: 26),
                    ),
                  ],
                ),
              ),
            ),
          ],
        ),
      ),
    );
  }
}

// ─── Guide Overlay Painter ────────────────────────────────────────────────────

class _GuideOverlayPainter extends CustomPainter {
  @override
  void paint(Canvas canvas, Size size) {
    final paint = Paint()
      ..color = Colors.white30
      ..style = PaintingStyle.stroke
      ..strokeWidth = 1.5;

    const margin = 60.0;
    const cornerSize = 24.0;

    final rect = Rect.fromLTWH(margin, size.height * 0.25,
        size.width - margin * 2, size.height * 0.5);

    // Corners only
    final path = Path()
      ..moveTo(rect.left, rect.top + cornerSize)
      ..lineTo(rect.left, rect.top)
      ..lineTo(rect.left + cornerSize, rect.top)
      ..moveTo(rect.right - cornerSize, rect.top)
      ..lineTo(rect.right, rect.top)
      ..lineTo(rect.right, rect.top + cornerSize)
      ..moveTo(rect.right, rect.bottom - cornerSize)
      ..lineTo(rect.right, rect.bottom)
      ..lineTo(rect.right - cornerSize, rect.bottom)
      ..moveTo(rect.left + cornerSize, rect.bottom)
      ..lineTo(rect.left, rect.bottom)
      ..lineTo(rect.left, rect.bottom - cornerSize);

    canvas.drawPath(path, paint..strokeWidth = 3..color = Colors.white70);
  }

  @override
  bool shouldRepaint(covariant CustomPainter oldDelegate) => false;
}

// ─── Flash Button ─────────────────────────────────────────────────────────────

class _FlashButton extends StatelessWidget {
  final FlashMode mode;
  final VoidCallback onTap;
  const _FlashButton({required this.mode, required this.onTap});

  @override
  Widget build(BuildContext context) {
    final icon = switch (mode) {
      FlashMode.auto   => Icons.flash_auto_rounded,
      FlashMode.always => Icons.flash_on_rounded,
      FlashMode.off    => Icons.flash_off_rounded,
      _                => Icons.flash_auto_rounded,
    };
    return IconButton(icon: Icon(icon, color: Colors.white, size: 28), onPressed: onTap);
  }
}

// ─── Processing Dialog ────────────────────────────────────────────────────────

class _ProcessingDialog extends StatelessWidget {
  const _ProcessingDialog();

  @override
  Widget build(BuildContext context) {
    return Dialog(
      backgroundColor: Colors.transparent,
      child: Container(
        padding: const EdgeInsets.all(32),
        decoration: BoxDecoration(
          color: Theme.of(context).colorScheme.surface,
          borderRadius: BorderRadius.circular(20),
        ),
        child: Column(
          mainAxisSize: MainAxisSize.min,
          children: [
            const SizedBox(
              width: 56, height: 56,
              child: CircularProgressIndicator(color: AppColors.primary, strokeWidth: 4),
            ),
            const SizedBox(height: 20),
            Text('AI Analysing Image', style: Theme.of(context).textTheme.titleMedium),
            const SizedBox(height: 8),
            Text(
              'Detecting issue type, severity,\nand generating description…',
              style: Theme.of(context).textTheme.bodySmall?.copyWith(color: AppColors.onSurfaceVar),
              textAlign: TextAlign.center,
            ),
          ],
        ),
      ),
    );
  }
}
