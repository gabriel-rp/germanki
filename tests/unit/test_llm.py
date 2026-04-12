import pytest
from unittest.mock import AsyncMock, patch
from germanki.llm import LLMAPI, AnkiCardContentsCollection
from germanki.core import AnkiCardInfo

@pytest.mark.asyncio
async def test_llm_query():
    # Mocking instructor's patched litellm
    with patch("instructor.from_litellm") as mock_instructor:
        mock_client = AsyncMock()
        mock_instructor.return_value = mock_client
        
        expected_card = AnkiCardInfo(
            word="Hund",
            translations=["dog", "hound"],
            definition="Ein Tier mit vier Beinen.",
            examples=["Der Hund bellt.", "Ich habe einen Hund."],
            extra="der Hund, -e",
            image_query_words=["dog"]
        )
        
        mock_client.chat.completions.create.return_value = AnkiCardContentsCollection(
            card_contents=[expected_card]
        )
        
        llm = LLMAPI(api_key="fake-key")
        result = await llm.query("Hund")
        
        assert len(result.card_contents) == 1
        assert result.card_contents[0].word == "Hund"
        assert result.card_contents[0].translations == ["dog", "hound"]

@pytest.mark.asyncio
async def test_llm_query_single_card():
    with patch("instructor.from_litellm") as mock_instructor:
        mock_client = AsyncMock()
        mock_instructor.return_value = mock_client
        
        expected_card = AnkiCardInfo(
            word="Hund",
            translations=["dog", "hound"],
            definition="Ein Tier mit vier Beinen.",
            examples=["Der Hund bellt.", "Ich habe einen Hund."],
            extra="der Hund, -e",
            image_query_words=["dog"]
        )
        
        mock_client.chat.completions.create.return_value = AnkiCardContentsCollection(
            card_contents=[expected_card]
        )
        
        llm = LLMAPI(api_key="fake-key")
        result = await llm.query_single_card("Hund")
        
        assert result.word == "Hund"
        assert result.translations == ["dog", "hound"]
