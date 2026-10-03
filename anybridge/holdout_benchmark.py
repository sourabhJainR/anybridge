"""Evidence-only benchmark aggregation for generated holdouts.

Aggregates independently scored holdouts into benchmark results. Generated
cases are never treated as evidence until independently scored, and results
never auto-promote a capability.
"""
from __future__ import annotations
from dataclasses import dataclass


def _b(x): return max(0.,min(1.,float(x)))


@dataclass(frozen=True)
class BenchmarkResult:
    capability_id: str
    domain: str
    attempts: int
    pass_rate: float
    confidence: float
    independent_attempts: int
    status: str
    reason: str
    def to_dict(self): return self.__dict__.copy()


class HoldoutBenchmark:
    def __init__(self, *, min_attempts=3, pass_rate=.9, max_results=1024):
        self.min_attempts=max(1,int(min_attempts))
        self.pass_rate=_b(pass_rate)
        self.max_results=max(1,int(max_results))
        self._cases={}
        self._outcomes=[]

    def ingest(self,cases,outcomes):
        self._cases={c.case_id:c for c in cases}
        for outcome in outcomes:
            if not outcome.independent:
                continue
            if outcome.case_id not in self._cases:
                continue
            self._outcomes.append(outcome)
        if len(self._outcomes)>self.max_results*4:
            self._outcomes=self._outcomes[-self.max_results*4:]
        return self.results()

    def results(self):
        groups={}
        for o in self._outcomes:
            c=self._cases[o.case_id]
            groups.setdefault((c.source_capability_id,c.target_domain),[]).append(o)
        out=[]
        for (cap,domain),xs in sorted(groups.items()):
            n=len(xs); rate=sum(int(x.passed) for x in xs)/n
            conf=sum(_b(x.evidence_confidence) for x in xs)/n
            status="validated_holdout" if n>=self.min_attempts and rate>=self.pass_rate else ("failed_holdout" if n>=self.min_attempts else "insufficient_evidence")
            out.append(BenchmarkResult(cap,domain,n,rate,conf,n,status,"independent benchmark outcome"))
        return tuple(out[-self.max_results:])

    def export(self):
        return {"version":1,"results":[x.to_dict() for x in self.results()]}
