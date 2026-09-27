import pytest
from unittest.mock import AsyncMock, patch, MagicMock
from germanki.llm import LLMAPI, AnkiCardContentsCollection, PreprocessedCollection, PreprocessedWord
from germanki.core import AnkiCardInfo

@pytest.mark.asyncio
async def test_llm_query():
    # Mocking instructor's patched litellm
    with patch("instructor.from_litellm") as mock_instructor:
        mock_client = AsyncMock()
        mock_instructor.return_value = mock_client
        
        # Step 1 mock (Preprocess)
        mock_preprocess = PreprocessedCollection(
            words=[PreprocessedWord(normalized_word="Hund", category="noun")]
        )
        
        # Step 2 mock (Content)
        expected_card = AnkiCardInfo(
            word="Hund",
            translations=["dog", "hound"],
            definition="Ein Tier mit vier Beinen.",
            examples=[
                "Der Hund bellt.", 
                "Der Hund bellte gestern.", 
                "Ich habe einen Hund gehabt.", 
                "Ich werde einen Hund haben.",
                "Der Hund wird geliebt."
            ],
            extra="der Hund, -e",
            image_query_words=["dog"]
        )
        mock_content = AnkiCardContentsCollection(
            card_contents=[expected_card]
        )
        
        # side_effect to return different models for different calls
        mock_client.chat.completions.create.side_effect = [mock_preprocess, mock_content]
        
        llm = LLMAPI(api_key="fake-key")
        
        cards = []
        async for batch in llm.query("Hund"):
            cards.extend(batch)
        
        assert len(cards) == 1
        assert cards[0].word == "Hund"
        assert len(cards[0].examples) == 5

@pytest.mark.asyncio
async def test_llm_query_single_card():
    with patch("instructor.from_litellm") as mock_instructor:
        mock_client = AsyncMock()
        mock_instructor.return_value = mock_client
        
        # Step 1 mock (Preprocess)
        mock_preprocess = PreprocessedCollection(
            words=[PreprocessedWord(normalized_word="Hund", category="noun")]
        )
        
        # Step 2 mock (Content)
        expected_card = AnkiCardInfo(
            word="Hund",
            translations=["dog", "hound"],
            definition="Ein Tier mit vier Beinen.",
            examples=[
                "Der Hund bellt.", 
                "Der Hund bellte gestern.", 
                "Ich habe einen Hund gehabt.", 
                "Ich werde einen Hund haben.",
                "Der Hund wird geliebt."
            ],
            extra="der Hund, -e",
            image_query_words=["dog"]
        )
        mock_content = AnkiCardContentsCollection(
            card_contents=[expected_card]
        )
        
        mock_client.chat.completions.create.side_effect = [mock_preprocess, mock_content]
        
        llm = LLMAPI(api_key="fake-key")
        result = await llm.query_single_card("Hund")
        
        assert result.word == "Hund"
        assert len(result.examples) == 5
