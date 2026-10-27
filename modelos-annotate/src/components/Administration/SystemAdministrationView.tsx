import React, { useState } from 'react';
import {
  Users,
  Cpu,
  Sliders,
  Activity,
  Plus,
  Search,
  CheckCircle2,
  X,
  Shield,
  Server,
  RefreshCw,
  Edit2,
  Trash2,
  Menu,
  Download,
  AlertTriangle,
  SlidersHorizontal,
} from 'lucide-react';

interface EnterpriseUser {
  id: string;
  name: string;
  email: string;
  role: 'Admin' | 'Qa Lead' | 'Reviewer' | 'Annotator' | 'Requester' | 'Guest';
  department: string;
  assignedProjects: string[];
  status: 'Active' | 'Suspended' | 'Pending';
}

interface InferenceEngine {
  id: string;
  name: string;
  model: string;
  endpoint: string;
  latencyMs: number;
  status: 'Operational' | 'Degraded' | 'Offline';
  throughputRps: number;
  tokenQuotaUsedPercent: number;
  lastPing: string;
}

interface AuditLogEntry {
  id: string;
  timestamp: string;
  actor: string;
  action: string;
  target: string;
  ipAddress: string;
  status: 'Success' | 'Warning' | 'Blocked';
}

interface SystemAdministrationViewProps {
  onToggleSidebar?: () => void;
  onToast?: (message: string) => void;
}

