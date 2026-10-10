"""Bounded scheduling policy. No claim of learned latency improvement."""
from dataclasses import dataclass

@dataclass(frozen=True)
class SourceClock:
    source_id:str
    elapsed_hours:float
    min_interval_hours:float
    max_interval_hours:float
    observed_change_rate:float=0
    priority:float=1
    approved:bool=True
    calls_today:int=0
    daily_cap:int=24
    retry_after_hours:float=0

    def __post_init__(self):
        if self.min_interval_hours<=0 or self.max_interval_hours<self.min_interval_hours:raise ValueError('Invalid intervals')
        if self.elapsed_hours<0 or self.observed_change_rate<0:raise ValueError('Invalid observations')

def due_sources(sources:list[SourceClock],budget:int) -> list[str]:
    if budget<0:raise ValueError('Negative budget')
    candidates=[]
    for s in sources:
        if not s.approved or s.calls_today>=s.daily_cap or s.retry_after_hours>0:continue
        if s.elapsed_hours<s.min_interval_hours:continue
        overdue=s.elapsed_hours>=s.max_interval_hours
        score=s.priority*(1+s.observed_change_rate)*s.elapsed_hours
        candidates.append((overdue,s.elapsed_hours/s.max_interval_hours,score,s.source_id))
    # An overdue heartbeat outranks popularity; budget/rights/rate limits still apply.
    candidates.sort(key=lambda x:(-x[0],-x[1] if x[0] else 0,-x[2],x[3]))
    return [x[3] for x in candidates[:budget]]
