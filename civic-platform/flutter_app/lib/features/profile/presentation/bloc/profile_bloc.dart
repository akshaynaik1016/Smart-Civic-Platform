import 'package:equatable/equatable.dart';
import 'package:flutter_bloc/flutter_bloc.dart';

import '../../../auth/data/models/user_model.dart';
import '../../../auth/data/repositories/auth_repository.dart';
import '../../../profile/data/repositories/profile_repository.dart';

// ─── Events ───────────────────────────────────────────────────────────────────

abstract class ProfileEvent extends Equatable {
  const ProfileEvent();
  @override
  List<Object?> get props => [];
}

class ProfileLoadRequested extends ProfileEvent {}

class ProfileUpdateRequested extends ProfileEvent {
  final String? fullName;
  final String? phone;
  const ProfileUpdateRequested({this.fullName, this.phone});
  @override
  List<Object?> get props => [fullName, phone];
}

class ProfileAvatarUploadRequested extends ProfileEvent {
  final String imagePath;
  const ProfileAvatarUploadRequested(this.imagePath);
  @override
  List<Object?> get props => [imagePath];
}

class ProfileActivityLoadRequested extends ProfileEvent {}

// ─── States ───────────────────────────────────────────────────────────────────

abstract class ProfileState extends Equatable {
  const ProfileState();
  @override
  List<Object?> get props => [];
}

class ProfileInitial extends ProfileState {}
class ProfileLoading extends ProfileState {}
class ProfileUpdating extends ProfileState {}

class ProfileLoaded extends ProfileState {
  final UserModel user;
  final Map<String, dynamic>? activity;
  const ProfileLoaded({required this.user, this.activity});
  @override
  List<Object?> get props => [user, activity];
}

class ProfileError extends ProfileState {
  final String message;
  const ProfileError(this.message);
  @override
  List<Object?> get props => [message];
}

class ProfileUpdateSuccess extends ProfileState {
  final UserModel user;
  const ProfileUpdateSuccess(this.user);
  @override
  List<Object?> get props => [user];
}

// ─── BLoC ─────────────────────────────────────────────────────────────────────

class ProfileBloc extends Bloc<ProfileEvent, ProfileState> {
  final ProfileRepository  _profileRepo;
  final AuthRepository     _authRepo;

  ProfileBloc({
    required ProfileRepository profileRepo,
    required AuthRepository    authRepo,
  })  : _profileRepo = profileRepo,
        _authRepo    = authRepo,
        super(ProfileInitial()) {
    on<ProfileLoadRequested>(_onLoad);
    on<ProfileUpdateRequested>(_onUpdate);
    on<ProfileAvatarUploadRequested>(_onAvatarUpload);
    on<ProfileActivityLoadRequested>(_onLoadActivity);
  }

  Future<void> _onLoad(
    ProfileLoadRequested event,
    Emitter<ProfileState> emit,
  ) async {
    emit(ProfileLoading());
    try {
      final user = await _authRepo.getCurrentUser();
      if (user == null) {
        emit(const ProfileError('Not authenticated'));
        return;
      }
      emit(ProfileLoaded(user: user));
    } catch (e) {
      emit(ProfileError(e.toString().replaceFirst('Exception: ', '')));
    }
  }

  Future<void> _onUpdate(
    ProfileUpdateRequested event,
    Emitter<ProfileState> emit,
  ) async {
    emit(ProfileUpdating());
    try {
      final updated = await _profileRepo.updateProfile(
        fullName: event.fullName,
        phone:    event.phone,
      );
      emit(ProfileUpdateSuccess(updated));
      emit(ProfileLoaded(user: updated));
    } catch (e) {
      emit(ProfileError(e.toString().replaceFirst('Exception: ', '')));
    }
  }

  Future<void> _onAvatarUpload(
    ProfileAvatarUploadRequested event,
    Emitter<ProfileState> emit,
  ) async {
    emit(ProfileUpdating());
    try {
      final updated = await _profileRepo.uploadAvatar(event.imagePath);
      emit(ProfileUpdateSuccess(updated));
      emit(ProfileLoaded(user: updated));
    } catch (e) {
      emit(ProfileError(e.toString().replaceFirst('Exception: ', '')));
    }
  }

  Future<void> _onLoadActivity(
    ProfileActivityLoadRequested event,
    Emitter<ProfileState> emit,
  ) async {
    final current = state;
    if (current is! ProfileLoaded) return;
    try {
      final activity = await _profileRepo.getActivitySummary();
      emit(ProfileLoaded(user: current.user, activity: activity));
    } catch (_) {}
  }
}