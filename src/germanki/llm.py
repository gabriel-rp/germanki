import json
from pathlib import Path
from typing import Final, Any, AsyncGenerator, Literal

import yaml
import litellm
import instructor
from pydantic import BaseModel, Field

from germanki.core import AnkiCardInfo
from germanki.static import input_examples


class AnkiCardContentsCollection(BaseModel):
    card_contents: list[AnkiCardInfo]

    def to_yaml(self) -> str:
        return yaml.dump(self.model_dump()['card_contents'])


class PreprocessedWord(BaseModel):
    normalized_word: str = Field(description="The word or expression in its base normalized form (e.g., 'Hund', 'gehen + akk.', 'gut').")
    category: Literal["noun", "verb", "adjective", "expression"] = Field(description="The grammatical category of the input.")

class PreprocessedCollection(BaseModel):
    words: list[PreprocessedWord]


PREPROCESS_PROMPT: Final[str] = """
You are a German language expert. Normalize the following inputs for an Anki deck.
For each input:
1. Fix any typos or misspellings (e.g., "Hünd" -> "Hund").
2. Nouns: Use singular form, capitalize it, and REMOVE any articles (e.g., "die Hunde" -> "Hund").
3. Verbs: Use the present infinitive. Add reflexive "sich" if the verb is reflexive. Add standard prepositions and cases if the verb is commonly used with them (e.g., "gefreut" -> "sich freuen + auf + akk.").
4. Adjectives: Use the basic, uninflected form (e.g., "schnellere" -> "schnell").
5. Expressions/Idioms: Keep the full base form (e.g., "den Löffel abgeben").

Identify the category for each: "noun", "verb", "adjective", or "expression".
"""

CONTENT_PROMPT: Final[str] = """
You are a German language teacher. For each preprocessed word and its category, generate comprehensive Anki card content.

General Rules:
- Translations: English, ordered by accuracy (2-4 words each).
- Definition: Concise explanation (in German). For expressions, explain the figurative meaning.
- Examples: Provide exactly 5 sentences using B1-level vocabulary. Each sentence MUST use a different grammatical form in this order:
  1. Präsens
  2. Präteritum
  3. Perfekt
  4. Futur I
  5. Passiv (Vorgangspassiv)
- Image Query: Keywords in English for a photo search.

Category Specifics:
- Nouns: In the "extra" field, provide the gender and plural (e.g., "der Hund, -e").
- Verbs: In the "extra" field, provide the Präteritum and the Perfekt (e.g., "ging | ist gegangen").
- Adjectives: In the "extra" field, specify it is an "Adjektiv".
- Expressions: In the "extra" field, specify "Idiom" or "Umgangssprache".
"""

WEB_UI_LLM_PROMPT: Final[str] = (
    f"PREPROCESSING STEP:\n{PREPROCESS_PROMPT}\n\nCONTENT GENERATION STEP:\n{CONTENT_PROMPT}"
    + f"""
Provide all the answer in a YAML format. Here's an example of the expected output format:
{(Path(input_examples.__file__).parent / 'default.yaml').read_text()}
"""
)


class LLMAPI:
    def __init__(
        self,
        api_key: str | None = None,
        model: str = 'gpt-4o-mini',
        max_tokens_per_query: int = 4096,
        temperature: float = 0,
    ):
        self.model = model
        self.max_tokens_per_query = max_tokens_per_query
        self.temperature = temperature
        self.api_key = api_key
        self.client = instructor.from_litellm(litellm.acompletion)

    async def query(self, input_text: str, batch_size: int = 10) -> AsyncGenerator[list[AnkiCardInfo], None]:
        lines = [line.strip() for line in input_text.split("\n") if line.strip()]
        if not lines:
            return

        for i in range(0, len(lines), batch_size):
            batch = lines[i : i + batch_size]
            
            # Step 1: Preprocess
            preprocessed: PreprocessedCollection = await self.client.chat.completions.create(
                model=self.model,
                messages=[
                    {'role': 'system', 'content': PREPROCESS_PROMPT},
                    {'role': 'user', 'content': "\n".join(batch)},
                ],
                response_model=PreprocessedCollection,
                temperature=self.temperature,
                api_key=self.api_key,
            )

            # Step 2: Generate Content
            content_input = "\n".join([f"{w.normalized_word} ({w.category})" for w in preprocessed.words])
            batch_result: AnkiCardContentsCollection = await self.client.chat.completions.create(
                model=self.model,
                messages=[
                    {'role': 'system', 'content': CONTENT_PROMPT},
                    {'role': 'user', 'content': content_input},
                ],
                response_model=AnkiCardContentsCollection,
                max_tokens=self.max_tokens_per_query,
                temperature=self.temperature,
                api_key=self.api_key,
            )
            yield batch_result.card_contents

    async def query_single_card(self, word: str) -> AnkiCardInfo:
        async for batch in self.query(word):
            if batch:
                return batch[0]
        raise ValueError(f"No card content generated for {word}")
