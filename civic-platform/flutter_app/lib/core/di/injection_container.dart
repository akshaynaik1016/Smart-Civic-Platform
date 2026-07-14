import 'package:get_it/get_it.dart';

import '../../features/auth/data/repositories/auth_repository.dart';
import '../../features/auth/presentation/bloc/auth_bloc.dart';
import '../../features/complaint/data/repositories/complaint_repository.dart';
import '../../features/complaint/presentation/bloc/complaint_bloc.dart';
import '../../features/notifications/data/repositories/notification_repository.dart';
import '../../features/notifications/presentation/bloc/notification_bloc.dart';
import '../../features/profile/data/repositories/profile_repository.dart';
import '../../features/profile/presentation/bloc/profile_bloc.dart';

final GetIt sl = GetIt.instance;

Future<void> init() async {
  // ── Repositories (lazy singletons — created on first use) ──────────────────
  sl.registerLazySingleton<AuthRepository>(AuthRepository.new);
  sl.registerLazySingleton<ComplaintRepository>(ComplaintRepository.new);
  sl.registerLazySingleton<NotificationRepository>(NotificationRepository.new);
  sl.registerLazySingleton<ProfileRepository>(ProfileRepository.new);

  // ── BLoCs (factories — new instance every time a screen requests one) ──────
  sl.registerFactory<AuthBloc>(
    () => AuthBloc(sl<AuthRepository>()),
  );

  sl.registerFactory<ComplaintBloc>(
    () => ComplaintBloc(sl<ComplaintRepository>()),
  );

  sl.registerFactory<NotificationBloc>(
    () => NotificationBloc(sl<NotificationRepository>()),
  );

  sl.registerFactory<ProfileBloc>(
    () => ProfileBloc(
      profileRepo: sl<ProfileRepository>(),
      authRepo:    sl<AuthRepository>(),
    ),
  );
}