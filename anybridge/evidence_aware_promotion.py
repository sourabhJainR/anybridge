"""Evidence-aware capability promotion across independent cohorts.

Report-only lifecycle state for capability candidates. Promotion requires
distinct independent cohorts, not repeated observations from one benchmark
family. Canary graduation, decay rollback, and repeated-decay retirement are
deterministic and bounded; callers own execution, authorization, and storage.
"""
from __future__ import annotations
from dataclasses import dataclass
from collections import defaultdict

def _b(x): return max(0.0, min(1.0, float(x)))

@dataclass(frozen=True)
class CohortEvidence:
    capability_id: str
    cohort_id: str
    passed: bool
    confidence: float = 0.0
    domain: str = ""
    benchmark_family: str = ""
    execution_id: str = ""
    def to_dict(self): return self.__dict__.copy()

@dataclass(frozen=True)
class PromotionDecision:
    capability_id: str
    status: str
    cohorts: int
    attempts: int
    pass_rate: float
    confidence: float
    reason: str
    def to_dict(self): return self.__dict__.copy()

class EvidenceAwarePromotionStore:
    def __init__(self, *, min_cohorts=3, min_attempts_per_cohort=1,
                 promotion_rate=.9, promotion_confidence=.8,
                 canary_rate=.9, decay_rate=.75, retirement_failures=3,
                 max_observations=4096):
        self.min_cohorts=max(1,int(min_cohorts))
        self.min_attempts_per_cohort=max(1,int(min_attempts_per_cohort))
        self.promotion_rate=_b(promotion_rate)
        self.promotion_confidence=_b(promotion_confidence)
        self.canary_rate=_b(canary_rate)
        self.decay_rate=_b(decay_rate)
        self.retirement_failures=max(1,int(retirement_failures))
        self.max_observations=max(1,int(max_observations))
        self._observations=[]
        self._state={}
        self._decay_streak=defaultdict(int)

    def ingest(self, observations):
        for o in observations:
            if not o.capability_id or not o.cohort_id:
                continue
            self._observations.append(o)
        if len(self._observations)>self.max_observations:
            self._observations=self._observations[-self.max_observations:]
        return self.decisions()

    def _cohorts(self, capability_id):
        groups=defaultdict(list)
        for o in self._observations:
            if o.capability_id==capability_id:
                groups[o.cohort_id].append(o)
        return groups

    def _promotion(self, cap):
        groups=self._cohorts(cap)
        eligible=[]
        for cid,xs in sorted(groups.items()):
            if len(xs) < self.min_attempts_per_cohort:
                continue
            rate=sum(int(x.passed) for x in xs)/len(xs)
            conf=sum(_b(x.confidence) for x in xs)/len(xs)
            eligible.append((cid,rate,conf,len(xs)))
        if len(eligible)<self.min_cohorts:
            return None, len(eligible), sum(x[3] for x in eligible), 0., 0.
        rate=sum(x[1] for x in eligible)/len(eligible)
        conf=sum(x[2] for x in eligible)/len(eligible)
        return eligible, len(eligible), sum(x[3] for x in eligible), rate, conf

    def observe(self, observations):
        self.ingest(observations)
        return self.decisions()

    def decide(self, capability_id):
        eligible, cohorts, attempts, rate, conf=self._promotion(capability_id)
        current=self._state.get(capability_id,"candidate")
        if current in ("retired","quarantined"):
            return self._decision(capability_id,current,cohorts,attempts,rate,conf,"terminal state requires explicit reactivation")
        if eligible is not None:
            weak=[x for x in eligible if x[1] < self.promotion_rate or x[2] < self.promotion_confidence]
            if weak:
                return self._decision(capability_id,"candidate",cohorts,attempts,rate,conf,"weak independent cohort blocks promotion")
            if current=="candidate":
                self._state[capability_id]="canary"
                return self._decision(capability_id,"canary",cohorts,attempts,rate,conf,"multi-cohort holdout evidence passed")
        # evaluate canary/active decay from the latest observation per cohort
        if current in ("canary","graduated"):
            groups=self._cohorts(capability_id)
            latest=[]
            for cid,xs in sorted(groups.items()):
                latest.append(xs[-1])
            if latest:
                recent_rate=sum(int(x.passed) for x in latest)/len(latest)
                recent_conf=sum(_b(x.confidence) for x in latest)/len(latest)
                if recent_rate < self.decay_rate or recent_conf < self.decay_rate:
                    self._decay_streak[capability_id]+=1
                    if self._decay_streak[capability_id]>=self.retirement_failures:
                        self._state[capability_id]="retired"
                        return self._decision(capability_id,"retired",cohorts,attempts,recent_rate,recent_conf,"repeated decay")
                    self._state[capability_id]="quarantined"
                    return self._decision(capability_id,"quarantined",cohorts,attempts,recent_rate,recent_conf,"performance decay detected")
                if current=="canary" and recent_rate>=self.canary_rate and recent_conf>=self.promotion_confidence:
                    self._state[capability_id]="graduated"
                    return self._decision(capability_id,"graduated",cohorts,attempts,recent_rate,recent_conf,"canary evidence passed")
        return self._decision(capability_id,self._state.get(capability_id,"candidate"),cohorts,attempts,rate,conf,"evidence insufficient for state transition")

    def _decision(self,cap,status,cohorts,attempts,rate,conf,reason):
        return PromotionDecision(cap,status,cohorts,attempts,rate,conf,reason)

    def decisions(self):
        caps=sorted({x.capability_id for x in self._observations})
        return tuple(self.decide(c) for c in caps)

    def export(self):
        return {"version":1,"states":dict(sorted(self._state.items())),
                "decisions":[x.to_dict() for x in self.decisions()],
                "observations":[x.to_dict() for x in self._observations]}

    def reset(self):
        self._observations.clear(); self._state.clear(); self._decay_streak.clear()
