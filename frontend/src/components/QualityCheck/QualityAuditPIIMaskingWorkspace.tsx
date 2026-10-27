import React from 'react';
import { QualityAuditImageWorkspace } from './QualityAuditImageWorkspace';

interface Props {
  projectId?: string;
  onToggleSidebar?: () => void;
  onNavigateToProjects?: () => void;
  onToast: (msg: string) => void;
}

/** PII masking uses the same persisted QC/agent workflow as other image audits. */
export const QualityAuditPIIMaskingWorkspace: React.FC<Props> = (props) => (
  <QualityAuditImageWorkspace {...props} auditTitle="PII Masking Quality Audit" />
);
