import json
from pathlib import Path
from typing import Final, Any

import yaml
import litellm
import instructor
from pydantic import BaseModel

from germanki.core import AnkiCardInfo
from germanki.static import input_examples


class AnkiCardContentsCollection(BaseModel):
    card_contents: list[AnkiCardInfo]

    def to_yaml(self) -> str:
        return yaml.dump(self.model_dump()['card_contents'])


LLM_PROMPT: Final[
    str
] = """
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
- Provide three example sentences using B1-level vocabulary in the "examples" field. At least one example should use Perfekt.
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

WEB_UI_LLM_PROMPT: Final[str] = (
    LLM_PROMPT
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
        max_tokens_per_query: int = 500,
        temperature: float = 0,
    ):
        self.model = model
        self.max_tokens_per_query = max_tokens_per_query
        self.temperature = temperature
        self.api_key = api_key

        # Set API key for litellm if provided
        if api_key:
            # We can set it directly in litellm
            # litellm will use the appropriate env var or parameter based on the model
            # For simplicity, we can pass it in the completion call as well.
            pass

        self.client = instructor.from_litellm(litellm.acompletion)

    async def query(self, prompt: str) -> AnkiCardContentsCollection:
        # litellm requires the model to be passed in completion
        # instructor handles the response_model and parsing
        return await self.client.chat.completions.create(
            model=self.model,
            messages=[
                {
                    'role': 'system',
                    'content': LLM_PROMPT,
                },
                {'role': 'user', 'content': prompt},
            ],
            response_model=AnkiCardContentsCollection,
            max_tokens=self.max_tokens_per_query,
            temperature=self.temperature,
            api_key=self.api_key,
        )

    async def query_single_card(self, word: str) -> AnkiCardInfo:
        prompt = f"Provide information for the word: {word}"
        collection = await self.query(prompt)
        if not collection.card_contents:
            raise ValueError(f"No card content generated for {word}")
        return collection.card_contents[0]
