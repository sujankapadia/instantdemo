Analyze the codebase to understand what this application does and how it works.

1. **Read product context**: README, CLAUDE.md, docs/, any marketing or onboarding copy
2. **Read route definitions**: Find the router config (React Router, Next.js pages/, SvelteKit routes/, Vue Router, etc.) to understand all available screens
3. **Read top-level page components**: For each route, read the main page component to understand what it renders. Don't read every file — just the page-level components.
4. **Check for seed data / fixtures**: Look for `seed.py`, `fixtures.json`, `docker-compose.yml`, database migrations, or setup scripts that populate the app with sample data
5. **Check for auth**: Is there a login? Look for dev credentials in `.env.example`, README, or a local auth bypass. Note what's needed to access the app.

Summarize what the app does, list the main screens/features, note any seed data setup, and describe how to access the app (auth, ports, etc).
