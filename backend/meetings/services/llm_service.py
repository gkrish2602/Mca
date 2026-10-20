"""LLM-based meeting analysis (GPT-4 / Claude via structured prompting).

Scaffold only: returns a mock structured response unless an API key is
configured, so the rest of the pipeline (storage, dashboard) can be built
and tested independently of a live LLM subscription.
"""
import json

from django.conf import settings

ANALYSIS_PROMPT = """You are a meeting analysis assistant. Given the meeting transcript below,
return a strict JSON object with fields:
  summary (string), decisions (array of strings),
  action_items (array of {{task, owner, deadline, priority}}),
  unresolved_questions (array of strings),
  productivity_score (integer 1-10).

Transcript:
{transcript}
"""


def analyze_transcript(transcript: str) -> dict:
    if not settings.OPENAI_API_KEY and not settings.ANTHROPIC_API_KEY:
        return {
            'summary': '[summary placeholder - configure OPENAI_API_KEY or ANTHROPIC_API_KEY]',
            'decisions': [],
            'action_items': [],
            'unresolved_questions': [],
            'productivity_score': None,
        }

    import openai  # imported lazily so the package is optional until configured

    client = openai.OpenAI(api_key=settings.OPENAI_API_KEY)
    response = client.chat.completions.create(
        model='gpt-4o-mini',
        messages=[{'role': 'user', 'content': ANALYSIS_PROMPT.format(transcript=transcript)}],
        response_format={'type': 'json_object'},
    )
    return json.loads(response.choices[0].message.content)
