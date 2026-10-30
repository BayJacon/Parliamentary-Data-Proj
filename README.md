# .order().order() #

A project designed to automate downloading debates using the Hansard API, transform them into a useable database, and then mine them for insights, content and predictions.

#### 1. hansard_scraperRun the cells top to bottom.
1. **Config**: set the house and date range
2. **Helpers** initialises a persistent requests.Session configured with polite headers and a custom get_json helper that handles connection timeouts, API rate limits, and server-side errors with automatic retries and backoff.
3. **Fetch the list** of debate sections from the Hansard API
4. **Filter** and print the debate IDs (check this list before going further)
5. **Download** each debate's full JSON to disk and print titles with counts
6. **Save** a summary CSV