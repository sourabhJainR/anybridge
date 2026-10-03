"""Evidence-gated capability promotion and rollback.

This module consumes caller-supplied independent holdout and canary outcomes.
It never executes a capability, persists external learning, or grants authority.
"""
from __future__ import annotations
from dataclasses import dataclass
from typing import Iterable


def _bounded(value: float) -> float:
    return max(0.0, min(1.0, float(value)))


@dataclass(frozen=True)
class HoldoutEvidence:
    capability_id: str
    attempts: int
    pass_rate: float
    confidence: float
    independent: bool = True


@dataclass(frozen=True)
class CanaryEvidence:
    capability_id: str
    passed: bool
    evidence_confidence: float = 0.0


@dataclass(frozen=True)
class CapabilityPromotionState:
    capability_id: str
    status: str
    version: int
    holdout_attempts: int
    holdout_pass_rate: float
    calibrated_confidence: float
    canary_attempts: int
    canary_pass_rate: float
    reason: str

    def to_dict(self) -> dict:
        return self.__dict__.copy()


@dataclass(frozen=True)
class CapabilityPromotionDecision:
    capability_id: str
    action: str
    state: CapabilityPromotionState

    def to_dict(self) -> dict:
        return {**self.__dict__, "state": self.state.to_dict()}


class CapabilityPromotionStore:
    """Small in-memory gate for independent holdout -> canary -> promotion."""

    def __init__(
        self,
        *,
        holdout_min_attempts: int = 3,
        holdout_min_rate: float = 0.90,
        min_confidence: float = 0.80,
        canary_min_attempts: int = 3,
        canary_min_rate: float = 0.90,
        rollback_rate: float = 0.75,
    ):
        self.holdout_min_attempts = max(1, int(holdout_min_attempts))
        self.holdout_min_rate = _bounded(holdout_min_rate)
        self.min_confidence = _bounded(min_confidence)
        self.canary_min_attempts = max(1, int(canary_min_attempts))
        self.canary_min_rate = _bounded(canary_min_rate)
        self.rollback_rate = _bounded(rollback_rate)
        self._states: dict[str, CapabilityPromotionState] = {}
        self._canaries: dict[str, list[CanaryEvidence]] = {}
        self._versions: dict[str, int] = {}

    def evaluate_holdout(self, evidence: HoldoutEvidence) -> CapabilityPromotionDecision:
        if not evidence.independent:
            return self._set(
                evidence.capability_id,
                status="candidate",
                reason="holdout evidence is not independent",
                holdout=evidence,
            )
        status = "candidate"
        reason = "awaiting independent holdout evidence"
        if (
            evidence.attempts >= self.holdout_min_attempts
            and _bounded(evidence.pass_rate) >= self.holdout_min_rate
            and _bounded(evidence.confidence) >= self.min_confidence
        ):
            status = "canary"
            reason = "independent holdout and confidence thresholds reached; canary permitted"
        return self._set(evidence.capability_id, status=status, reason=reason, holdout=evidence)

    def evaluate_canary(
        self, capability_id: str, observations: Iterable[CanaryEvidence]
    ) -> CapabilityPromotionDecision:
        key = str(capability_id)
        bucket = self._canaries.setdefault(key, [])
        bucket.extend(observations)
        if len(bucket) > self.canary_min_attempts * 4:
            del bucket[:-self.canary_min_attempts * 4]
        prior = self._states.get(key)
        if prior is None:
            raise KeyError(key)
        if prior.status not in {"canary", "promoted"}:
            return self._set(
                key,
                status=prior.status,
                reason="independent holdout gate has not opened canary",
                prior=prior,
                canary_attempts=len(bucket),
            )
        attempts = len(bucket)
        rate = sum(int(x.passed) for x in bucket) / attempts if attempts else 0.0
        if attempts >= 1 and rate < self.rollback_rate:
            self._versions[key] = self._versions.get(key, prior.version) + 1
            return self._set(
                key,
                status="rolled_back",
                reason="canary regression crossed rollback threshold",
                prior=prior,
                canary_attempts=attempts,
                canary_rate=rate,
            )
        if attempts >= self.canary_min_attempts and rate >= self.canary_min_rate:
            self._versions[key] = self._versions.get(key, prior.version) + 1
            return self._set(
                key,
                status="promoted",
                reason="canary threshold reached; capability promotion permitted",
                prior=prior,
                canary_attempts=attempts,
                canary_rate=rate,
            )
        return self._set(
            key,
            status="canary",
            reason="canary evidence still required",
            prior=prior,
            canary_attempts=attempts,
            canary_rate=rate,
        )

    def _set(
        self,
        capability_id: str,
        *,
        status: str,
        reason: str,
        holdout: HoldoutEvidence | None = None,
        prior: CapabilityPromotionState | None = None,
        canary_attempts: int | None = None,
        canary_rate: float | None = None,
    ) -> CapabilityPromotionDecision:
        existing = prior or self._states.get(capability_id)
        holdout_attempts = (
            holdout.attempts if holdout is not None else existing.holdout_attempts if existing else 0
        )
        holdout_rate = (
            _bounded(holdout.pass_rate) if holdout is not None else existing.holdout_pass_rate if existing else 0.0
        )
        confidence = (
            _bounded(holdout.confidence) if holdout is not None else existing.calibrated_confidence if existing else 0.0
        )
        canary_bucket = self._canaries.get(capability_id, [])
        c_attempts = canary_attempts if canary_attempts is not None else len(canary_bucket)
        c_rate = canary_rate if canary_rate is not None else (
            sum(int(x.passed) for x in canary_bucket) / len(canary_bucket) if canary_bucket else 0.0
        )
        state = CapabilityPromotionState(
            capability_id, status, self._versions.get(capability_id, existing.version if existing else 0),
            holdout_attempts, holdout_rate, confidence, c_attempts, c_rate, reason,
        )
        self._states[capability_id] = state
        action = {
            "candidate": "collect_holdout",
            "canary": "run_canary",
            "promoted": "use_capability",
            "rolled_back": "quarantine",
        }[status]
        return CapabilityPromotionDecision(capability_id, action, state)

    def states(self) -> tuple[CapabilityPromotionState, ...]:
        return tuple(sorted(self._states.values(), key=lambda x: x.capability_id))

    def export(self) -> dict:
        return {"version": 1, "states": [x.to_dict() for x in self.states()]}

    def reset(self) -> None:
        self._states.clear()
        self._canaries.clear()
        self._versions.clear()
