"""
Unit tests for Self-Healing Incident Auto-Remediation Playbook Engine.
"""

import pytest
from cortex_workflow_engine.auto_remediation import (
    AutoRemediationEngine,
    IncidentSeverity,
    IncidentType,
    RemediationActionType,
    RemediationExecutionReceipt,
)


def test_remediation_high_error_rate_execution():
    engine = AutoRemediationEngine()
    receipt = engine.execute_playbook(
        tenant_id="tenant_acme",
        incident_id="inc_err_001",
        incident_type_str="HIGH_ERROR_RATE",
        severity_str="HIGH",
        context={"service": "checkout_api"},
    )
    assert isinstance(receipt, RemediationExecutionReceipt)
    assert receipt.status == "COMPLETED"
    assert receipt.tenant_id == "tenant_acme"
    assert len(receipt.steps) == 2
    actions = [s.action for s in receipt.steps]
    assert RemediationActionType.CIRCUIT_TRIP in actions
    assert RemediationActionType.SHED_TRAFFIC in actions
    assert len(receipt.hmac_signature) == 64


def test_remediation_rate_limit_spike():
    engine = AutoRemediationEngine()
    receipt = engine.execute_playbook(
        tenant_id="tenant_acme",
        incident_id="inc_rl_002",
        incident_type_str="RATE_LIMIT_SPIKE",
        severity_str="HIGH",
        context={"violating_ip": "203.0.113.42"},
    )
    assert receipt.status == "COMPLETED"
    ip_step = next(s for s in receipt.steps if s.action == RemediationActionType.QUARANTINE_IP)
    assert ip_step.parameters["target_ip"] == "203.0.113.42"
    assert "Quarantined IP" in ip_step.details


def test_remediation_critical_severity_approval_gate():
    engine = AutoRemediationEngine()
    # Without auto_approve, CRITICAL incidents must pause in PENDING_APPROVAL
    receipt = engine.execute_playbook(
        tenant_id="tenant_acme",
        incident_id="inc_crit_999",
        incident_type_str="EXCESSIVE_5XX",
        severity_str="CRITICAL",
        auto_approve=False,
    )
    assert receipt.status == "PENDING_APPROVAL"
    assert all(not s.executed for s in receipt.steps)

    # With auto_approve=True, executes immediately
    receipt_approved = engine.execute_playbook(
        tenant_id="tenant_acme",
        incident_id="inc_crit_999",
        incident_type_str="EXCESSIVE_5XX",
        severity_str="CRITICAL",
        auto_approve=True,
    )
    assert receipt_approved.status == "COMPLETED"
    assert all(s.executed for s in receipt_approved.steps)
