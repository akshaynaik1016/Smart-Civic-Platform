import 'package:equatable/equatable.dart';
import 'package:flutter_bloc/flutter_bloc.dart';

import '../../data/models/complaint_model.dart';
import '../../data/repositories/complaint_repository.dart';
// ══════════════════════════════════════════════════════════════════════════════
// EVENTS
// ══════════════════════════════════════════════════════════════════════════════

abstract class ComplaintEvent extends Equatable {
  const ComplaintEvent();
  @override
  List<Object?> get props => [];
}

class ComplaintsFetchRequested extends ComplaintEvent {
  final String? status;
  final String? category;
  final String? search;
  final bool refresh;
  const ComplaintsFetchRequested({
    this.status, this.category, this.search, this.refresh = false,
  });
  @override
  List<Object?> get props => [status, category, search, refresh];
}

class ComplaintsLoadMoreRequested extends ComplaintEvent {
  const ComplaintsLoadMoreRequested();
}

class ComplaintDetailRequested extends ComplaintEvent {
  final String complaintId;
  const ComplaintDetailRequested({required this.complaintId});
  @override
  List<Object?> get props => [complaintId];
}

class ComplaintSubmitRequested extends ComplaintEvent {
  final String imagePath;
  final String title;
  final String description;
  final String category;
  final String severity;
  final double latitude;
  final double longitude;
  final String address;
  final double aiConfidence;
  final List<dynamic> boundingBoxes;

  const ComplaintSubmitRequested({
    required this.imagePath,
    required this.title,
    required this.description,
    required this.category,
    required this.severity,
    required this.latitude,
    required this.longitude,
    required this.address,
    required this.aiConfidence,
    required this.boundingBoxes,
  });

  @override
  List<Object?> get props => [
        imagePath, title, description, category,
        severity, latitude, longitude, address,
      ];
}

class ComplaintSupportToggled extends ComplaintEvent {
  final String complaintId;
  const ComplaintSupportToggled({required this.complaintId});
  @override
  List<Object?> get props => [complaintId];
}

class ComplaintVerifyRequested extends ComplaintEvent {
  final String complaintId;
  final bool isResolved;
  const ComplaintVerifyRequested({
    required this.complaintId,
    required this.isResolved,
  });
  @override
  List<Object?> get props => [complaintId, isResolved];
}

// ══════════════════════════════════════════════════════════════════════════════
// STATES
// ══════════════════════════════════════════════════════════════════════════════

abstract class ComplaintState extends Equatable {
  const ComplaintState();
  @override
  List<Object?> get props => [];
}

class ComplaintInitial extends ComplaintState {}

class ComplaintsLoading extends ComplaintState {}

class ComplaintsLoaded extends ComplaintState {
  final List<ComplaintModel> complaints;
  final bool hasMore;
  final bool isLoadingMore;
  final int currentPage;

  const ComplaintsLoaded({
    required this.complaints,
    this.hasMore       = false,
    this.isLoadingMore = false,
    this.currentPage   = 1,
  });

  ComplaintsLoaded copyWith({
    List<ComplaintModel>? complaints,
    bool? hasMore,
    bool? isLoadingMore,
    int?  currentPage,
  }) =>
      ComplaintsLoaded(
        complaints:    complaints    ?? this.complaints,
        hasMore:       hasMore       ?? this.hasMore,
        isLoadingMore: isLoadingMore ?? this.isLoadingMore,
        currentPage:   currentPage   ?? this.currentPage,
      );

  @override
  List<Object?> get props => [complaints, hasMore, isLoadingMore, currentPage];
}

class ComplaintDetailLoading extends ComplaintState {}

class ComplaintDetailLoaded extends ComplaintState {
  final ComplaintModel complaint;
  const ComplaintDetailLoaded(this.complaint);
  @override
  List<Object?> get props => [complaint];
}

class ComplaintSubmitting extends ComplaintState {}

class ComplaintSubmitted extends ComplaintState {
  final String complaintId;
  const ComplaintSubmitted({required this.complaintId});
  @override
  List<Object?> get props => [complaintId];
}

class ComplaintError extends ComplaintState {
  final String message;
  const ComplaintError(this.message);
  @override
  List<Object?> get props => [message];
}

