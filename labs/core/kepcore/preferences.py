"""Small classical preference estimators, separated from factual eligibility.

Ratings only: no model API, no sensitive profiles, no food/service-label leakage.
Scores are expected ratings on the training scale, NOT confidence probabilities.
"""
from __future__ import annotations
from dataclasses import dataclass
from collections import defaultdict
from itertools import combinations
import math


@dataclass(frozen=True)
class Rating:
    user: str
    item: str
    value: float


class PreferenceModel:
    def __init__(self, kind: str='bias', regularization: float=5., k: int=15):
        if kind not in {'global_mean','item_mean','user_mean','bias','item_knn'}:
            raise ValueError('Unknown estimator')
        if regularization <= 0 or k < 1: raise ValueError('Invalid parameters')
        self.kind, self.reg, self.k = kind, regularization, k
        self.fitted = False

    def fit(self, rows: list[Rating]) -> 'PreferenceModel':
        if not rows: raise ValueError('Empty training set')
        if any(not math.isfinite(r.value) or not 0 <= r.value <= 2 for r in rows):
            raise ValueError('Expected finite 0..2 ratings')
        pairs = {(r.user,r.item) for r in rows}
        if len(pairs) != len(rows): raise ValueError('Duplicate user-item pairs')
        self.training_pairs = frozenset(pairs)
        self.mu = sum(r.value for r in rows)/len(rows)
        self.by_user, self.by_item = defaultdict(dict), defaultdict(dict)
        for r in sorted(rows, key=lambda r:(r.user,r.item)):
            self.by_user[r.user][r.item] = r.value
            self.by_item[r.item][r.user] = r.value
        self.bu = {u:0. for u in self.by_user}
        self.bi = {i:0. for i in self.by_item}
        if self.kind == 'item_mean':
            for i, rs in self.by_item.items():
                self.bi[i]=sum(v-self.mu for v in rs.values())/(len(rs)+self.reg)
        elif self.kind == 'user_mean':
            for u, rs in self.by_user.items():
                self.bu[u]=sum(v-self.mu for v in rs.values())/(len(rs)+self.reg)
        elif self.kind in {'bias','item_knn'}:
            # Coordinate descent for regularized squared-error additive baseline.
            for _ in range(30):
                for u, rs in self.by_user.items():
                    self.bu[u]=sum(v-self.mu-self.bi[i] for i,v in rs.items())/(len(rs)+self.reg)
                for i, rs in self.by_item.items():
                    self.bi[i]=sum(v-self.mu-self.bu[u] for u,v in rs.items())/(len(rs)+self.reg)
        self.sim = defaultdict(dict)
        if self.kind == 'item_knn':
            acc = defaultdict(lambda:[0.,0.,0.,0])
            for u, rs in self.by_user.items():
                for i,j in combinations(sorted(rs),2):
                    x=rs[i]-self.baseline(u,i); y=rs[j]-self.baseline(u,j)
                    a=acc[i,j];a[0]+=x*y;a[1]+=x*x;a[2]+=y*y;a[3]+=1
            for (i,j),(dot,xx,yy,n) in acc.items():
                if n<2 or xx<=0 or yy<=0: continue
                val=dot/math.sqrt(xx*yy)*n/(n+10.)
                if val>0: self.sim[i][j]=val;self.sim[j][i]=val
        self.fitted=True
        return self

    def baseline(self,user:str,item:str) -> float:
        return self.mu+self.bu.get(user,0.)+self.bi.get(item,0.)

    def predict(self,user:str,item:str) -> float:
        if not self.fitted: raise RuntimeError('Model must be fitted')
        pred=self.baseline(user,item)
        if self.kind=='item_knn':
            sims=self.sim.get(item,{})
            values=sorted(((sims[j],j,v) for j,v in self.by_user.get(user,{}).items() if j in sims), key=lambda t:(-t[0],t[1]))[:self.k]
            if values:
                pred+=sum(w*(v-self.baseline(user,j)) for w,j,v in values)/sum(w for w,_,_ in values)
        return max(0.,min(2.,pred))

    def support(self,user:str,item:str) -> dict:
        return dict(user_ratings=len(self.by_user.get(user,{})),
                    item_ratings=len(self.by_item.get(item,{})),
                    unknown_user=user not in self.by_user,
                    unknown_item=item not in self.by_item,
                    score_type='expected_rating_not_probability')


def rerank_eligible(decision, scores: dict[str,float], limit:int=3) -> list[dict]:
    """Never reintroduce blocked entities; learned desirability != factual truth."""
    if limit<1: raise ValueError('Positive limit required')
    out=[]
    for row in decision.selected:
        score=scores.get(row['id'])
        if score is not None and (isinstance(score,bool) or not isinstance(score,(int,float)) or not math.isfinite(score)):
            raise ValueError('Invalid preference score')
        out.append({**row,'preference_score':score})
    out.sort(key=lambda r:(r['preference_score'] is None,-(r['preference_score'] or 0.),r['id']))
    return out[:limit]
