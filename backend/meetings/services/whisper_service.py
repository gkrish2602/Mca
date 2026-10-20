"""Speech-to-text via OpenAI Whisper.

This is a scaffold: it calls the Whisper API when OPENAI_API_KEY is set,
otherwise it returns a placeholder transcript so the rest of the pipeline
can be developed/tested without live API access.
"""
from django.conf import settings


def transcribe_audio(audio_path: str) -> str:
    if not settings.OPENAI_API_KEY:
        return '[transcription placeholder - set OPENAI_API_KEY to enable real Whisper transcription]'

    import openai  # imported lazily so the package is optional until configured

    client = openai.OpenAI(api_key=settings.OPENAI_API_KEY)
    with open(audio_path, 'rb') as audio_file:
        result = client.audio.transcriptions.create(model='whisper-1', file=audio_file)
    return result.text
