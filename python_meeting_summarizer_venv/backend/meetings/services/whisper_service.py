"""Speech-to-text via the OpenAI Whisper API."""
from django.conf import settings


def transcribe_audio(audio_path: str) -> str:
    if not settings.OPENAI_API_KEY:
        raise RuntimeError('OPENAI_API_KEY is required to transcribe audio.')

    import openai  # imported lazily so the package is optional until configured

    client = openai.OpenAI(api_key=settings.OPENAI_API_KEY)
    with open(audio_path, 'rb') as audio_file:
        result = client.audio.transcriptions.create(model='whisper-1', file=audio_file)
    transcript = result.text.strip()
    if not transcript:
        raise ValueError('The transcription service returned an empty transcript.')
    return transcript
