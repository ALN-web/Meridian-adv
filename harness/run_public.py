"""Run all public tasks unattended (except OTP), store results, feed the evaluation page.

Tasks come from {PORTAL_BASE_URL}/internal/tasks.json?key=<TEAM_KEY>; the key is read from env only.
TODO: implement once the agent runner exists.
"""
