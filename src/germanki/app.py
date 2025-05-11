import streamlit as st

from germanki.ui import InputSource, PhotoSource, UIController

# UI
st.set_page_config(page_title='GermAnki', layout='wide', page_icon='🙊')
st.title('GermAnki 🙊')
columns = st.columns(spec=[3, 2, 7])

st.markdown(
    """
<style>
    .stMainBlockContainer {
        padding: 40px;
    }
</style>
""",
    unsafe_allow_html=True,
)

# Important state
if 'ui' not in st.session_state:
    st.session_state['ui'] = UIController(InputSource.CHATGPT)
ui: UIController = st.session_state['ui']

# Card Data Input
with columns[0]:
    photo_source = st.radio(
        'Photo Source',
        options=[item.value for item in PhotoSource],
        horizontal=True,
    )

    if photo_source:
        try:
            ui.photo_source = PhotoSource.from_str(photo_source)
        except Exception as e:
            st.warning(e)

    input_method = st.radio(
        'Input Mode',
        options=[item.value for item in InputSource],
        horizontal=True,
    )

    if input_method:
        try:
            ui.input_source = InputSource.from_str(input_method)
        except Exception as e:
            st.warning(e)

    input_field = ui.create_input_field()

# Other input and buttons
with columns[1]:
    with st.container(
        border=False, height=int(ui.default_window_height * 1.7)
    ):
        deck_name = st.text_input('Deck Name', 'Germanki Deck')
        selected_speaker_input = st.selectbox(
            'Select Speaker:',
            ui.speakers,
            placeholder='Choose a speaker',
        )
        if selected_speaker_input:
            ui.select_speaker_action(selected_speaker_input)

        with st.popover('Update API Keys', use_container_width=True):
            pexels_api_key = st.text_input('Pexels API Key')
            openai_api_key = st.text_input('OpenAI API Key')
            unsplash_api_key = st.text_input('Unsplash API Key')
            if st.button('Update'):
                ui.update_api_keys_action(
                    pexels_api_key, openai_api_key, unsplash_api_key
                )

        if st.button(
            'Preview Cards',
            key='preview_chatgpt_input',
            icon='👀',
            type='primary',
            use_container_width=True,
        ):
            ui.preview_cards_action(input_field)

        if st.button(
            'Create Cards', icon='➕', type='primary', use_container_width=True
        ):
            ui.create_cards_action(deck_name)

# Preview
with columns[2]:
    with st.container(border=False):
        ui.refresh_preview()
