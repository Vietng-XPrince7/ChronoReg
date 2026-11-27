"""Disambiguate programme/class wording for public scholarship-rate questions.

Only reclassify a rate request if the original advisor classifier found a class
and the same classifier, with programme wording masked, finds REGULATION.
Student IDs/names, explicit class references, news and course trends retain
priority. This changes advisor context, not the safety/risk router or question.
"""
import re
from scholarship import is_rate_query, group_of
from quality import norm
from tuition import dimensions

_PROGRAMME_CLASS = re.compile(r'\blớp\s+(?:chất\s+lượng\s+cao|CLC)\b',re.I)
# In a rate question, explicitly named QH cohort is not necessarily a roster.
_COHORT = re.compile(r'\bkhóa\s+(?:từ\s+)?QH[- ]*20\d{2}\b',re.I)
# Conservative: do not strip scope when a real class/student cue remains.
_REAL_CLASS = re.compile(r'\b(?:lop minh|lop toi|lop chung ta|lop dang quan ly|trong lop|toan lop|ca lop|cua lop|bang diem|danh sach sinh vien|sinh vien nao|em nao|nhung em|cac em|bao nhieu em|si so|mssv|ma sinh vien|k68|k69|cntt1|diem ren luyen|gpa|cpa)\b')

def classify_with_scope(original, question, *, roster=None, mssv=None):
    category, entities = original(question, roster=roster, mssv=mssv)
    if category not in ('CLASS_STATS','ELIGIBILITY_CHECK') or mssv or (entities or {}).get('mssv'):
        return category, entities
    if not (is_rate_query(question) and group_of(question)) and dimensions(question) is None:
        return category, entities
    masked = _PROGRAMME_CLASS.sub('chương trình chất lượng cao', question)
    masked = _COHORT.sub('khóa tuyển sinh', masked)
    if masked == question or _REAL_CLASS.search(norm(masked)):
        return category, entities
    new_category, _ = original(masked, roster=roster, mssv=mssv)
    if new_category == 'REGULATION':
        return new_category, entities
    return category, entities
