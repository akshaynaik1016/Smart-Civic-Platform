import 'dart:io';
import 'package:flutter/material.dart';
import 'package:flutter_bloc/flutter_bloc.dart';
import 'package:geocoding/geocoding.dart';
import 'package:geolocator/geolocator.dart';
import 'package:go_router/go_router.dart';

import '../../../../core/theme/app_theme.dart';
import '../../../../shared/widgets/app_text_field.dart';
import '../../../../shared/widgets/loading_button.dart';
import '../../../../shared/widgets/severity_badge.dart';
import '../bloc/complaint_bloc.dart';

class ComplaintSubmitScreen extends StatefulWidget {
  final Map<String, dynamic> data;
  const ComplaintSubmitScreen({super.key, required this.data});

  @override
  State<ComplaintSubmitScreen> createState() => _ComplaintSubmitScreenState();
}

class _ComplaintSubmitScreenState extends State<ComplaintSubmitScreen> {
  final _formKey      = GlobalKey<FormState>();
  final _titleCtrl    = TextEditingController();
  final _descCtrl     = TextEditingController();
  final _addressCtrl  = TextEditingController();

  late String   _category;
  late String   _severity;
  double?       _lat, _lng;
  bool          _resolvingAddress = false;

  final _categories = [
    'pothole', 'garbage', 'water_leakage', 'open_manhole',
    'broken_streetlight', 'fallen_tree', 'damaged_road_sign', 'illegal_dumping', 'other',
  ];

  final _severities = ['low', 'medium', 'high', 'critical'];

  @override
  void initState() {
    super.initState();
    _category = widget.data['category'] as String? ?? 'other';
    _severity = widget.data['severity'] as String? ?? 'medium';
    _lat = widget.data['latitude'] as double?;
    _lng = widget.data['longitude'] as double?;

    // Pre-fill AI description
    final desc = widget.data['description'] as String? ?? '';
    _descCtrl.text = desc;
    _titleCtrl.text = _category.displayCategory;

    if (_lat != null && _lng != null) _resolveAddress();
  }

  @override
  void dispose() {
    _titleCtrl.dispose(); _descCtrl.dispose(); _addressCtrl.dispose();
    super.dispose();
  }

  Future<void> _resolveAddress() async {
    setState(() => _resolvingAddress = true);
    try {
      final placemarks = await placemarkFromCoordinates(_lat!, _lng!);
      if (placemarks.isNotEmpty) {
        final p = placemarks.first;
        _addressCtrl.text =
            '${p.street ?? ''}, ${p.subLocality ?? ''}, ${p.locality ?? ''}, ${p.postalCode ?? ''}';
      }
    } catch (_) {
      _addressCtrl.text = 'Location: ${_lat!.toStringAsFixed(5)}, ${_lng!.toStringAsFixed(5)}';
    } finally {
      if (mounted) setState(() => _resolvingAddress = false);
    }
  }

  Future<void> _getCurrentLocation() async {
    try {
      final pos = await Geolocator.getCurrentPosition(
          desiredAccuracy: LocationAccuracy.high);
      setState(() {
        _lat = pos.latitude;
        _lng = pos.longitude;
      });
      await _resolveAddress();
    } catch (e) {
      ScaffoldMessenger.of(context).showSnackBar(
          const SnackBar(content: Text('Could not fetch location')));
    }
  }

