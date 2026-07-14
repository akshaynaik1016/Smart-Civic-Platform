import 'package:equatable/equatable.dart';
import 'package:flutter_bloc/flutter_bloc.dart';

import '../../data/models/user_model.dart';
import '../../data/repositories/auth_repository.dart';

// ─── Events ──────────────────────────────────────────────────────────────────

abstract class AuthEvent extends Equatable {
  const AuthEvent();
  @override List<Object?> get props => [];
}

class AuthCheckRequested   extends AuthEvent {}
class AuthLogoutRequested  extends AuthEvent {}

class AuthLoginRequested extends AuthEvent {
  final String email;
  final String password;
  const AuthLoginRequested({required this.email, required this.password});
  @override List<Object?> get props => [email, password];
}

class AuthRegisterRequested extends AuthEvent {
  final String fullName;
  final String email;
  final String phone;
  final String password;
  const AuthRegisterRequested({
    required this.fullName, required this.email,
    required this.phone,    required this.password,
  });
  @override List<Object?> get props => [fullName, email, phone, password];
}

class AuthOtpRequested extends AuthEvent {
  final String otp;
  const AuthOtpRequested({required this.otp});
  @override List<Object?> get props => [otp];
}

// ─── States ──────────────────────────────────────────────────────────────────

abstract class AuthState extends Equatable {
  const AuthState();
  @override List<Object?> get props => [];
}

class AuthInitial       extends AuthState {}
class AuthLoading       extends AuthState {}

class AuthAuthenticated extends AuthState {
  final UserModel user;
  const AuthAuthenticated(this.user);
  @override List<Object?> get props => [user];
}

class AuthUnauthenticated extends AuthState {}
class AuthOtpRequired     extends AuthState {}

class AuthError extends AuthState {
  final String message;
  const AuthError(this.message);
  @override List<Object?> get props => [message];
}

// ─── BLoC ────────────────────────────────────────────────────────────────────

class AuthBloc extends Bloc<AuthEvent, AuthState> {
  final AuthRepository _repo;

  AuthBloc(this._repo) : super(AuthInitial()) {
    on<AuthCheckRequested>(_onCheckRequested);
    on<AuthLoginRequested>(_onLoginRequested);
    on<AuthRegisterRequested>(_onRegisterRequested);
    on<AuthOtpRequested>(_onOtpRequested);
    on<AuthLogoutRequested>(_onLogoutRequested);
  }

  Future<void> _onCheckRequested(
    AuthCheckRequested event, Emitter<AuthState> emit,
  ) async {
    emit(AuthLoading());
    try {
      final user = await _repo.getCurrentUser();
      if (user != null) {
        emit(AuthAuthenticated(user));
      } else {
        emit(AuthUnauthenticated());
      }
    } catch (_) {
      emit(AuthUnauthenticated());
    }
  }

  Future<void> _onLoginRequested(
    AuthLoginRequested event, Emitter<AuthState> emit,
  ) async {
    emit(AuthLoading());
    try {
      final user = await _repo.login(
        email: event.email, password: event.password,
      );
      emit(AuthAuthenticated(user));
    } catch (e) {
      emit(AuthError(e.toString()));
    }
  }

  Future<void> _onRegisterRequested(
    AuthRegisterRequested event, Emitter<AuthState> emit,
  ) async {
    emit(AuthLoading());
    try {
      await _repo.register(
        fullName: event.fullName, email: event.email,
        phone: event.phone,      password: event.password,
      );
      emit(AuthOtpRequired());
    } catch (e) {
      emit(AuthError(e.toString()));
    }
  }

  Future<void> _onOtpRequested(
    AuthOtpRequested event, Emitter<AuthState> emit,
  ) async {
    emit(AuthLoading());
    try {
      final user = await _repo.verifyOtp(otp: event.otp);
      emit(AuthAuthenticated(user));
    } catch (e) {
      emit(AuthError(e.toString()));
    }
  }

  Future<void> _onLogoutRequested(
    AuthLogoutRequested event, Emitter<AuthState> emit,
  ) async {
    await _repo.logout();
    emit(AuthUnauthenticated());
  }
}
