@app.post("/generate")
async def generate_cards(
    request: Request,
    input_text: str = Form(...),
    input_source: str = Form("chatgpt"),
    photo_source: str = Form("pexels"),
    enable_images: str | None = Form(None),
    session: UserSession = Depends(get_session),
    service: Germanki = Depends(get_germanki_service),
):
    session.input_source = input_source
    session.input_text = input_text
    session.photo_source = photo_source
    session.enable_images = enable_images == "on"

    async def generate_stream():
        try:
            # 1. Start: Disable UI and Clear list using OOB
            yield "<div id='card-list' hx-swap-oob='true' style='list-style: none; padding: 0; margin: 0; display: grid; grid-template-columns: repeat(auto-fill, minmax(300px, 1fr)); gap: 1.5rem; width: 100%;'></div>"
            yield "<script hx-swap-oob='true'>document.getElementById('sync-button').disabled = true;</script>"

            if input_source == "chatgpt":
                if not service.config.openai_api_key:
                    yield "<div id='card-list' hx-swap-oob='true'><div class='error'>API Key missing</div></div>"
                    yield "<script hx-swap-oob='true'>document.getElementById('sync-button').disabled = false;</script>"
                    return

                input_lines = [line.strip() for line in input_text.split("\n") if line.strip()]
                
                # Filter session cards
                new_session_cards = []
                for card in session.cards:
                    if any(line.lower() in card.word.lower() or card.word.lower() in line.lower() for line in input_lines):
                        new_session_cards.append(card)
                session.cards = new_session_cards

                # Identify truly new lines
                new_lines = []
                for line in input_lines:
                    if not any(line.lower() in card.word.lower() or card.word.lower() in line.lower() for card in session.cards):
                        new_lines.append(line)

                # Show existing cards first
                if session.cards:
                    existing_html = ""
                    for i, card in enumerate(session.cards):
                        card_inner = templates.get_template("partials/card_preview.html").render(
                            {"request": request, "card": card, "index": i}
                        )
                        existing_html += f"<li id='card-item-{i}'>{card_inner}</li>"
                    yield f"<div id='card-list' hx-swap-oob='true' style='list-style: none; padding: 0; margin: 0; display: grid; grid-template-columns: repeat(auto-fill, minmax(300px, 1fr)); gap: 1.5rem; width: 100%;'>{existing_html}</div>"

                if new_lines:
                    llm = LLMAPI(api_key=service.config.openai_api_key, model=session.llm_model)
                    
                    async for batch_cards in llm.query("\n".join(new_lines)):
                        await service.populate_media(batch_cards, skip_images=not session.enable_images)
                        
                        for card in batch_cards:
                            curr_idx = len(session.cards)
                            session.cards.append(card)
                            await SessionManager.save_session(session)
                            
                            card_inner = templates.get_template("partials/card_preview.html").render(
                                {"request": request, "card": card, "index": curr_idx}
                            )
                            # Append using beforeend swap on the list
                            yield f"<div id='card-list' hx-swap-oob='beforeend'><li id='card-item-{curr_idx}'>{card_inner}</li></div>"

            else:
                import yaml
                data = yaml.safe_load(input_text)
                session.cards = [AnkiCardInfo(**item) for item in data]
                await service.populate_media(session.cards, skip_images=not session.enable_images)
                await SessionManager.save_session(session)
                
                all_html = ""
                for i, card in enumerate(session.cards):
                    card_inner = templates.get_template("partials/card_preview.html").render(
                        {"request": request, "card": card, "index": i}
                    )
                    all_html += f"<li id='card-item-{i}'>{card_inner}</li>"
                yield f"<div id='card-list' hx-swap-oob='true' style='list-style: none; padding: 0; margin: 0; display: grid; grid-template-columns: repeat(auto-fill, minmax(300px, 1fr)); gap: 1.5rem; width: 100%;'>{all_html}</div>"

            # Finalize: enable sync button
            yield "<script hx-swap-oob='true'>document.getElementById('sync-button').disabled = false;</script>"
            
        except Exception as e:
            logger.error(f"Stream error: {e}", exc_info=True)
            yield f"<div id='card-list' hx-swap-oob='beforeend'><div class='error'><strong>❌ Error:</strong> {str(e)}</div></div>"
            yield "<script hx-swap-oob='true'>document.getElementById('sync-button').disabled = false;</script>"

    return StreamingResponse(generate_stream(), media_type="text/html")