// ══════════════════════════════════════════════════════════════════════════════
// BLOC
// ══════════════════════════════════════════════════════════════════════════════

class ComplaintBloc extends Bloc<ComplaintEvent, ComplaintState> {
  final ComplaintRepository _repo;
  static const int _pageSize = 20;

  ComplaintBloc(this._repo) : super(ComplaintInitial()) {
    on<ComplaintsFetchRequested>(_onFetch);
    on<ComplaintsLoadMoreRequested>(_onLoadMore);
    on<ComplaintDetailRequested>(_onDetail);
    on<ComplaintSubmitRequested>(_onSubmit);
    on<ComplaintSupportToggled>(_onSupport);
    on<ComplaintVerifyRequested>(_onVerify);
  }

  Future<void> _onFetch(
    ComplaintsFetchRequested event,
    Emitter<ComplaintState> emit,
  ) async {
    emit(ComplaintsLoading());
    try {
      final complaints = await _repo.fetchComplaints(
        status: event.status, category: event.category,
        search: event.search, page: 1, pageSize: _pageSize,
      );
      emit(ComplaintsLoaded(
        complaints:  complaints,
        hasMore:     complaints.length == _pageSize,
        currentPage: 1,
      ));
          } catch (e, stack) {
        print("FETCH ERROR:");
        print(e);
        print(stack);

        emit(ComplaintError(_clean(e)));
      }
  }

  Future<void> _onLoadMore(
    ComplaintsLoadMoreRequested event,
    Emitter<ComplaintState> emit,
  ) async {
    final current = state;
    if (current is! ComplaintsLoaded ||
        current.isLoadingMore || !current.hasMore) return;

    emit(current.copyWith(isLoadingMore: true));
    try {
      final nextPage = current.currentPage + 1;
      final more = await _repo.fetchComplaints(page: nextPage, pageSize: _pageSize);
      emit(current.copyWith(
        complaints:    [...current.complaints, ...more],
        hasMore:       more.length == _pageSize,
        isLoadingMore: false,
        currentPage:   nextPage,
      ));
    } catch (_) {
      emit(current.copyWith(isLoadingMore: false));
    }
  }

  Future<void> _onDetail(
    ComplaintDetailRequested event,
    Emitter<ComplaintState> emit,
  ) async {
    emit(ComplaintDetailLoading());
    try {
      final complaint = await _repo.fetchDetail(event.complaintId);
      emit(ComplaintDetailLoaded(complaint));
    } catch (e) {
      emit(ComplaintError(_clean(e)));
    }
  }

  Future<void> _onSubmit(
    ComplaintSubmitRequested event,
    Emitter<ComplaintState> emit,
  ) async {
    emit(ComplaintSubmitting());
    try {
      final complaint = await _repo.submit(
        imagePath:     event.imagePath,
        title:         event.title,
        description:   event.description,
        category:      event.category,
        severity:      event.severity,
        latitude:      event.latitude,
        longitude:     event.longitude,
        address:       event.address,
        aiConfidence:  event.aiConfidence,
        boundingBoxes: event.boundingBoxes,
      );
      emit(ComplaintSubmitted(complaintId: complaint.id));
    } catch (e) {
      emit(ComplaintError(_clean(e)));
    }
  }

  Future<void> _onSupport(
    ComplaintSupportToggled event,
    Emitter<ComplaintState> emit,
  ) async {
    final currentlySupporting = state is ComplaintDetailLoaded
        ? (state as ComplaintDetailLoaded).complaint.isSupporting
        : false;
    try {
      await _repo.toggleSupport(
          event.complaintId, currentlySupporting: currentlySupporting);
      add(ComplaintDetailRequested(complaintId: event.complaintId));
    } catch (e) {
      emit(ComplaintError(_clean(e)));
    }
  }

  Future<void> _onVerify(
    ComplaintVerifyRequested event,
    Emitter<ComplaintState> emit,
  ) async {
    try {
      final updated = await _repo.verifyResolution(
        id: event.complaintId, isResolved: event.isResolved,
      );
      emit(ComplaintDetailLoaded(updated));
    } catch (e) {
      emit(ComplaintError(_clean(e)));
    }
  }

  String _clean(Object e) => e.toString().replaceFirst('Exception: ', '');
}