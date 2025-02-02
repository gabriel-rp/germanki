import streamlit as st

from germanki.ui import UIController

# Important state
if 'ui' not in st.session_state:
    st.session_state['ui'] = UIController()
ui = st.session_state['ui']

# UI
st.set_page_config(page_title='GermAnki', layout='wide', page_icon='🦠')
st.title('GermAnki 🦠')
columns = st.columns(spec=[3, 2, 7])

# Card Data Input
with columns[0]:
    cards_input = st.text_area(
        'YAML-formatted list with fields `front`, `back`, `extra`',
        value=ui.default_input_text(),
        height=ui.page_height,
    )

# Parameters & Buttons
with columns[1]:
    with st.container(border=False, height=ui.page_height):
        deck_name = st.text_input('Deck Name', 'Germanki Deck')
        selected_speaker_input = st.selectbox(
            'Select Speaker:',
            ui.speakers,
            index=ui.speakers.index(ui.selected_speaker),
        )

        if st.button('Preview Cards', icon='👀', type='primary'):
            ui.preview_cards_action(cards_input, selected_speaker_input)

        if st.button('Create Cards', icon='➕', type='primary'):
            ui.create_cards_action(deck_name)

# Preview
with columns[2]:
    with st.container(border=False):
        ui.refresh_preview_action()