  void _submit() {
    if (_formKey.currentState!.validate()) {
      if (_lat == null || _lng == null) {
        ScaffoldMessenger.of(context).showSnackBar(
            const SnackBar(content: Text('Please allow location access')));
        return;
      }
      context.read<ComplaintBloc>().add(ComplaintSubmitRequested(
        imagePath:   widget.data['imagePath'] as String,
        title:       _titleCtrl.text.trim(),
        description: _descCtrl.text.trim(),
        category:    _category,
        severity:    _severity,
        latitude:    _lat!,
        longitude:   _lng!,
        address:     _addressCtrl.text.trim(),
        aiConfidence: widget.data['confidence'] as double? ?? 0,
        boundingBoxes: widget.data['bounding_boxes'] as List<dynamic>? ?? [],
      ));
    }
  }

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      appBar: AppBar(title: const Text('Submit Report')),
      body: BlocConsumer<ComplaintBloc, ComplaintState>(
        listener: (context, state) {
          if (state is ComplaintSubmitted) {
            ScaffoldMessenger.of(context).showSnackBar(
              const SnackBar(
                content: Text('✅ Complaint submitted successfully!'),
                backgroundColor: AppColors.statusResolved,
                behavior: SnackBarBehavior.floating,
              ),
            );
            // Navigate to detail
            context.go('/history/detail/${state.complaintId}');
          } else if (state is ComplaintError) {
            ScaffoldMessenger.of(context).showSnackBar(
              SnackBar(content: Text(state.message), backgroundColor: Colors.red),
            );
          }
        },
        builder: (context, state) {
          return Form(
            key: _formKey,
            child: ListView(
              padding: const EdgeInsets.all(20),
              children: [

                // ── Image preview ──────────────────────────────────────
                ClipRRect(
                  borderRadius: BorderRadius.circular(16),
                  child: Stack(
                    children: [
                      Image.file(
                        File(widget.data['imagePath'] as String),
                        height: 200, width: double.infinity, fit: BoxFit.cover,
                      ),
                      Positioned(
                        top: 12, right: 12,
                        child: SeverityBadge(severity: _severity),
                      ),
                      Positioned(
                        bottom: 12, left: 12,
                        child: Container(
                          padding: const EdgeInsets.symmetric(horizontal: 10, vertical: 5),
                          decoration: BoxDecoration(
                            color: Colors.black54,
                            borderRadius: BorderRadius.circular(12),
                          ),
                          child: Row(mainAxisSize: MainAxisSize.min, children: [
                            Text(_category.categoryEmoji, style: const TextStyle(fontSize: 14)),
                            const SizedBox(width: 6),
                            Text(_category.displayCategory,
                                style: const TextStyle(color: Colors.white, fontSize: 12, fontWeight: FontWeight.w600)),
                          ]),
                        ),
                      ),
                    ],
                  ),
                ),
                const SizedBox(height: 20),

                // ── Category picker ────────────────────────────────────
                Text('Issue Category', style: Theme.of(context).textTheme.titleMedium),
                const SizedBox(height: 10),
                Wrap(
                  spacing: 8, runSpacing: 8,
                  children: _categories.map((cat) => ChoiceChip(
                    label: Text('${cat.categoryEmoji} ${cat.displayCategory}',
                        style: const TextStyle(fontSize: 12)),
                    selected: _category == cat,
                    selectedColor: cat.categoryColor.withOpacity(0.2),
                    onSelected: (_) => setState(() => _category = cat),
                  )).toList(),
                ),
                const SizedBox(height: 20),

                // ── Title ──────────────────────────────────────────────
                AppTextField(
                  controller: _titleCtrl,
                  label: 'Issue Title',
                  hint: 'e.g. Large pothole on College Road',
                  prefixIcon: Icons.title_rounded,
                  textInputAction: TextInputAction.next,
                  validator: (v) => v == null || v.trim().isEmpty ? 'Title is required' : null,
                ),
                const SizedBox(height: 16),

                // ── Description ────────────────────────────────────────
                AppTextField(
                  controller: _descCtrl,
                  label: 'Description',
                  hint: 'Describe the issue in detail…',
                  prefixIcon: Icons.description_rounded,
                  maxLines: 4,
                  textInputAction: TextInputAction.next,
                  validator: (v) => v == null || v.trim().length < 10
                      ? 'Minimum 10 characters' : null,
                ),
                const SizedBox(height: 16),

                // ── Severity picker ────────────────────────────────────
                Text('Severity Level', style: Theme.of(context).textTheme.titleMedium),
                const SizedBox(height: 10),
                Row(
                  children: _severities.map((s) => Expanded(
                    child: Padding(
                      padding: const EdgeInsets.symmetric(horizontal: 4),
                      child: ChoiceChip(
                        label: Text(s[0].toUpperCase() + s.substring(1),
                            style: const TextStyle(fontSize: 11)),
                        selected: _severity == s,
                        selectedColor: s.severityColor.withOpacity(0.2),
                        side: BorderSide(
                            color: _severity == s ? s.severityColor : AppColors.divider),
                        onSelected: (_) => setState(() => _severity = s),
                        padding: EdgeInsets.zero,
                      ),
                    ),
                  )).toList(),
                ),
                const SizedBox(height: 20),

                // ── Location ───────────────────────────────────────────
                Text('Location', style: Theme.of(context).textTheme.titleMedium),
                const SizedBox(height: 10),
                if (_lat != null && _lng != null)
                  Container(
                    padding: const EdgeInsets.all(12),
                    decoration: BoxDecoration(
                      color: AppColors.surfaceVariant,
                      borderRadius: BorderRadius.circular(14),
                    ),
                    child: Row(children: [
                      const Icon(Icons.gps_fixed_rounded, color: AppColors.secondary, size: 18),
                      const SizedBox(width: 8),
                      Expanded(
                        child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
                          Text('${_lat!.toStringAsFixed(5)}, ${_lng!.toStringAsFixed(5)}',
                              style: const TextStyle(fontSize: 11, color: AppColors.onSurfaceVar)),
                          if (_resolvingAddress)
                            const Text('Resolving address…',
                                style: TextStyle(fontSize: 12, color: AppColors.onSurfaceVar))
                          else
                            Text(_addressCtrl.text.isNotEmpty ? _addressCtrl.text : '—',
                                style: const TextStyle(fontSize: 13, fontWeight: FontWeight.w500)),
                        ]),
                      ),
                      TextButton(
                        onPressed: _getCurrentLocation,
                        child: const Text('Update', style: TextStyle(fontSize: 12)),
                      ),
                    ]),
                  )
                else
                  OutlinedButton.icon(
                    onPressed: _getCurrentLocation,
                    icon: const Icon(Icons.my_location_rounded),
                    label: const Text('Use Current Location'),
                  ),

                const SizedBox(height: 32),

                // ── Submit ─────────────────────────────────────────────
                LoadingButton(
                  label: 'Submit Complaint',
                  isLoading: state is ComplaintSubmitting,
                  icon: Icons.send_rounded,
                  onPressed: _submit,
                ),
                const SizedBox(height: 24),

                // ── Disclaimer ─────────────────────────────────────────
                const Text(
                  '⚠️ False reports may lead to account suspension. '
                  'Submit only genuine civic issues.',
                  textAlign: TextAlign.center,
                  style: TextStyle(fontSize: 11, color: AppColors.onSurfaceVar, height: 1.6),
                ),
              ],
            ),
          );
        },
      ),
    );
  }
}
