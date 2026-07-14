import 'package:flutter/material.dart';
import 'package:flutter_bloc/flutter_bloc.dart';
import 'package:go_router/go_router.dart';
import 'package:image_picker/image_picker.dart';

import '../../../../core/theme/app_theme.dart';
import '../../../auth/data/models/user_model.dart';
import '../../../auth/presentation/bloc/auth_bloc.dart';
import '../bloc/profile_bloc.dart';

class ProfileScreen extends StatefulWidget {
  const ProfileScreen({super.key});

  @override
  State<ProfileScreen> createState() => _ProfileScreenState();
}

class _ProfileScreenState extends State<ProfileScreen> {
  @override
  void initState() {
    super.initState();
    context.read<ProfileBloc>()
      ..add(ProfileLoadRequested())
      ..add(ProfileActivityLoadRequested());
  }

  Future<void> _pickAndUploadAvatar() async {
    final picker = ImagePicker();
    final file   = await picker.pickImage(
      source:     ImageSource.gallery,
      imageQuality: 80,
      maxWidth:   512,
    );
    if (file != null && mounted) {
      context
          .read<ProfileBloc>()
          .add(ProfileAvatarUploadRequested(file.path));
    }
  }

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      body: BlocConsumer<ProfileBloc, ProfileState>(
        listener: (context, state) {
          if (state is ProfileUpdateSuccess) {
            ScaffoldMessenger.of(context).showSnackBar(
              const SnackBar(
                content:          Text('Profile updated'),
                backgroundColor:  AppColors.statusResolved,
                behavior:         SnackBarBehavior.floating,
              ),
            );
          }
          if (state is ProfileError) {
            ScaffoldMessenger.of(context).showSnackBar(
              SnackBar(
                content:         Text(state.message),
                backgroundColor: Colors.red.shade700,
                behavior:        SnackBarBehavior.floating,
              ),
            );
          }
        },
        builder: (context, state) {
          if (state is ProfileLoading) {
            return const Center(child: CircularProgressIndicator());
          }

          final user = state is ProfileLoaded     ? state.user
                     : state is ProfileUpdateSuccess ? state.user
                     : state is ProfileUpdating
                         ? (context.read<ProfileBloc>().state is ProfileLoaded
                             ? (context.read<ProfileBloc>().state as ProfileLoaded).user
                             : null)
                         : null;

          if (user == null) {
            return Center(
              child: Column(
                mainAxisAlignment: MainAxisAlignment.center,
                children: [
                  const Icon(Icons.person_off_rounded,
                      size: 56, color: AppColors.onSurfaceVar),
                  const SizedBox(height: 16),
                  const Text('Could not load profile'),
                  const SizedBox(height: 16),
                  ElevatedButton(
                    onPressed: () =>
                        context.read<ProfileBloc>().add(ProfileLoadRequested()),
                    child: const Text('Retry'),
                  ),
                ],
              ),
            );
          }

          final activity = state is ProfileLoaded ? state.activity : null;

          return CustomScrollView(
            slivers: [
              // ── Profile header ──────────────────────────────────────────
              SliverAppBar(
                expandedHeight: 240,
                pinned:         true,
                backgroundColor: AppColors.primary,
                actions: [
                  IconButton(
                    icon:     const Icon(Icons.settings_rounded, color: Colors.white),
                    onPressed: () => context.push('/profile/settings'),
                    tooltip:  'Settings',
                  ),
                ],
                flexibleSpace: FlexibleSpaceBar(
                  background: Container(
                    decoration: const BoxDecoration(
                      gradient: LinearGradient(
                        begin:  Alignment.topLeft,
                        end:    Alignment.bottomRight,
                        colors: [Color(0xFF1565C0), Color(0xFF0D47A1)],
                      ),
                    ),
                    child: SafeArea(
                      child: Column(
                        mainAxisAlignment: MainAxisAlignment.center,
                        children: [
                          const SizedBox(height: 16),

                          // Avatar
                          Stack(
                            children: [
                              CircleAvatar(
                                radius: 48,
                                backgroundColor: Colors.white24,
                                backgroundImage: user.avatarUrl != null
                                    ? NetworkImage(user.avatarUrl!)
                                    : null,
                                child: user.avatarUrl == null
                                    ? Text(
                                        user.fullName.isNotEmpty
                                            ? user.fullName[0].toUpperCase()
                                            : 'U',
                                        style: const TextStyle(
                                          fontSize:   36,
                                          fontWeight: FontWeight.w700,
                                          color:      Colors.white,
                                        ),
                                      )
                                    : null,
                              ),
                              Positioned(
                                bottom: 0,
                                right:  0,
                                child:  GestureDetector(
                                  onTap: _pickAndUploadAvatar,
                                  child: Container(
                                    padding: const EdgeInsets.all(6),
                                    decoration: const BoxDecoration(
                                      color: AppColors.accent,
                                      shape: BoxShape.circle,
                                    ),
                                    child: const Icon(
                                      Icons.camera_alt_rounded,
                                      color: Colors.white,
                                      size:  16,
                                    ),
                                  ),
                                ),
                              ),
                              if (state is ProfileUpdating)
                                Positioned.fill(
                                  child: Container(
                                    decoration: const BoxDecoration(
                                      color:  Colors.black38,
                                      shape: BoxShape.circle,
                                    ),
                                    child: const CircularProgressIndicator(
                                      color: Colors.white,
                                      strokeWidth: 2,
                                    ),
                                  ),
                                ),
                            ],
                          ),
                          const SizedBox(height: 12),

                          // Name
                          Text(
                            user.fullName,
                            style: const TextStyle(
                              color:      Colors.white,
                              fontSize:   20,
                              fontWeight: FontWeight.w700,
                            ),
                          ),
                          const SizedBox(height: 4),

                          // Email
                          Text(
                            user.email,
                            style: const TextStyle(
                              color:    Colors.white70,
                              fontSize: 13,
                            ),
                          ),

                          // Role badge
                          const SizedBox(height: 8),
                          Container(
                            padding: const EdgeInsets.symmetric(
                                horizontal: 12, vertical: 4),
                            decoration: BoxDecoration(
                              color:        Colors.white24,
                              borderRadius: BorderRadius.circular(20),
                            ),
                            child: Text(
                              user.role.toUpperCase(),
                              style: const TextStyle(
                                color:      Colors.white,
                                fontSize:   11,
                                fontWeight: FontWeight.w700,
                                letterSpacing: 0.5,
                              ),
                            ),
                          ),
                        ],
                      ),
                    ),
                  ),
                ),
              ),

              // ── Stats ───────────────────────────────────────────────────
              SliverToBoxAdapter(
                child: Padding(
                  padding: const EdgeInsets.all(20),
                  child: Row(
                    children: [
                      _StatTile(
                        label: 'Complaints',
                        value: '${user.totalComplaints}',
                        icon:  Icons.assignment_rounded,
                        color: AppColors.primary,
                      ),
                      const SizedBox(width: 12),
                      _StatTile(
                        label: 'Resolved',
                        value: '${user.resolvedComplaints}',
                        icon:  Icons.check_circle_rounded,
                        color: AppColors.statusResolved,
                      ),
                      const SizedBox(width: 12),
                      _StatTile(
                        label: 'Score',
                        value: user.reputationScore != null
                            ? user.reputationScore!.toStringAsFixed(0)
                            : '—',
                        icon:  Icons.star_rounded,
                        color: AppColors.accent,
                      ),
                    ],
                  ),
                ),
              ),

              // ── Edit profile button ─────────────────────────────────────
              SliverToBoxAdapter(
                child: Padding(
                  padding: const EdgeInsets.symmetric(horizontal: 20),
                  child: OutlinedButton.icon(
                    icon:     const Icon(Icons.edit_rounded, size: 18),
                    label:    const Text('Edit Profile'),
                    onPressed: () => _showEditSheet(context, user),
                  ),
                ),
              ),
              const SliverToBoxAdapter(child: SizedBox(height: 24)),

              // ── Info tiles ──────────────────────────────────────────────
              SliverToBoxAdapter(
                child: Padding(
                  padding: const EdgeInsets.symmetric(horizontal: 20),
                  child: Column(
                    crossAxisAlignment: CrossAxisAlignment.start,
                    children: [
                      Text('Account Details',
                          style: Theme.of(context).textTheme.titleMedium),
                      const SizedBox(height: 12),
                      _InfoTile(
                        icon:  Icons.email_outlined,
                        label: 'Email',
                        value: user.email,
                      ),
                      if (user.phone != null && user.phone!.isNotEmpty)
                        _InfoTile(
                          icon:  Icons.phone_outlined,
                          label: 'Phone',
                          value: user.phone!,
                        ),
                      _InfoTile(
                        icon:  Icons.verified_rounded,
                        label: 'Email Verified',
                        value: user.emailVerified ? 'Yes ✓' : 'Not verified',
                        valueColor: user.emailVerified
                            ? AppColors.statusResolved
                            : Colors.red,
                      ),
                    ],
                  ),
                ),
              ),

              // ── Activity summary ────────────────────────────────────────
              if (activity != null)
                SliverToBoxAdapter(
                  child: Padding(
                    padding: const EdgeInsets.fromLTRB(20, 24, 20, 0),
                    child: Column(
                      crossAxisAlignment: CrossAxisAlignment.start,
                      children: [
                        Text('Activity Summary',
                            style: Theme.of(context).textTheme.titleMedium),
                        const SizedBox(height: 12),
                        _InfoTile(
                          icon:  Icons.pending_actions_rounded,
                          label: 'Open Complaints',
                          value: '${activity['open_complaints'] ?? 0}',
                        ),
                        _InfoTile(
                          icon:  Icons.trending_up_rounded,
                          label: 'Resolution Rate',
                          value:
                              '${activity['resolution_rate'] ?? 0}%',
                        ),
                      ],
                    ),
                  ),
                ),

              const SliverToBoxAdapter(child: SizedBox(height: 40)),
            ],
          );
        },
      ),
    );
  }

  void _showEditSheet(BuildContext context, UserModel user) {
    final nameCtrl  = TextEditingController(text: user.fullName);
    final phoneCtrl = TextEditingController(text: user.phone ?? '');
    final formKey   = GlobalKey<FormState>();

    showModalBottomSheet<void>(
      context:       context,
      isScrollControlled: true,
      shape: const RoundedRectangleBorder(
        borderRadius: BorderRadius.vertical(top: Radius.circular(20)),
      ),
      builder: (ctx) => Padding(
        padding: EdgeInsets.only(
          left:   24, right: 24, top: 24,
          bottom: MediaQuery.of(ctx).viewInsets.bottom + 24,
        ),
        child: Form(
          key: formKey,
          child: Column(
            mainAxisSize:        MainAxisSize.min,
            crossAxisAlignment:  CrossAxisAlignment.start,
            children: [
              Text('Edit Profile',
                  style: Theme.of(context).textTheme.titleLarge),
              const SizedBox(height: 20),
              TextFormField(
                controller: nameCtrl,
                decoration: const InputDecoration(
                  labelText: 'Full Name',
                  prefixIcon: Icon(Icons.person_outline_rounded),
                ),
                validator: (v) => v == null || v.trim().length < 2
                    ? 'Enter at least 2 characters'
                    : null,
              ),
              const SizedBox(height: 16),
              TextFormField(
                controller:   phoneCtrl,
                decoration:   const InputDecoration(
                  labelText:  'Phone Number',
                  prefixIcon: Icon(Icons.phone_outlined),
                ),
                keyboardType: TextInputType.phone,
              ),
              const SizedBox(height: 24),
              SizedBox(
                width: double.infinity,
                height: 52,
                child: ElevatedButton(
                  onPressed: () {
                    if (formKey.currentState!.validate()) {
                      context.read<ProfileBloc>().add(
                            ProfileUpdateRequested(
                              fullName: nameCtrl.text.trim(),
                              phone:    phoneCtrl.text.trim().isEmpty
                                  ? null
                                  : phoneCtrl.text.trim(),
                            ),
                          );
                      Navigator.pop(ctx);
                    }
                  },
                  child: const Text('Save Changes'),
                ),
              ),
            ],
          ),
        ),
      ),
    );
  }
}

