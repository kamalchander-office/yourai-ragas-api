"""Tests for rule validator integration."""

from validators.rule_validator import RuleValidator


def test_rule_validator_pass():
    tc = {"expected_source": "vault_document"}
    row = {"actual_source": "vault_document", "actual_doc_id": None, "reference": None}
    assert RuleValidator().validate(tc, row).passed


def test_rule_validator_skip_when_no_expected():
    tc = {}
    row = {"actual_source": "anything"}
    assert RuleValidator().validate(tc, row).passed
