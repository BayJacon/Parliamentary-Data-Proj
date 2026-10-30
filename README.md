#### .order().order() ####

A project designed to automate downloading debates using the Hansard API, transform them into a useable database, and then mine them for insights and content.

# 1. hansard_scraper
Use the configuration cell to set the date range and/or number of files to download. Amend list of filtered material as needed to ensure non-substantive (apolitical) material doesn't get downloaded in the first place.
The "Data Acquisition & Helper Utilities" cell initialises a persistent requests.Session configured with polite headers and a custom get_json helper that handles connection timeouts, API rate limits, and server-side errors with automatic retries and backoff. It also includes an HTML-stripping utility to extract clean, plain-text transcripts from the raw Hansard API responses for analysis.
Metadata harvesting cell queries Hansard's API search endpoint to page through and retrieve raw index listings of scheduled debates within the specified date range. It handles pagination automatically and enforces limits to prevent infinite loops, saving the complete list as a local JSON file to act as the master registry for subsequent downloads.
Content filtering and selection cleanses the raw metadata by filtering out irrelevant sittings (e.g., Westminster Hall debates or procedural points) based on a blocklist, leaving only main chamber debates within your targeted date range for down-stream processing.
The bulk download cell downloads full transcript details for each validated debate ID, stores the raw responses as local files, and extracts key metrics such as speaker count, total text word-count, and overall item counts.
Finally, the script compiles the processed metadata into a structured CSV file for easy analytical use and flags potential anomalies, such as empty or unusually short debates, for manual inspection.
