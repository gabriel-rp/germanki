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
Each line of input will contain a german word or expression.
One line of input may generate more than one output.
The answer should be YAML-formatted.
The complete schema will be provided below with examples.
Each line of input should be checked against all of the rules below.
All rules should apply simultaneously.
Ensure all of them still apply after one rule overrides the original input.

Rules:
- An input is still considered a verb even when it contains extra information such as the german case or the required prepositions (e.g., "sich freuen + auf + akk.").
- If the word is mispelled, fix it in the "word" field.
- Image query words must always be in English in the "image_query_words" field.
- Provide two example sentences using B1-level vocabulary in the "examples" field.
- List english translations in order from most to least accurate (minimum 2 and maximum 4 words each) in the "translations" field.
- If the input is a noun, include gender and plural in the "extra" field (e.g., "der Hund, -e").
- If the input is a noun, capitalize the first letter of the word in the "word" field ("hund" -> "Hund").
- If the input is a noun and the article was accidentally provided with the word, remove it from the "word" field ("der Hund" -> "Hund").
- If the input is a noun and the word was provided in the plural form and there is a singular form, use the singular form in the "word" field ("Hunde" -> "Hund").
- If the input is a verb, use the verb in the infinitive version in the "word" field ("gehe" -> "gehen").
- If the input is a verb, add the case to the "word" field (e.g., "trinken" -> "trinken + akk.")
- If the input is a relexiv verb, ensure "sich" is in the "word" field ("erinnern" -> "sich erinnern + an + akk.").
- If the input is a verb and it requires a preposition, ensure it's included in the "word" field ("warten" -> "warten + auf + akk."). If multiple prepositions are possible, create one output list element for each ("sich freuen" should create two entries: "sich freuen + über + akk." and "sich freuen + auf + akk.")
- If the input is a verb, include the Perfekt (e.g., "sich freuen + auf + akk." -> "haben + gefreut + auf") in the "extra" field. Ensure the correct help verb is used, either "haben" or "sein".
"""

WEB_UI_CHATGPT_PROMPT = (
    CHATGPT_PROMPT
    + f"""
Provide all the answer in a YAML format. Here's an example of the expected output format:
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
                                'description': 'Language learning flashcard information for German',
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
                                            'description': 'Word provided by the user with extra information, when it applies (case, preposition, "sich")',
                                            'type': 'string',
                                        },
                                        'definition': {
                                            'description': 'German definition with B1-level vocabulary',
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
                                            'description': 'Three examples of this word usage. At least one in Present and one in Perfect.',
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
