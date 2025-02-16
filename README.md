[![code style blue](https://img.shields.io/badge/code%20style-blue-4495d1.svg)](https://github.com/invenia/Blue)
[![codecov](https://codecov.io/gh/gabriel-rp/germanki/graph/badge.svg?token=BT3BBAOSBW)](https://codecov.io/gh/gabriel-rp/germanki)
[![Quality Gate Status](https://sonarcloud.io/api/project_badges/measure?project=gabriel-rp_germanki&metric=alert_status)](https://sonarcloud.io/summary/new_code?id=gabriel-rp_germanki)

# GermAnki
Make Anki German vocabulary card creation less time-consuming with GermAnki.

This is only possible thanks to [AnkiConnect](https://foosoft.net/projects/anki-connect/), [TTSMP3](https://ttsmp3.com/), and [Pexels](https://www.pexels.com/). Thanks!

# Features
1. Automatically include pronunciation audio to your card.
2. Automatically include a relevant image to your card.

<img src="docs/img/preview.png">

# ChatGPT Input Mode
If you have an OpenAI API key, Germanki will prompt ChatGPT and create all your card contents for you. Just enter the word or expressions you want to generate a card for.

# Customizations
## Change Speaker's Voice
Choose among available voices to pronounce the German text the front of your card.

## Refresh Image
Is the first image pick not good enough? Click the _Refresh Images_ button and get a new random one.

# Requirements
1. Install the [AnkiConnect](https://ankiweb.net/shared/info/2055492159) add-on.
2. Add support these three fields in your `Basic` Anki card type: `Front`, `Back`, and `Extra`.

Optional:
1. Create an account on [Pexels](https://www.pexels.com/) and create your API key. It's free. Then set the environment variable `PEXELS_API_KEY` to your key.

    **Required to have images in your cards**

2. Create an account on [ChatGPT](https://chatgpt.com/) to generate inputs for you.
3. Generate an OpenAI API Key and add it to Germanki so that it can generate the card contents for you.

    **Required to have ChatGPT Input Mode**

# Run
1. Clone this repository
2. Install [poetry](https://python-poetry.org/docs/)

Then, inside the repository:
```sh
# install the dependencies
poetry install
# set your Pexels API key if you have one
export PEXELS_API_KEY=<your-api-key>
# set your OpenAI API key if you have one
export OPENAI_API_KEY=<your-api-key>
# run the app
poetry run germanki
```
Then go to http://localhost:8501/.

# Alternatively, use Docker
```bash
docker run -p 8501:8501 gabrielrphub/germanki:latest
```
Then go to http://localhost:8501/.

# Anki Cards
By default, this is how the GermAnki is programmed to work.

**Front:**
- The German word.
- A pronunciation audio.

**Back:**
- The English translations.
- A relevant picture to help with memorization.

**Extra:**
- Description, example, and other information relevant for the word type e.g. perfect form of verbs, article and plural form of nouns.

Example:
<img src="docs/img/dog_card.png">