export const SystemAdministrationView: React.FC<SystemAdministrationViewProps> = ({
  onToggleSidebar,
  onToast,
}) => {
  const [activeTab, setActiveTab] = useState<
    'rbac' | 'engines' | 'thresholds' | 'audit'
  >('rbac');

  // Enterprise identities matching user's exact specification
  const [identities, setIdentities] = useState<EnterpriseUser[]>([
    {
      id: 'usr-1',
      name: 'Elena Rostova',
      email: 'elena.rostova@annotateai.internal',
      role: 'Admin',
      department: 'Platform Architecture & AI Ops',
      assignedProjects: ['proj_traffic', 'proj_sentiment', 'proj_callcenter'],
      status: 'Active',
    },
    {
      id: 'usr-2',
      name: 'Marcus Vance',
      email: 'marcus.vance@annotateai.internal',
      role: 'Qa Lead',
      department: 'Quality Assurance & Standards',
      assignedProjects: ['proj_traffic', 'proj_sentiment', 'proj_callcenter'],
      status: 'Active',
    },
    {
      id: 'usr-3',
      name: 'Sarah Chen',
      email: 'sarah.chen@annotateai.internal',
      role: 'Reviewer',
      department: 'HITL Review Operations',
      assignedProjects: ['proj_traffic', 'proj_sentiment'],
      status: 'Active',
    },
    {
      id: 'usr-4',
      name: 'Alex Rivera',
      email: 'alex.rivera@annotateai.internal',
      role: 'Annotator',
      department: 'Data Labelling Core',
      assignedProjects: ['proj_traffic', 'proj_callcenter'],
      status: 'Active',
    },
    {
      id: 'usr-5',
      name: 'Rachel Green',
      email: 'rachel.green@annotateai.internal',
      role: 'Requester',
      department: 'Autonomous Mobility R&D',
      assignedProjects: ['proj_traffic'],
      status: 'Active',
    },
    {
      id: 'usr-6',
      name: 'Guest Observer',
      email: 'observer@external_auditor.com',
      role: 'Guest',
      department: 'External Compliance',
      assignedProjects: ['proj_traffic', 'proj_sentiment'],
      status: 'Active',
    },
  ]);

  // AI Inference Engines
  const [inferenceEngines, setInferenceEngines] = useState<InferenceEngine[]>([
    {
      id: 'eng-1',
      name: 'Gemini 2.5 Flash Grounded',
      model: 'models/gemini-2.5-flash',
      endpoint: 'https://generativelanguage.googleapis.com/v1beta',
      latencyMs: 168,
      status: 'Operational',
      throughputRps: 42.5,
      tokenQuotaUsedPercent: 38,
      lastPing: '2s ago',
    },
    {
      id: 'eng-2',
      name: 'Gemini 2.5 Pro Vision High-Res',
      model: 'models/gemini-2.5-pro',
      endpoint: 'https://generativelanguage.googleapis.com/v1beta',
      latencyMs: 312,
      status: 'Operational',
      throughputRps: 18.2,
      tokenQuotaUsedPercent: 64,
      lastPing: '4s ago',
    },
    {
      id: 'eng-3',
      name: 'YOLOv8x Object Detector Cluster',
      model: 'yolov8x-coco-v2',
      endpoint: 'https://inference.internal.annotateai/v1/detect',
      latencyMs: 44,
      status: 'Operational',
      throughputRps: 120.0,
      tokenQuotaUsedPercent: 29,
      lastPing: '1s ago',
    },
    {
      id: 'eng-4',
      name: 'DistilBERT Clinical NER Extractor',
      model: 'distilbert-ner-v4',
      endpoint: 'https://inference.internal.annotateai/v1/ner',
      latencyMs: 58,
      status: 'Operational',
      throughputRps: 85.4,
      tokenQuotaUsedPercent: 41,
      lastPing: '5s ago',
    },
    {
      id: 'eng-5',
      name: 'RoBERTa Multi-Aspect Sentiment',
      model: 'roberta-sentiment-aspect-v1',
      endpoint: 'https://inference.internal.annotateai/v1/sentiment',
      latencyMs: 49,
      status: 'Operational',
      throughputRps: 94.2,
      tokenQuotaUsedPercent: 22,
      lastPing: '3s ago',
    },
  ]);

  // Global Quality Thresholds
  const [thresholds, setThresholds] = useState({
    minConfidenceAutoAccept: 0.85,
    iouOverlapThreshold: 0.7,
    minNerF1Score: 0.88,
    doubleReviewConsensus: 0.9,
    piiMaskingPrivacyCutoff: 0.95,
    maxDailyRejectionsPercent: 12,
  });

  // Audit Logs
  const [auditLogs] = useState<AuditLogEntry[]>([
    {
      id: 'log-1',
      timestamp: '2026-09-21 14:12:05',
      actor: 'Elena Rostova',
      action: 'MODIFY_ROLE_PERMISSION',
      target: 'Sarah Chen (Reviewer -> Full Approver)',
      ipAddress: '10.240.12.84',
      status: 'Success',
    },
    {
      id: 'log-2',
      timestamp: '2026-09-21 13:45:19',
      actor: 'Marcus Vance',
      action: 'APPROVE_QA_BATCH',
      target: 'proj_traffic / batch_0884 (48 assets)',
      ipAddress: '10.240.14.22',
      status: 'Success',
    },
    {
      id: 'log-3',
      timestamp: '2026-09-21 12:30:44',
      actor: 'System Automation',
      action: 'AUTO_TRIGGER_DOUBLE_REVIEW',
      target: 'asset_frame_0442 (IoU below 0.70)',
      ipAddress: '127.0.0.1 (Internal)',
      status: 'Warning',
    },
    {
      id: 'log-4',
      timestamp: '2026-09-21 11:15:30',
      actor: 'observer@external_auditor.com',
      action: 'EXPORT_COMPLIANCE_REPORT',
      target: 'ISO-27001 Data Masking Audit (Q3)',
      ipAddress: '198.51.100.45',
      status: 'Success',
    },
    {
      id: 'log-5',
      timestamp: '2026-09-21 09:22:11',
      actor: 'External Origin 203.0.113.12',
      action: 'UNAUTHORIZED_ACCESS_ATTEMPT',
      target: '/api/v1/admin/inference-keys',
      ipAddress: '203.0.113.12',
      status: 'Blocked',
    },
  ]);

  // Invite Member Modal state
  const [isInviteModalOpen, setIsInviteModalOpen] = useState(false);
  const [inviteForm, setInviteForm] = useState({
    name: '',
    email: '',
    role: 'Annotator' as EnterpriseUser['role'],
    department: 'Data Labelling Core',
    assignedProjects: 'proj_traffic',
  });

  // Filter state for user table
  const [userSearchQuery, setUserSearchQuery] = useState('');

  const filteredIdentities = identities.filter(
    (u) =>
      u.name.toLowerCase().includes(userSearchQuery.toLowerCase()) ||
      u.email.toLowerCase().includes(userSearchQuery.toLowerCase()) ||
      u.department.toLowerCase().includes(userSearchQuery.toLowerCase()) ||
      u.role.toLowerCase().includes(userSearchQuery.toLowerCase())
  );

  const handleInviteSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    if (!inviteForm.name || !inviteForm.email) {
      onToast?.('Please enter both name and email');
      return;
    }

    const projectsList = inviteForm.assignedProjects
      .split(',')
      .map((p) => p.trim())
      .filter(Boolean);

    const newUser: EnterpriseUser = {
      id: `usr-${Date.now()}`,
      name: inviteForm.name,
      email: inviteForm.email,
      role: inviteForm.role,
      department: inviteForm.department,
      assignedProjects: projectsList.length > 0 ? projectsList : ['proj_traffic'],
      status: 'Active',
    };

    setIdentities((prev) => [...prev, newUser]);
    setIsInviteModalOpen(false);
    setInviteForm({
      name: '',
      email: '',
      role: 'Annotator',
      department: 'Data Labelling Core',
      assignedProjects: 'proj_traffic',
    });
    onToast?.(`Invited ${newUser.name} as ${newUser.role}`);
  };

  const handleToggleUserStatus = (userId: string) => {
    setIdentities((prev) =>
      prev.map((u) => {
        if (u.id === userId) {
          const nextStatus = u.status === 'Active' ? 'Suspended' : 'Active';
          onToast?.(`User ${u.name} set to ${nextStatus}`);
          return { ...u, status: nextStatus };
        }
        return u;
      })
    );
  };

  const handleSaveThresholds = () => {
    onToast?.('Global Quality Thresholds updated successfully');
  };

  const handlePingEngine = (engineName: string) => {
    onToast?.(`Inference test to ${engineName}: 200 OK (Latency: 42ms)`);
  };

  return (
    <div
      id="system-administration-governance-screen"
      className="flex flex-1 flex-col min-w-0 bg-[#F8FAFC] min-h-screen text-slate-800"
    >
      {/* Top Bar with Mobile Menu Toggle */}
      <div className="bg-white border-b border-slate-200/80 px-4 sm:px-8 py-3.5 flex items-center justify-between">
        <div className="flex items-center gap-3">
          {onToggleSidebar && (
            <button
              id="admin-toggle-sidebar"
              onClick={onToggleSidebar}
              className="lg:hidden p-2 text-slate-600 hover:text-slate-900 hover:bg-slate-100 rounded-lg cursor-pointer"
              title="Open Navigation"
            >
              <Menu className="h-5 w-5" />
            </button>
          )}
          <div className="flex items-center gap-2">
            <span className="text-xs font-semibold text-slate-500 uppercase tracking-wider">
              Administration
            </span>
            <span className="text-slate-300">/</span>
            <span className="text-xs font-semibold text-slate-800">
              System Governance
            </span>
          </div>
        </div>
        <div className="flex items-center gap-2.5 text-xs text-slate-500 font-medium">
          <span className="flex items-center gap-1.5 text-emerald-600 bg-emerald-50 px-2.5 py-1 rounded-full border border-emerald-200 font-semibold">
            <span className="h-2 w-2 rounded-full bg-emerald-500 animate-pulse" />
            Security Guardrails Active
          </span>
        </div>
      </div>

      {/* Main Container */}
      <main className="flex-1 px-4 sm:px-8 py-7 max-w-[1500px] w-full mx-auto">
        {/* Header Section from Image */}
        <div className="mb-6">
          <div className="flex flex-wrap items-center gap-2.5 mb-1.5">
            <h1
              id="admin-page-title"
              className="text-2xl sm:text-3xl font-extrabold tracking-tight text-slate-900"
            >
              System Administration & Governance
            </h1>
            <span
              id="admin-only-badge"
              className="inline-flex items-center px-2 py-0.5 rounded text-xs font-bold bg-[#FDE8E8] text-[#E31837] tracking-wider uppercase border border-red-200"
            >
              PROJECT MANAGER ONLY
            </span>
          </div>
          <p
            id="admin-page-subtitle"
            className="text-sm text-slate-600 max-w-4xl"
          >
            Configure access control, AI inference endpoints, system-wide quality
            thresholds, and compliance logs
          </p>
        </div>

        {/* Tab Navigation Row matching Image */}
        <div
          id="admin-tab-nav"
          className="flex items-center gap-8 border-b border-slate-200 mb-6 overflow-x-auto no-scrollbar"
        >
          <button
            id="tab-user-team-rbac"
            onClick={() => setActiveTab('rbac')}
            className={`flex items-center gap-2 pb-3 text-sm font-semibold transition-all whitespace-nowrap cursor-pointer border-b-2 ${
              activeTab === 'rbac'
                ? 'border-blue-600 text-blue-600'
                : 'border-transparent text-slate-500 hover:text-slate-800'
            }`}
          >
            <Users className="h-4 w-4" />
            <span>User & Team RBAC</span>
          </button>

          <button
            id="tab-ai-inference-engines"
            onClick={() => setActiveTab('engines')}
            className={`flex items-center gap-2 pb-3 text-sm font-semibold transition-all whitespace-nowrap cursor-pointer border-b-2 ${
              activeTab === 'engines'
                ? 'border-blue-600 text-blue-600'
                : 'border-transparent text-slate-500 hover:text-slate-800'
            }`}
          >
            <Cpu className="h-4 w-4" />
            <span>AI Inference Engines</span>
          </button>

          <button
            id="tab-global-quality-thresholds"
            onClick={() => setActiveTab('thresholds')}
            className={`flex items-center gap-2 pb-3 text-sm font-semibold transition-all whitespace-nowrap cursor-pointer border-b-2 ${
              activeTab === 'thresholds'
                ? 'border-blue-600 text-blue-600'
                : 'border-transparent text-slate-500 hover:text-slate-800'
            }`}
          >
            <SlidersHorizontal className="h-4 w-4" />
            <span>Global Quality Thresholds</span>
          </button>

          <button
            id="tab-system-audit-logs"
            onClick={() => setActiveTab('audit')}
            className={`flex items-center gap-2 pb-3 text-sm font-semibold transition-all whitespace-nowrap cursor-pointer border-b-2 ${
              activeTab === 'audit'
                ? 'border-blue-600 text-blue-600'
                : 'border-transparent text-slate-500 hover:text-slate-800'
            }`}
          >
            <Activity className="h-4 w-4" />
            <span>System Audit Logs</span>
          </button>
        </div>

        {/* TAB 1: User & Team RBAC (Exact replication of screenshot) */}
        {activeTab === 'rbac' && (
          <div
            id="admin-rbac-container"
            className="rounded-xl border border-slate-200/90 bg-white shadow-xs overflow-hidden"
          >
            {/* Card Header Row */}
            <div className="flex flex-col sm:flex-row sm:items-center justify-between p-5 border-b border-slate-100 gap-4">
              <div className="flex items-center gap-3">
                <h2
                  id="enterprise-identities-title"
                  className="text-xs sm:text-sm font-bold tracking-wider text-slate-800 uppercase"
                >
                  ENTERPRISE IDENTITIES ({filteredIdentities.length})
                </h2>
                <div className="relative">
                  <Search className="absolute left-2.5 top-1/2 -translate-y-1/2 h-3.5 w-3.5 text-slate-400" />
                  <input
                    type="text"
                    placeholder="Filter members..."
                    value={userSearchQuery}
                    onChange={(e) => setUserSearchQuery(e.target.value)}
                    className="pl-8 pr-3 py-1 text-xs rounded-lg border border-slate-200 bg-slate-50 text-slate-800 placeholder-slate-400 focus:bg-white focus:border-blue-500 focus:outline-hidden transition"
                  />
                </div>
              </div>

              <button
                id="btn-invite-member"
                onClick={() => setIsInviteModalOpen(true)}
                className="inline-flex items-center justify-center gap-1.5 rounded-lg bg-blue-600 hover:bg-blue-700 active:bg-blue-800 text-white px-4 py-2 text-xs sm:text-sm font-medium transition cursor-pointer shadow-xs"
              >
                <Plus className="h-4 w-4" />
                <span>Invite Member</span>
              </button>
            </div>

            {/* Table Area matching Screenshot */}
            <div className="overflow-x-auto">
              <table
                id="enterprise-identities-table"
                className="w-full border-collapse text-left text-sm"
              >
                <thead>
                  <tr className="border-b border-slate-200 bg-white">
                    <th className="py-3.5 px-6 text-[11px] font-bold uppercase tracking-wider text-slate-500">
                      USER
                    </th>
                    <th className="py-3.5 px-6 text-[11px] font-bold uppercase tracking-wider text-slate-500">
                      ROLE
                    </th>
                    <th className="py-3.5 px-6 text-[11px] font-bold uppercase tracking-wider text-slate-500">
                      DEPARTMENT
                    </th>
                    <th className="py-3.5 px-6 text-[11px] font-bold uppercase tracking-wider text-slate-500">
                      ASSIGNED PROJECTS
                    </th>
                    <th className="py-3.5 px-6 text-[11px] font-bold uppercase tracking-wider text-slate-500 text-right sm:text-left">
                      STATUS
                    </th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-slate-100">
                  {filteredIdentities.map((user) => (
                    <tr
                      key={user.id}
                      id={`user-row-${user.id}`}
                      className="hover:bg-slate-50/70 transition-colors"
                    >
                      {/* USER Column */}
                      <td className="py-4 px-6 align-middle">
                        <div className="flex flex-col">
                          <span className="font-bold text-slate-900 text-sm">
                            {user.name}
                          </span>
                          <span className="text-xs text-slate-400 font-normal">
                            {user.email}
                          </span>
                        </div>
                      </td>

                      {/* ROLE Column */}
                      <td className="py-4 px-6 align-middle">
                        <span
                          id={`badge-role-${user.id}`}
                          className="inline-flex items-center px-3 py-1 rounded-md text-xs font-medium bg-[#F1F5F9] text-slate-700 border border-slate-200/80"
                        >
                          {user.role}
                        </span>
                      </td>

                      {/* DEPARTMENT Column */}
                      <td className="py-4 px-6 align-middle text-slate-600 text-xs sm:text-sm font-normal">
                        {user.department}
                      </td>

                      {/* ASSIGNED PROJECTS Column */}
                      <td className="py-4 px-6 align-middle">
                        <span className="font-mono text-xs text-slate-500">
                          {user.assignedProjects.join(', ')}
                        </span>
                      </td>

                      {/* STATUS Column */}
                      <td className="py-4 px-6 align-middle text-right sm:text-left">
                        <button
                          id={`btn-status-${user.id}`}
                          onClick={() => handleToggleUserStatus(user.id)}
                          title="Click to toggle active status"
                          className="group inline-flex items-center gap-1.5 px-3 py-0.5 rounded-full text-xs font-semibold bg-emerald-50 text-emerald-700 border border-emerald-200/90 cursor-pointer hover:bg-emerald-100 transition"
                        >
                          <span className="h-1.5 w-1.5 rounded-full bg-emerald-500" />
                          <span>{user.status}</span>
                        </button>
                      </td>
                    </tr>
                  ))}
                  {filteredIdentities.length === 0 && (
                    <tr>
                      <td
                        colSpan={5}
                        className="py-12 text-center text-slate-400 text-xs"
                      >
                        No enterprise identities matching &quot;{userSearchQuery}&quot;
                      </td>
                    </tr>
                  )}
                </tbody>
              </table>
            </div>
          </div>
        )}

        {/* TAB 2: AI Inference Engines */}
        {activeTab === 'engines' && (
          <div
            id="admin-engines-container"
            className="space-y-4"
          >
            <div className="rounded-xl border border-slate-200/90 bg-white p-5 shadow-xs">
              <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-4 pb-4 border-b border-slate-100">
                <div>
                  <h2 className="text-sm font-bold tracking-wider text-slate-800 uppercase">
                    ACTIVE INFERENCE ENDPOINTS ({inferenceEngines.length})
                  </h2>
                  <p className="text-xs text-slate-500 mt-0.5">
                    Centralized AI orchestration, latency SLAs, and token rate limits
                  </p>
                </div>
                <button
                  onClick={() => {
                    onToast?.('Refreshed AI endpoint connectivity status');
                  }}
                  className="inline-flex items-center gap-1.5 px-3 py-1.5 rounded-lg border border-slate-200 text-xs font-medium text-slate-700 hover:bg-slate-50 cursor-pointer"
                >
                  <RefreshCw className="h-3.5 w-3.5 text-slate-500" />
                  <span>Test All Endpoints</span>
                </button>
              </div>

              <div className="divide-y divide-slate-100 mt-2">
                {inferenceEngines.map((engine) => (
                  <div
                    key={engine.id}
                    className="py-4 flex flex-col md:flex-row md:items-center justify-between gap-4 hover:bg-slate-50/50 rounded-lg px-2 transition"
                  >
                    <div className="flex items-start gap-3">
                      <div className="p-2.5 rounded-lg bg-blue-50 text-blue-600 border border-blue-100 shrink-0">
                        <Server className="h-4 w-4" />
                      </div>
                      <div>
                        <div className="flex items-center gap-2">
                          <span className="font-bold text-slate-900 text-sm">
                            {engine.name}
                          </span>
                          <span className="px-2 py-0.5 rounded text-[11px] font-semibold bg-emerald-50 text-emerald-700 border border-emerald-200">
                            {engine.status}
                          </span>
                        </div>
                        <div className="text-xs font-mono text-slate-500 mt-1">
                          {engine.endpoint} • <span className="text-slate-400">Model: {engine.model}</span>
                        </div>
                      </div>
                    </div>

                    <div className="flex items-center gap-6">
                      <div className="text-right">
                        <span className="text-[11px] font-semibold uppercase text-slate-400 block">
                          Latency
                        </span>
                        <span className="text-xs font-bold text-slate-800 font-mono">
                          {engine.latencyMs} ms
                        </span>
                      </div>
                      <div className="text-right">
                        <span className="text-[11px] font-semibold uppercase text-slate-400 block">
                          Throughput
                        </span>
                        <span className="text-xs font-bold text-slate-800 font-mono">
                          {engine.throughputRps} rps
                        </span>
                      </div>
                      <div className="w-24 text-right">
                        <span className="text-[11px] font-semibold uppercase text-slate-400 block">
                          Quota ({engine.tokenQuotaUsedPercent}%)
                        </span>
                        <div className="h-1.5 w-full bg-slate-100 rounded-full mt-1 overflow-hidden">
                          <div
                            className={`h-full rounded-full ${
                              engine.tokenQuotaUsedPercent > 80
                                ? 'bg-amber-500'
                                : 'bg-blue-600'
                            }`}
                            style={{ width: `${engine.tokenQuotaUsedPercent}%` }}
                          />
                        </div>
                      </div>
                      <button
                        onClick={() => handlePingEngine(engine.name)}
                        className="px-3 py-1.5 rounded-lg bg-slate-100 hover:bg-slate-200 text-slate-700 text-xs font-medium cursor-pointer transition"
                      >
                        Ping SLA
                      </button>
                    </div>
                  </div>
                ))}
              </div>
            </div>
          </div>
        )}

        {/* TAB 3: Global Quality Thresholds */}
        {activeTab === 'thresholds' && (
          <div
            id="admin-thresholds-container"
            className="rounded-xl border border-slate-200/90 bg-white p-6 shadow-xs max-w-4xl"
          >
            <div className="pb-4 border-b border-slate-100 mb-6">
              <h2 className="text-sm font-bold tracking-wider text-slate-800 uppercase">
                SYSTEM-WIDE QUALITY & CONSENSUS GATES
              </h2>
              <p className="text-xs text-slate-500 mt-0.5">
                Automated gates dictate when an asset passes straight to production vs. triggers human annotator review
              </p>
            </div>

            <div className="space-y-6">
              {/* Threshold 1 */}
              <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-4 p-4 rounded-xl bg-slate-50/70 border border-slate-100">
                <div className="max-w-md">
                  <span className="font-bold text-slate-900 text-sm block">
                    AI Auto-Accept Confidence Cutoff
                  </span>
                  <span className="text-xs text-slate-500">
                    Predictions scoring above this threshold bypass initial human review directly to QA sampling.
                  </span>
                </div>
                <div className="flex items-center gap-3">
                  <input
                    type="range"
                    min="0.5"
                    max="0.99"
                    step="0.01"
                    value={thresholds.minConfidenceAutoAccept}
                    onChange={(e) =>
                      setThresholds({
                        ...thresholds,
                        minConfidenceAutoAccept: parseFloat(e.target.value),
                      })
                    }
                    className="w-36 accent-blue-600 cursor-pointer"
                  />
                  <span className="font-mono text-xs font-bold bg-white px-2.5 py-1 rounded border border-slate-200 text-blue-600 min-w-[54px] text-center">
                    {(thresholds.minConfidenceAutoAccept * 100).toFixed(0)}%
                  </span>
                </div>
              </div>

              {/* Threshold 2 */}
              <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-4 p-4 rounded-xl bg-slate-50/70 border border-slate-100">
                <div className="max-w-md">
                  <span className="font-bold text-slate-900 text-sm block">
                    Object Detection IoU Agreement
                  </span>
                  <span className="text-xs text-slate-500">
                    Intersection over Union required between AI proposal and human boundary before flagging deviation.
                  </span>
                </div>
                <div className="flex items-center gap-3">
                  <input
                    type="range"
                    min="0.4"
                    max="0.95"
                    step="0.05"
                    value={thresholds.iouOverlapThreshold}
                    onChange={(e) =>
                      setThresholds({
                        ...thresholds,
                        iouOverlapThreshold: parseFloat(e.target.value),
                      })
                    }
                    className="w-36 accent-blue-600 cursor-pointer"
                  />
                  <span className="font-mono text-xs font-bold bg-white px-2.5 py-1 rounded border border-slate-200 text-blue-600 min-w-[54px] text-center">
                    {(thresholds.iouOverlapThreshold * 100).toFixed(0)}%
                  </span>
                </div>
              </div>

              {/* Threshold 3 */}
              <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-4 p-4 rounded-xl bg-slate-50/70 border border-slate-100">
                <div className="max-w-md">
                  <span className="font-bold text-slate-900 text-sm block">
                    PII Masking Privacy Strictness
                  </span>
                  <span className="text-xs text-slate-500">
                    Confidence threshold for automated redaction of faces, license plates, and identification numbers.
                  </span>
                </div>
                <div className="flex items-center gap-3">
                  <input
                    type="range"
                    min="0.8"
                    max="0.99"
                    step="0.01"
                    value={thresholds.piiMaskingPrivacyCutoff}
                    onChange={(e) =>
                      setThresholds({
                        ...thresholds,
                        piiMaskingPrivacyCutoff: parseFloat(e.target.value),
                      })
                    }
                    className="w-36 accent-blue-600 cursor-pointer"
                  />
                  <span className="font-mono text-xs font-bold bg-white px-2.5 py-1 rounded border border-slate-200 text-emerald-600 min-w-[54px] text-center">
                    {(thresholds.piiMaskingPrivacyCutoff * 100).toFixed(0)}%
                  </span>
                </div>
              </div>

              {/* Threshold 4 */}
              <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-4 p-4 rounded-xl bg-slate-50/70 border border-slate-100">
                <div className="max-w-md">
                  <span className="font-bold text-slate-900 text-sm block">
                    Double-Blind Review Consensus Trigger
                  </span>
                  <span className="text-xs text-slate-500">
                    If two human reviewers differ by more than this ratio, escalate automatically to QA Lead.
                  </span>
                </div>
                <div className="flex items-center gap-3">
                  <input
                    type="range"
                    min="0.7"
                    max="0.99"
                    step="0.01"
                    value={thresholds.doubleReviewConsensus}
                    onChange={(e) =>
                      setThresholds({
                        ...thresholds,
                        doubleReviewConsensus: parseFloat(e.target.value),
                      })
                    }
                    className="w-36 accent-blue-600 cursor-pointer"
                  />
                  <span className="font-mono text-xs font-bold bg-white px-2.5 py-1 rounded border border-slate-200 text-blue-600 min-w-[54px] text-center">
                    {(thresholds.doubleReviewConsensus * 100).toFixed(0)}%
                  </span>
                </div>
              </div>

              <div className="pt-4 flex justify-end">
                <button
                  id="btn-save-thresholds"
                  onClick={handleSaveThresholds}
                  className="px-5 py-2.5 rounded-lg bg-blue-600 hover:bg-blue-700 text-white font-semibold text-xs sm:text-sm cursor-pointer shadow-xs transition"
                >
                  Save Global Thresholds
                </button>
              </div>
            </div>
          </div>
        )}

        {/* TAB 4: System Audit Logs */}
        {activeTab === 'audit' && (
          <div
            id="admin-audit-container"
            className="rounded-xl border border-slate-200/90 bg-white shadow-xs overflow-hidden"
          >
            <div className="flex items-center justify-between p-5 border-b border-slate-100">
              <div>
                <h2 className="text-xs sm:text-sm font-bold tracking-wider text-slate-800 uppercase">
                  COMPLIANCE & SYSTEM AUDIT TRAIL ({auditLogs.length})
                </h2>
                <p className="text-xs text-slate-500 mt-0.5">
                  Immutable SOC2 Type II & GDPR compliant action logs
                </p>
              </div>
              <button
                onClick={() => onToast?.('Exported audit trail to audit_log_2026.csv')}
                className="inline-flex items-center gap-1.5 px-3 py-1.5 rounded-lg border border-slate-200 text-xs font-medium text-slate-700 hover:bg-slate-50 cursor-pointer"
              >
                <Download className="h-3.5 w-3.5 text-slate-500" />
                <span>Export CSV</span>
              </button>
            </div>

            <div className="overflow-x-auto">
              <table className="w-full border-collapse text-left text-sm">
                <thead>
                  <tr className="border-b border-slate-200 bg-slate-50/60">
                    <th className="py-3 px-6 text-[11px] font-bold uppercase tracking-wider text-slate-500">
                      TIMESTAMP
                    </th>
                    <th className="py-3 px-6 text-[11px] font-bold uppercase tracking-wider text-slate-500">
                      ACTOR
                    </th>
                    <th className="py-3 px-6 text-[11px] font-bold uppercase tracking-wider text-slate-500">
                      ACTION
                    </th>
                    <th className="py-3 px-6 text-[11px] font-bold uppercase tracking-wider text-slate-500">
                      TARGET ENTITY
                    </th>
                    <th className="py-3 px-6 text-[11px] font-bold uppercase tracking-wider text-slate-500">
                      IP ADDRESS
                    </th>
                    <th className="py-3 px-6 text-[11px] font-bold uppercase tracking-wider text-slate-500">
                      STATUS
                    </th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-slate-100">
                  {auditLogs.map((log) => (
                    <tr key={log.id} className="hover:bg-slate-50/50">
                      <td className="py-3.5 px-6 font-mono text-xs text-slate-500">
                        {log.timestamp}
                      </td>
                      <td className="py-3.5 px-6 font-medium text-xs text-slate-900">
                        {log.actor}
                      </td>
                      <td className="py-3.5 px-6 font-mono text-xs font-semibold text-slate-700">
                        {log.action}
                      </td>
                      <td className="py-3.5 px-6 text-xs text-slate-600">
                        {log.target}
                      </td>
                      <td className="py-3.5 px-6 font-mono text-xs text-slate-400">
                        {log.ipAddress}
                      </td>
                      <td className="py-3.5 px-6">
                        <span
                          className={`inline-flex items-center px-2.5 py-0.5 rounded-full text-[11px] font-semibold ${
                            log.status === 'Success'
                              ? 'bg-emerald-50 text-emerald-700 border border-emerald-200'
                              : log.status === 'Warning'
                              ? 'bg-amber-50 text-amber-700 border border-amber-200'
                              : 'bg-red-50 text-red-700 border border-red-200'
                          }`}
                        >
                          {log.status}
                        </span>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </div>
        )}
      </main>

      {/* Invite Member Modal */}
      {isInviteModalOpen && (
        <div
          id="invite-member-modal-backdrop"
          className="fixed inset-0 z-50 flex items-center justify-center bg-slate-900/40 backdrop-blur-xs p-4"
        >
          <div
            id="invite-member-modal"
            className="w-full max-w-md rounded-2xl bg-white p-6 shadow-2xl border border-slate-100 animate-in fade-in zoom-in-95 duration-150"
          >
            <div className="flex items-center justify-between pb-3 border-b border-slate-100">
              <div className="flex items-center gap-2">
                <div className="p-2 rounded-lg bg-blue-50 text-blue-600">
                  <Users className="h-5 w-5" />
                </div>
                <div>
                  <h3 className="text-sm font-bold text-slate-900">
                    Invite Enterprise Member
                  </h3>
                  <p className="text-xs text-slate-500">
                    Grant team access with RBAC role enforcement
                  </p>
                </div>
              </div>
              <button
                onClick={() => setIsInviteModalOpen(false)}
                className="p-1 rounded-lg text-slate-400 hover:text-slate-600 hover:bg-slate-100 cursor-pointer"
              >
                <X className="h-4 w-4" />
              </button>
            </div>

            <form onSubmit={handleInviteSubmit} className="mt-4 space-y-3.5">
              <div>
                <label className="block text-xs font-semibold text-slate-700 mb-1">
                  Full Name
                </label>
                <input
                  type="text"
                  required
                  placeholder="e.g. Jordan Smith"
                  value={inviteForm.name}
                  onChange={(e) =>
                    setInviteForm({ ...inviteForm, name: e.target.value })
                  }
                  className="w-full rounded-lg border border-slate-200 px-3 py-2 text-xs text-slate-900 focus:border-blue-500 focus:outline-hidden"
                />
              </div>

              <div>
                <label className="block text-xs font-semibold text-slate-700 mb-1">
                  Enterprise Email
                </label>
                <input
                  type="email"
                  required
                  placeholder="name@annotateai.internal"
                  value={inviteForm.email}
                  onChange={(e) =>
                    setInviteForm({ ...inviteForm, email: e.target.value })
                  }
                  className="w-full rounded-lg border border-slate-200 px-3 py-2 text-xs text-slate-900 focus:border-blue-500 focus:outline-hidden"
                />
              </div>

              <div className="grid grid-cols-2 gap-3">
                <div>
                  <label className="block text-xs font-semibold text-slate-700 mb-1">
                    Role
                  </label>
                  <select
                    value={inviteForm.role}
                    onChange={(e) =>
                      setInviteForm({
                        ...inviteForm,
                        role: e.target.value as EnterpriseUser['role'],
                      })
                    }
                    className="w-full rounded-lg border border-slate-200 px-2.5 py-2 text-xs text-slate-900 focus:border-blue-500 focus:outline-hidden bg-white"
                  >
                    <option value="Admin">Admin</option>
                    <option value="Qa Lead">Qa Lead</option>
                    <option value="Reviewer">Reviewer</option>
                    <option value="Annotator">Annotator</option>
                    <option value="Requester">Requester</option>
                    <option value="Guest">Guest</option>
                  </select>
                </div>

                <div>
                  <label className="block text-xs font-semibold text-slate-700 mb-1">
                    Department
                  </label>
                  <input
                    type="text"
                    value={inviteForm.department}
                    onChange={(e) =>
                      setInviteForm({ ...inviteForm, department: e.target.value })
                    }
                    className="w-full rounded-lg border border-slate-200 px-3 py-2 text-xs text-slate-900 focus:border-blue-500 focus:outline-hidden"
                  />
                </div>
              </div>

              <div>
                <label className="block text-xs font-semibold text-slate-700 mb-1">
                  Assigned Project Identifiers (comma separated)
                </label>
                <input
                  type="text"
                  value={inviteForm.assignedProjects}
                  onChange={(e) =>
                    setInviteForm({
                      ...inviteForm,
                      assignedProjects: e.target.value,
                    })
                  }
                  placeholder="proj_traffic, proj_sentiment"
                  className="w-full font-mono rounded-lg border border-slate-200 px-3 py-2 text-xs text-slate-900 focus:border-blue-500 focus:outline-hidden"
                />
              </div>

              <div className="pt-2 flex items-center justify-end gap-2 border-t border-slate-100">
                <button
                  type="button"
                  onClick={() => setIsInviteModalOpen(false)}
                  className="px-3.5 py-1.5 rounded-lg border border-slate-200 text-xs font-semibold text-slate-600 hover:bg-slate-50 cursor-pointer"
                >
                  Cancel
                </button>
                <button
                  type="submit"
                  className="px-4 py-1.5 rounded-lg bg-blue-600 hover:bg-blue-700 text-xs font-semibold text-white cursor-pointer shadow-xs"
                >
                  Send Invitation
                </button>
              </div>
            </form>
          </div>
        </div>
      )}
    </div>
  );
};
