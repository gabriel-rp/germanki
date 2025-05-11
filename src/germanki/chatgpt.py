import json
import pickle
from pathlib import Path
from typing import List

import yaml
from openai import OpenAI
from pydantic import BaseModel

from germanki.core import AnkiCardInfo
from germanki.static import input_examples


class AnkiCardContentsCollection(BaseModel):
    card_contents: List[AnkiCardInfo]

    def to_yaml(self) -> str:
        return yaml.dump(self.model_dump()['card_contents'])


CHATGPT_PROMPT = """
For each line of input with a german word/expression, you will:
- For nouns, include gender and plural in the "extra" field (e.g., "der Hund, -e").
- For verbs, include the Perfekt (e.g., "haben + studiert").
- Provide two example sentences using A2-level vocabulary.
- List translations in order from most to least accurate (2–4 words each).
"""

WEB_UI_CHATGPT_PROMPT = (
    CHATGPT_PROMPT
    + f"""
Provide all the answer in a YAML format. Here's an example of the expected output:
{(Path(input_examples.__file__).parent / 'default.yaml').read_text()}
"""
)


class ChatGPTAPI:
    def __init__(
        self,
        openai_api_key,
        model='gpt-4o-mini',
        max_tokens_per_query: int = 500,
        temperature: int = 0,
    ):
        self.client = OpenAI(api_key=openai_api_key)
        self.model = model
        self.max_tokens_per_query = max_tokens_per_query
        self.temperature = temperature

    def query(self, prompt) -> AnkiCardContentsCollection:
        completion = self.client.chat.completions.create(
            model=self.model,
            messages=[
                {
                    'role': 'developer',
                    'content': CHATGPT_PROMPT,
                },
                {'role': 'user', 'content': prompt},
            ],
            response_format={
                'type': 'json_schema',
                'json_schema': {
                    'name': 'card_content_schema',
                    'strict': True,
                    'schema': {
                        'type': 'object',
                        'additionalProperties': False,
                        'required': ['card_contents'],
                        'properties': {
                            'card_contents': {
                                'description': 'List of information for each input word/expression',
                                'type': 'array',
                                'items': {
                                    'type': 'object',
                                    'required': [
                                        'word',
                                        'definition',
                                        'translations',
                                        'examples',
                                        'extra',
                                        'image_query_words',
                                    ],
                                    'additionalProperties': False,
                                    'properties': {
                                        'word': {
                                            'description': 'Original word provided by the user',
                                            'type': 'string',
                                        },
                                        'definition': {
                                            'description': 'Brief German definition',
                                            'type': 'string',
                                        },
                                        'translations': {
                                            'description': 'List of translations in order from most to least accurate',
                                            'type': 'array',
                                            'items': {
                                                'type': 'string',
                                            },
                                        },
                                        'examples': {
                                            'description': 'A couple of examples of this word usage',
                                            'type': 'array',
                                            'items': {
                                                'type': 'string',
                                            },
                                        },
                                        'extra': {
                                            'description': 'Gender/plural or Perfekt (for verbs)',
                                            'type': 'string',
                                        },
                                        'image_query_words': {
                                            'description': 'A search query one could use to find an image that best describes the original word. The less words, the better. List of words ordered from most relevant to least relevant.',
                                            'type': 'array',
                                            'items': {
                                                'type': 'string',
                                            },
                                        },
                                    },
                                },
                            },
                        },
                    },
                },
            },
        )

        return AnkiCardContentsCollection(
            **json.loads(completion.choices[0].message.content)
        )
