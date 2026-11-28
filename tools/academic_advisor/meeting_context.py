"""Request-scoped, coarse counseling context. Never store raw conversation or grades.
Signed browser tokens carry only the hypothetical topic labels, not confirmed facts.
"""
from contextvars import ContextVar
import re
from quality import norm

CURRENT = ContextVar('advisor_meeting_context', default=None)
PATTERNS = {
 'time': r'di lam|lam them|vua hoc vua lam|thieu thoi gian|ban viec|ca lam|thoi gian hoc han che',
 'finance': r'kho khan tai chinh|kho khan kinh te|khong du tien|ap luc tai chinh|hoc phi qua cao',
 'confidence': r'mat dong luc|nan chi|mat tu tin|ap luc hoc tap|so truot|chan nan',
 'foundation': r'mat goc|yeu nen tang|khong theo kip|khong hieu bai',
 'family': r'cham soc nguoi than|cham nguoi nha|viec gia dinh|trach nhiem gia dinh',
 'commute': r'di lai xa|nha xa|di hoc xa|mat nhieu thoi gian di lai',
}
# Explicit negation/removal only; do not interpret "không đủ tiền" as negation.
NEGATIVE = re.compile(r'\b(?:khong con|khong he|khong phai|khong|da ngung|da nghi|da thoi|het|khong co)\s+(?:viec\s+)?$')
QUESTION_ONLY = re.compile(r'\b(?:chi (?:can |muon )?(?:cho co |viet |neu |liet ke |dua ra )?(?:\d+ |ba |hai |mot )?cau hoi|chi (?:nen )?hoi|chi hoi|trong buoi gap (?:do|nay) co nen hoi gi|rut gon.*cau hoi)\b')
ACTION_ONLY = re.compile(r'\b(?:chi (?:can |muon )?(?:cho co |neu |liet ke |dua ra )?(?:cac )?(?:buoc|hanh dong|viec)|chi de xuat|sau buoi gap (?:do|nay) co nen lam gi)\b')
SHORT = re.compile(r'\b(?:ngan gon|rut gon|tom tat|gon lai)\b')
COUNT = re.compile(r'\b([1-5]|mot|hai|ba|bon|nam)\s+cau hoi\b')

def update_topics(question, previous=()):
    q=norm(question); topics=set(previous)&PATTERNS.keys(); touched=False
    for k,pat in PATTERNS.items():
        for m in re.finditer(r'\b(?:'+pat+r')\b',q):
            touched=True
            if NEGATIVE.search(q[max(0,m.start()-30):m.start()]):topics.discard(k)
            else:topics.add(k)
    return sorted(topics),touched

def focus(question):
    q=norm(question)
    if QUESTION_ONLY.search(q) or (COUNT.search(q) and re.search(r'\b(?:viet|soan|liet ke|dua ra|cho co|de xuat)\b',q)):return 'questions'
    if ACTION_ONLY.search(q):return 'actions'
    if SHORT.search(q):return 'short'
    return 'full'

def question_count(question):
    m=COUNT.search(norm(question)); words={'mot':1,'hai':2,'ba':3,'bon':4,'nam':5}
    return (words.get(m[1],int(m[1]) if m[1].isdigit() else 3) if m else 3)

def state_for(sid):
    x=CURRENT.get() or {}
    return x if str(x.get('mssv'))==str(sid) else {}

def continuation(question):
    q=norm(question)
    return focus(q)!='full' or bool(re.search(r'\b(?:trong buoi gap (?:do|nay)|sau buoi gap (?:do|nay))\b',q)) or update_topics(q)[1]

# A format request without an explicit student reference must be narrow;
# e.g. "tóm tắt học phí năm nay" must remain a public knowledge query.
def standalone_format(question):
    q=norm(question)
    return bool(re.fullmatch(r'(?:rut gon|tom tat|gon lai)(?: (?:giup )?co)?(?: (?:thoi|nhe))?|(?:chi )?(?:can |muon )?(?:cho co |viet |neu |liet ke |dua ra )?(?:[1-5] |mot |hai |ba |bon |nam )?cau hoi(?: (?:thoi|nhe|ngan gon))?|chi (?:neu |liet ke |de xuat )?(?:cac )?(?:buoc|hanh dong|viec)(?: (?:thoi|nhe|ngan gon))?',q))
