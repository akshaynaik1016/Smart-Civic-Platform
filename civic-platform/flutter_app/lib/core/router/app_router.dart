import 'package:flutter/material.dart';
import 'package:flutter_bloc/flutter_bloc.dart';
import 'package:go_router/go_router.dart';

import '../../features/auth/presentation/bloc/auth_bloc.dart';
import '../../features/auth/presentation/screens/login_screen.dart';
import '../../features/auth/presentation/screens/register_screen.dart';
import '../../features/auth/presentation/screens/splash_screen.dart';
import '../../features/complaint/presentation/screens/ai_result_screen.dart';
import '../../features/complaint/presentation/screens/camera_screen.dart';
import '../../features/complaint/presentation/screens/complaint_detail_screen.dart';
import '../../features/complaint/presentation/screens/complaint_history_screen.dart';
import '../../features/complaint/presentation/screens/complaint_submit_screen.dart';
import '../../features/home/presentation/screens/home_screen.dart';
import '../../features/map/presentation/screens/nearby_map_screen.dart';
import '../../features/notifications/presentation/screens/notifications_screen.dart';
import '../../features/profile/presentation/screens/profile_screen.dart';
import '../../features/profile/presentation/screens/settings_screen.dart';
import '../constants/app_constants.dart';

final _rootNavigatorKey = GlobalKey<NavigatorState>();

class AppRouter {
  static final router = GoRouter(
    navigatorKey: _rootNavigatorKey,
    initialLocation: AppRoutes.splash,
    debugLogDiagnostics: false,
    redirect: _authGuard,
    routes: [
      GoRoute(
        path: AppRoutes.splash,
        name: 'splash',
        builder: (_, __) => const SplashScreen(),
      ),
      GoRoute(
        path: AppRoutes.login,
        name: 'login',
        builder: (_, __) => const LoginScreen(),
      ),
      GoRoute(
        path: AppRoutes.register,
        name: 'register',
        builder: (_, __) => const RegisterScreen(),
      ),

      // Main app shell (bottom nav)
      StatefulShellRoute.indexedStack(
        builder: (context, state, shell) => MainShell(shell: shell),
        branches: [
          StatefulShellBranch(routes: [
            GoRoute(
              path: AppRoutes.home,
              name: 'home',
              builder: (_, __) => const HomeScreen(),
            ),
          ]),
          StatefulShellBranch(routes: [
            GoRoute(
              path: AppRoutes.history,
              name: 'history',
              builder: (_, __) => const ComplaintHistoryScreen(),
              routes: [
                GoRoute(
                  path: 'detail/:id',
                  name: 'complaint-detail',
                  builder: (_, state) => ComplaintDetailScreen(
                    complaintId: state.pathParameters['id']!,
                  ),
                ),
              ],
            ),
          ]),
          StatefulShellBranch(routes: [
            GoRoute(
              path: AppRoutes.map,
              name: 'map',
              builder: (_, __) => const NearbyMapScreen(),
            ),
          ]),
          StatefulShellBranch(routes: [
            GoRoute(
              path: AppRoutes.notifications,
              name: 'notifications',
              builder: (_, __) => const NotificationsScreen(),
            ),
          ]),
          StatefulShellBranch(routes: [
            GoRoute(
              path: AppRoutes.profile,
              name: 'profile',
              builder: (_, __) => const ProfileScreen(),
              routes: [
                GoRoute(
                  path: 'settings',
                  name: 'settings',
                  builder: (_, __) => const SettingsScreen(),
                ),
              ],
            ),
          ]),
        ],
      ),

      // Camera & AI flow (full-screen, no shell)
      GoRoute(
        path: AppRoutes.camera,
        name: 'camera',
        builder: (_, __) => const CameraScreen(),
      ),
      GoRoute(
        path: AppRoutes.aiResult,
        name: 'ai-result',
        builder: (_, state) {
          final extra = state.extra as Map<String, dynamic>;
          return AiResultScreen(
            imagePath:   extra['imagePath']  as String,
            analysisResult: extra['analysis'] as Map<String, dynamic>?,
          );
        },
      ),
      GoRoute(
        path: AppRoutes.submitComplaint,
        name: 'submit-complaint',
        builder: (_, state) {
          final extra = state.extra as Map<String, dynamic>;
          return ComplaintSubmitScreen(data: extra);
        },
      ),
    ],
  );

  static String? _authGuard(BuildContext context, GoRouterState state) {
    final authState = context.read<AuthBloc>().state;
    final isLoggingIn = state.matchedLocation == AppRoutes.login ||
        state.matchedLocation == AppRoutes.register ||
        state.matchedLocation == AppRoutes.splash;

    if (authState is AuthLoading) return null;
    if (authState is AuthAuthenticated) {
      return isLoggingIn ? AppRoutes.home : null;
    }
    return isLoggingIn ? null : AppRoutes.login;
  }
}

class AppRoutes {
  static const splash          = '/';
  static const login           = '/login';
  static const register        = '/register';
  static const home            = '/home';
  static const history         = '/history';
  static const map             = '/map';
  static const notifications   = '/notifications';
  static const profile         = '/profile';
  static const camera          = '/camera';
  static const aiResult        = '/ai-result';
  static const submitComplaint = '/submit-complaint';
}

// ─── Main Shell with Bottom Nav ──────────────────────────────────────────────

class MainShell extends StatelessWidget {
  final StatefulNavigationShell shell;
  const MainShell({super.key, required this.shell});

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      body: shell,
      floatingActionButton: FloatingActionButton(
        onPressed: () => context.push(AppRoutes.camera),
        child: const Icon(Icons.camera_alt_rounded, size: 28),
      ),
      floatingActionButtonLocation: FloatingActionButtonLocation.centerDocked,
      bottomNavigationBar: BottomAppBar(
        shape: const CircularNotchedRectangle(),
        notchMargin: 8,
        child: Row(
          mainAxisAlignment: MainAxisAlignment.spaceAround,
          children: [
            _NavItem(icon: Icons.home_rounded,         label: 'Home',    index: 0, shell: shell),
            _NavItem(icon: Icons.list_alt_rounded,     label: 'Reports', index: 1, shell: shell),
            const SizedBox(width: 64), // FAB space
            _NavItem(icon: Icons.map_rounded,          label: 'Map',     index: 2, shell: shell),
            _NavItem(icon: Icons.notifications_rounded,label: 'Alerts',  index: 3, shell: shell),
          ],
        ),
      ),
    );
  }
}

class _NavItem extends StatelessWidget {
  final IconData icon;
  final String label;
  final int index;
  final StatefulNavigationShell shell;

  const _NavItem({
    required this.icon, required this.label,
    required this.index, required this.shell,
  });

  @override
  Widget build(BuildContext context) {
    final selected = shell.currentIndex == index;
    final color = selected
        ? Theme.of(context).colorScheme.primary
        : Theme.of(context).colorScheme.onSurfaceVariant;
    return GestureDetector(
      onTap: () => shell.goBranch(index, initialLocation: index == shell.currentIndex),
      behavior: HitTestBehavior.opaque,
      child: Padding(
        padding: const EdgeInsets.symmetric(horizontal: 16, vertical: 8),
        child: Column(
          mainAxisSize: MainAxisSize.min,
          children: [
            Icon(icon, color: color, size: 24),
            const SizedBox(height: 2),
            Text(label, style: TextStyle(fontSize: 11, color: color, fontWeight: FontWeight.w600)),
          ],
        ),
      ),
    );
  }
}
