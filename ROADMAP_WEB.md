# Roadmap: Running Germanki as a Web Service

Moving `germanki` from a local-first tool to a multi-user web application requires addressing several architectural hurdles.

## 1. Authentication & Multi-Tenancy
Current sessions are anonymous and tied to cookies. A web service needs:
- **User Accounts:** Registration and login (OAuth2/OpenID Connect or Email/Password).
- **Data Isolation:** Ensuring User A cannot see or modify User B's cards.
- **API Key Management:** A secure way for users to provide their own OpenAI/Pexels/Unsplash keys, or a billing system if the service provides these keys.

## 2. Media Storage
Currently, audio and images are saved to a local folder on the server.
- **Problem:** Local storage is non-persistent in most cloud environments (like Heroku, Fly.io, or Lambda) and doesn't scale.
- **Solution:** Use Object Storage (AWS S3, Google Cloud Storage, or Cloudflare R2). 
  - The app would upload generated files to a bucket.
  - The database would store the public or signed URL to the asset.

## 3. Database Scaling
SQLite is excellent for local use but has limitations with high-concurrency writes.
- **Recommendation:** Switch to a managed relational database like **PostgreSQL**.
  - Provides better support for multiple users.
  - Easier backups and point-in-time recovery.
  - Compatible with most cloud hosting providers.

## 4. The Anki Connectivity Challenge
AnkiConnect is a plugin that runs inside the Anki desktop application on the **user's computer**. A web server in the cloud cannot directly "talk" to `localhost:8765` on a user's machine.

### Solutions:
- **Option A: Anki Package (.apkg) Export:** Instead of direct sync, the web app generates a `.apkg` file that the user downloads and imports into Anki manually. This is the most reliable "web-native" approach.
- **Option B: Browser-Side Sync:** Use JavaScript in the user's browser to bridge the gap. The web app sends the card data to the browser, and the browser makes a `fetch` request to `http://localhost:8765` (AnkiConnect).
- **Option C: AnkiWeb Integration:** AnkiWeb does not have an official public API for third-party card creation, making this difficult and prone to breakage.

## 5. Deployment Architecture
- **Containerization:** The existing `Dockerfile` is a great start.
- **CI/CD:** Utilize GitHub Actions (already present in `.github/workflows/`) to automate testing and deployment.
- **Reverse Proxy:** Use Nginx or Caddy for SSL termination and static file serving.
- **Background Tasks:** Card generation (LLM + Media) can be slow. Use a task queue like **Celery** or **Arq** to handle generation in the background so the UI remains responsive.

## Summary of Next Steps
1. Implement User Authentication.
2. Refactor media handling to support S3-compatible storage.
3. Implement `.apkg` generation as a fallback for users who cannot use direct sync.
4. Migrate from SQLite to PostgreSQL.
