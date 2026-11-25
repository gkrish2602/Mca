"""Small lexical retriever for relevant notes from earlier team meetings."""
import re

from django.db.models import Q

from ..models import Meeting

STOP_WORDS = {
    'about', 'after', 'again', 'also', 'been', 'before', 'being', 'between',
    'could', 'from', 'have', 'into', 'meeting', 'more', 'other', 'same',
    'some', 'that', 'their', 'them', 'then', 'there', 'these', 'they',
    'this', 'those', 'through', 'under', 'very', 'were', 'what', 'when',
    'where', 'which', 'while', 'will', 'with', 'would', 'your',
}


def _tokens(text: str) -> set[str]:
    return {
        token for token in re.findall(r'[a-z0-9]{3,}', text.casefold())
        if token not in STOP_WORDS
    }


def retrieve_relevant_context(meeting: Meeting, limit: int = 3) -> str:
    organization = meeting.created_by.organization
    scope = (
        Q(created_by__organization=organization)
        if organization
        else Q(created_by=meeting.created_by)
    )
    previous_meetings = Meeting.objects.filter(scope).exclude(
        id=meeting.id,
    ).exclude(summary='').order_by('-created_at')[:25]
    query_tokens = _tokens(meeting.transcript)
    ranked = []

    for previous in previous_meetings:
        action_items = ' '.join(previous.action_items.values_list('description', flat=True))
        questions = ' '.join(previous.unresolved_questions.values_list('question', flat=True))
        content = '\n'.join(filter(None, (previous.summary, previous.decisions, action_items, questions)))
        previous_tokens = _tokens(content)
        if not query_tokens or not previous_tokens:
            continue
        overlap = len(query_tokens & previous_tokens) / len(query_tokens | previous_tokens)
        if overlap >= 0.02:
            ranked.append((overlap, previous, content))

    ranked.sort(key=lambda result: (result[0], result[1].created_at), reverse=True)
    return '\n\n'.join(
        f'Previous meeting "{previous.title}": {content[:1200]}'
        for _, previous, content in ranked[:limit]
    )[:4000]
