"""FairLend Watch read-only JSON API (Phase 12A) for the web interface in web/.

It imports the existing engine in src/ and only lays its results out as JSON: no detection logic lives
here, so every number matches the Streamlit app. Presentation mode, demo data only, GET only.
All data is synthetic. A flag is a prompt for a human to look, not a verdict.
"""
