// ─── Enums ────────────────────────────────────────────────────────────────────

export type UserRole     = 'citizen' | 'officer' | 'admin';
export type UserStatus   = 'active' | 'inactive' | 'suspended' | 'pending_verification';

export type ComplaintStatus =
  | 'submitted' | 'ai_processing' | 'pending_review'
  | 'assigned'  | 'in_progress'   | 'resolved'
  | 'verified'  | 'closed'        | 'rejected';

export type SeverityLevel = 'low' | 'medium' | 'high' | 'critical';

export type IssueCategory =
  | 'pothole' | 'garbage'           | 'water_leakage'
  | 'open_manhole' | 'broken_streetlight' | 'fallen_tree'
  | 'damaged_road_sign' | 'illegal_dumping' | 'other';

export type NotificationType =
  | 'complaint_submitted' | 'complaint_assigned' | 'complaint_status_changed'
  | 'complaint_resolved'  | 'verification_required' | 'system_announcement';

// ─── Models ───────────────────────────────────────────────────────────────────

export interface User {
  id:                  string;
  email:               string;
  phone?:              string;
  fullName:            string;
  role:                UserRole;
  status:              UserStatus;
  avatarUrl?:          string;
  wardId?:             number;
  city:                string;
  emailVerified:       boolean;
  phoneVerified:       boolean;
  totalComplaints:     number;
  resolvedComplaints:  number;
  reputationScore:     number;
  lastLoginAt?:        string;
  createdAt:           string;
}

export interface Officer {
  id:                string;
  userId:            string;
  user:              User;
  badgeNumber:       string;
  department:        string;
  designation?:      string;
  wardIds:           number[];
  categoryIds:       number[];
  isAvailable:       boolean;
  maxComplaints:     number;
  totalAssigned:     number;
  totalResolved:     number;
  avgResolutionDays?: number;
  performanceScore:  number;
  createdAt:         string;
}

export interface ComplaintImage {
  id:            string;
  cdnUrl?:       string;
  thumbnailUrl?: string;
  isPrimary:     boolean;
  isResolution:  boolean;
  caption?:      string;
  boundingBoxes?: BoundingBox[];
  createdAt:     string;
}

export interface BoundingBox {
  label:      string;
  confidence: number;
  bbox:       [number, number, number, number];
}

export interface StatusHistory {
  id:         string;
  fromStatus: ComplaintStatus | null;
  toStatus:   ComplaintStatus;
  changedBy:  User;
  notes?:     string;
  createdAt:  string;
}

export interface AIAnalysis {
  id:                   string;
  detectedCategory?:    IssueCategory;
  confidenceScore:      number;
  severityPredicted:    SeverityLevel;
  generatedDescription?: string;
  isDuplicate:          boolean;
  similarComplaintIds?: string[];
  modelName:            string;
  modelVersion:         string;
  inferenceTimeMs?:     number;
  createdAt:            string;
}

export interface Resolution {
  id:               string;
  officerId:        string;
  officer:          Officer;
  resolutionType?:  string;
  workDone:         string;
  materialUsed?:    string;
  estimatedCost?:   number;
  actualCost?:      number;
  scheduledDate?:   string;
  startedAt?:       string;
  completedAt?:     string;
  citizenFeedback?: string;
  citizenRating?:   number;
  createdAt:        string;
}

export interface Complaint {
  id:                 string;
  complaintNumber:    string;
  citizenId:          string;
  citizen:            User;
  officerId?:         string;
  officer?:           Officer;
  categoryId:         number;
  category:           IssueCategory;
  status:             ComplaintStatus;
  severity:           SeverityLevel;
  priorityScore:      number;
  latitude:           number;
  longitude:          number;
  address?:           string;
  wardId?:            number;
  landmark?:          string;
  title:              string;
  description:        string;
  aiDescription?:     string;
  tags?:              string[];
  isDuplicate:        boolean;
  parentComplaintId?: string;
  supportCount:       number;
  aiConfidence?:      number;
  aiProcessedAt?:     string;
  resolvedAt?:        string;
  resolutionNotes?:   string;
  citizenVerified:    boolean;
  citizenRating?:     number;
  slaDeadline?:       string;
  slaBreached:        boolean;
  images:             ComplaintImage[];
  statusHistory:      StatusHistory[];
  aiAnalysis?:        AIAnalysis;
  resolution?:        Resolution;
  createdAt:          string;
  updatedAt:          string;
}

// ─── API Payloads ─────────────────────────────────────────────────────────────

export interface PaginatedResponse<T> {
  items:    T[];
  total:    number;
  page:     number;
  pageSize: number;
  pages:    number;
}

export interface ComplaintFilters {
  status?:    ComplaintStatus;
  severity?:  SeverityLevel;
  category?:  IssueCategory;
  wardId?:    number;
  officerId?: string;
  dateFrom?:  string;
  dateTo?:    string;
  search?:    string;
  page?:      number;
  pageSize?:  number;
  sortBy?:    string;
  sortOrder?: 'asc' | 'desc';
}

// ─── Analytics ────────────────────────────────────────────────────────────────

export interface DashboardStats {
  totalComplaints:      number;
  openComplaints:       number;
  resolvedToday:        number;
  avgResolutionDays:    number;
  slaBreachRate:        number;
  citizenSatisfaction:  number;
  totalCitizens:        number;
  activeOfficers:       number;
  changeVsPrevWeek: {
    totalComplaints:   number;
    openComplaints:    number;
    resolvedToday:     number;
    avgResolutionDays: number;
  };
}

export interface CategoryCount {
  category:    IssueCategory;
  count:       number;
  resolved:    number;
  pending:     number;
  percentage:  number;
}

export interface MonthlyTrend {
  month:       string;   // "Jan", "Feb" …
  submitted:   number;
  resolved:    number;
  pending:     number;
}

export interface WardSummary {
  wardId:          number;
  wardName:        string;
  totalComplaints: number;
  resolved:        number;
  pending:         number;
  resolutionRate:  number;
  lat:             number;
  lng:             number;
}

export interface HeatmapPoint {
  lat:    number;
  lng:    number;
  weight: number;
}

export interface SeverityDistribution {
  severity:   SeverityLevel;
  count:      number;
  percentage: number;
}

export interface OfficerPerformance {
  officerId:          string;
  officerName:        string;
  badgeNumber:        string;
  totalAssigned:      number;
  totalResolved:      number;
  avgResolutionDays:  number;
  performanceScore:   number;
  satisfactionRating: number;
}

// ─── Auth ─────────────────────────────────────────────────────────────────────

export interface AuthTokens {
  accessToken:  string;
  refreshToken: string;
  tokenType:    string;
  expiresIn:    number;
}

export interface LoginRequest {
  email:    string;
  password: string;
}

export interface AuthState {
  user:      User | null;
  tokens:    AuthTokens | null;
  isLoading: boolean;
  error:     string | null;
}

// ─── Notifications ────────────────────────────────────────────────────────────

export interface Notification {
  id:          string;
  type:        NotificationType;
  title:       string;
  body:        string;
  read:        boolean;
  complaintId?: string;
  createdAt:   string;
}
