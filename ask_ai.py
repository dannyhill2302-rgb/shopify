import time
import openai

client = openai.OpenAI()


def ask_ai(prompt, temperature=1, max_retries=3):
    """Call the OpenAI chat API with retry logic for transient rate limits."""
    for attempt in range(max_retries):
        try:
            completion = client.chat.completions.create(
                model='gpt-4o',
                messages=[
                    {'role': 'system', 'content': 'You are a sci-fi writer and poet.'},
                    {'role': 'user', 'content': prompt},
                ],
                temperature=temperature,
            )
            return completion.choices[0].message.content

        except openai.RateLimitError as e:
            error_code = getattr(e, 'code', None) or (
                e.body.get('error', {}).get('code') if isinstance(getattr(e, 'body', None), dict) else None
            )
            # insufficient_quota is a billing problem — retrying won't help
            if error_code == 'insufficient_quota':
                raise RuntimeError(
                    'OpenAI quota exhausted. Please check your billing details at '
                    'https://platform.openai.com/account/billing'
                ) from e

            if attempt == max_retries - 1:
                raise

            wait = 2 ** attempt  # 1s, 2s, 4s
            print(f'Rate limited (attempt {attempt + 1}/{max_retries}), retrying in {wait}s...')
            time.sleep(wait)
