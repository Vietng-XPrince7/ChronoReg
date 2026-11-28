"""Exact minimum-round scheduling for small candidate DAGs.
Integrated into course_planning; provenance remains with the caller. All prerequisite edges mean strictly earlier round.
No actual semester, official registration load, or graduation prediction implied.
"""
from collections import deque
import json


def optimize_rounds(credits, prerequisites, budget, *, satisfied=(), first_course=None):
    """credits: {code: positive int}; prerequisites: {code: iterable of code}.
    Every course must have a prerequisite entry, even an empty list. An external
    prerequisite is allowed only if explicitly satisfied. Fail closed otherwise.
    Returns minimum number of hypothetical rounds, or raises ValueError.
    """
    if type(budget) is not int or budget <= 0:
        raise ValueError('positive integer budget required')
    codes=sorted(credits); n=len(codes)
    if first_course is not None and first_course not in credits:raise ValueError("first course not schedulable")
    if n>12: raise ValueError('exact search limited to 12 courses; use a larger solver')
    if set(prerequisites)!=set(codes): raise ValueError('missing or extraneous prerequisite entries')
    sat=set(satisfied)
    if sat.intersection(codes): raise ValueError('course both pending and satisfied')
    if any(type(credits[c]) is not int or not 0<credits[c]<=budget for c in codes):
        raise ValueError('invalid or over-budget course credits')
    bit={c:1<<i for i,c in enumerate(codes)}; full=(1<<n)-1
    deps=[]
    for c in codes:
        req=set(prerequisites[c]); unknown=req-set(codes)-sat
        if unknown: raise ValueError(f'{c}: unverified prerequisites {sorted(unknown)}')
        deps.append(sum(bit[x] for x in req if x in bit))
    weights=[0]*(full+1)
    for mask in range(1,full+1):
        low=mask&-mask; weights[mask]=weights[mask^low]+credits[codes[low.bit_length()-1]]
    queue=deque([0]); prev={0:None}
    while queue:
        state=queue.popleft()
        if state==full:
            batches=[]
            while prev[state] is not None:
                earlier, batch=prev[state]
                batches.append([c for c in codes if batch&bit[c]])
                state=earlier
            batches.reverse()
            return {'rounds':batches,'round_count':len(batches),'optimal_for_supplied_graph':True,'budget':budget}
        available=0
        for i,dep in enumerate(deps):
            b=1<<i
            if not state&b and dep&state==dep: available|=b
        batch=available
        while batch:
            if weights[batch]<=budget and (state or first_course is None or batch&bit[first_course]):
                nxt=state|batch
                if nxt not in prev:
                    prev[nxt]=(state,batch);queue.append(nxt)
            batch=(batch-1)&available
    raise ValueError('no valid schedule (cycle or unsatisfiable dependencies)')


def validate(result, credits, prerequisites, budget, satisfied=()):
    done=set(satisfied)
    seen=set()
    for batch in result['rounds']:
        if not batch or len(set(batch))!=len(batch) or seen.intersection(batch): return False
        if any(c not in credits for c in batch) or sum(credits[c] for c in batch)>budget: return False
        if any(not set(prerequisites[c]).issubset(done) for c in batch): return False
        done.update(batch);seen.update(batch)
    return seen==set(credits) and len(result['rounds'])==result['round_count']
