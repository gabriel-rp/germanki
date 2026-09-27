# Proposal: Persistent Card Storage Database

## Current Situation
Currently, `germanki` uses a session-based SQLite database (`sessions` table) where all session data, including the list of cards, is stored as a single JSON blob. 

**Limitations:**
- **Transience:** Cards are tied to a session ID. If the session expires or the cookie is cleared, pending cards are lost.
- **Atomic Operations:** Updating a single card requires reading the entire session, modifying the JSON, and writing it back.
- **Status Tracking:** There's no robust way to track which cards have been successfully synced to Anki and which are still pending.
- **Historical Data:** Once cards are synced, they are typically cleared from the session, leaving no local record.

## Proposed Change
We propose decoupling card storage from the session and creating a dedicated `cards` table.

### Schema Design
A new table `cards` will be added to `germanki.db`:

| Column | Type | Description |
| :--- | :--- | :--- |
| `id` | UUID/TEXT | Unique identifier for the card. |
| `user_id` | TEXT | Identifier for the user/session that owns the card. |
| `front` | TEXT | Front content (German word/phrase). |
| `back` | TEXT | Back content (Translation/Meaning). |
| `example` | TEXT | Usage example. |
| `audio_path` | TEXT | Local path or URL to the generated audio. |
| `image_path` | TEXT | Local path or URL to the generated image. |
| `deck_name` | TEXT | Target Anki deck. |
| `status` | TEXT | `pending`, `synced`, or `failed`. |
| `created_at` | DATETIME | When the card was generated. |
| `synced_at` | DATETIME | When the card was successfully sent to Anki. |

### Workflow Enhancements
1. **Auto-Save:** As soon as ChatGPT generates cards or they are manually entered, they are persisted to the `cards` table with a `pending` status.
2. **Review Queue:** A new "Pending Sync" view in the UI will allow users to review, edit, or delete cards before they ever reach Anki.
3. **Resilient Sync:** If Anki is closed during a sync attempt, the status remains `pending`, allowing for a "Retry Sync" later without re-generating content (saving API costs).
4. **Sync History:** Users can view a history of cards they've created.

## Implementation Steps
1. **Migration:** Update `SessionManager.initialize()` to create the `cards` table.
2. **Core Refactor:** Update `Germanki` service to return `Card` objects that are saved to the DB immediately.
3. **UI Updates:**
   - Add a "Saved Cards" or "Queue" tab.
   - Show a sync status indicator on each card.
   - Implement a "Sync All Pending" button.
4. **Session Cleanup:** The `UserSession` model will no longer store the full card list, only the `session_id` and UI preferences.