class _StatTile extends StatelessWidget {
  final String label, value;
  final IconData icon;
  final Color color;

  const _StatTile({
    required this.label, required this.value,
    required this.icon,  required this.color,
  });

  @override
  Widget build(BuildContext context) => Expanded(
        child: Container(
          padding: const EdgeInsets.symmetric(vertical: 16, horizontal: 8),
          decoration: BoxDecoration(
            color:        Theme.of(context).colorScheme.surface,
            borderRadius: BorderRadius.circular(16),
            boxShadow: [
              BoxShadow(
                color:      Colors.black.withOpacity(0.06),
                blurRadius: 12,
                offset:     const Offset(0, 4),
              ),
            ],
          ),
          child: Column(
            children: [
              Icon(icon, color: color, size: 24),
              const SizedBox(height: 6),
              Text(value,
                  style: TextStyle(
                    fontSize:   20,
                    fontWeight: FontWeight.w700,
                    color:      color,
                  )),
              const SizedBox(height: 2),
              Text(label,
                  style: const TextStyle(
                    fontSize: 11,
                    color:    AppColors.onSurfaceVar,
                  ),
                  textAlign: TextAlign.center),
            ],
          ),
        ),
      );
}

class _InfoTile extends StatelessWidget {
  final IconData icon;
  final String label, value;
  final Color? valueColor;

  const _InfoTile({
    required this.icon, required this.label, required this.value,
    this.valueColor,
  });

  @override
  Widget build(BuildContext context) => Padding(
        padding: const EdgeInsets.symmetric(vertical: 8),
        child: Row(
          children: [
            Icon(icon, size: 20, color: AppColors.primary),
            const SizedBox(width: 12),
            Text('$label: ',
                style: const TextStyle(
                  fontWeight: FontWeight.w600, fontSize: 14)),
            Expanded(
              child: Text(
                value,
                style: TextStyle(
                  fontSize: 14,
                  color:    valueColor ?? AppColors.onSurfaceVar,
                ),
                overflow: TextOverflow.ellipsis,
              ),
            ),
          ],
        ),
      );
}