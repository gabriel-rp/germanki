from unittest.mock import patch

import pytest

from germanki.core import AnkiCardInfo
from germanki.ui import (
    ChatGPTUIHandler,
    InvalidManualInputException,
    ManualInputUIHandler,
    OpenAPIKeyNotProvided,
)


@pytest.fixture()
def chatgpt_handler():
    return ChatGPTUIHandler(openai_api_key='fake-key')


@pytest.fixture()
def manual_handler():
    return ManualInputUIHandler()


@patch('germanki.chatgpt.ChatGPTAPI.query')
def test_chatgpt_handler_parse(mock_query, chatgpt_handler: ChatGPTUIHandler):
    mock_query.return_value.card_contents = [
        AnkiCardInfo(
            word='Hallo',
            translations=['Hello'],
            definition='Ein Gruß',
            examples=["Hallo, wie geht's?"],
            extra='',
        )
    ]
    response = chatgpt_handler.parse('Hallo')
    assert len(response) == 1
    assert response[0].word == 'Hallo'


@patch('germanki.chatgpt.ChatGPTAPI.query', side_effect=OpenAPIKeyNotProvided)
def test_chatgpt_handler_no_api_key(mock_query):
    with pytest.raises(OpenAPIKeyNotProvided):
        ChatGPTUIHandler(openai_api_key=None)


def test_manual_handler_parse_success(manual_handler: ManualInputUIHandler):
    yaml_input = """
    - word: "Hallo"
      translations: ["Hello"]
      definition: "The definition"
      examples: ["Hello!"]
      extra: ""
    """
    response = manual_handler.parse(yaml_input)
    assert len(response) == 1
    assert response[0].word == 'Hallo'


def test_manual_handler_parse_invalid_yaml(
    manual_handler: ManualInputUIHandler,
):
    with pytest.raises(
        InvalidManualInputException, match='Invalid YAML input.'
    ):
        manual_handler.parse('invalid: yaml: data')


def test_manual_handler_parse_empty_input(
    manual_handler: ManualInputUIHandler,
):
    with pytest.raises(
        InvalidManualInputException, match='No input provided.'
    ):
        manual_handler.parse('')
