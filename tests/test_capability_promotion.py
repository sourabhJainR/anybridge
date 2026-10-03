from anybridge.capability_promotion import (
    CanaryEvidence,
    CapabilityPromotionStore,
    HoldoutEvidence,
)


def test_independent_holdout_opens_canary():
    store = CapabilityPromotionStore()
    decision = store.evaluate_holdout(HoldoutEvidence("cap", 3, 0.95, 0.9))
    assert decision.action == "run_canary"
    assert decision.state.status == "canary"


def test_non_independent_holdout_cannot_promote():
    store = CapabilityPromotionStore()
    decision = store.evaluate_holdout(HoldoutEvidence("cap", 10, 1.0, 1.0, independent=False))
    assert decision.state.status == "candidate"


def test_canary_promotes_after_bounded_evidence():
    store = CapabilityPromotionStore()
    store.evaluate_holdout(HoldoutEvidence("cap", 3, 1.0, 0.95))
    decision = store.evaluate_canary(
        "cap", [CanaryEvidence("cap", True), CanaryEvidence("cap", True), CanaryEvidence("cap", True)]
    )
    assert decision.state.status == "promoted"
    assert decision.state.version == 1


def test_canary_regression_rolls_back_and_versions():
    store = CapabilityPromotionStore()
    store.evaluate_holdout(HoldoutEvidence("cap", 3, 1.0, 0.95))
    decision = store.evaluate_canary("cap", [CanaryEvidence("cap", False)])
    assert decision.state.status == "rolled_back"
    assert decision.action == "quarantine"
    assert decision.state.version == 1


def test_confidence_gate_keeps_capability_in_candidate_state():
    store = CapabilityPromotionStore()
    decision = store.evaluate_holdout(HoldoutEvidence("cap", 3, 1.0, 0.79))
    assert decision.state.status == "candidate"
    assert decision.action == "collect_holdout"


def test_canary_cannot_bypass_holdout_gate():
    store = CapabilityPromotionStore()
    decision = store.evaluate_canary("cap", [CanaryEvidence("cap", True)])
    assert decision.state.status == "candidate"
    assert decision.action == "collect_holdout"
