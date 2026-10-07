# Anderson County SC Tax Sale Analyzer v9.4

- Direct official Anderson County Property Viewer links using the TMS.
- Uses `disclaimer=false`, so the manual disclaimer checkbox is skipped.
- Removes the failing live county-coordinate lookup that caused the timeout.
- Keeps Google Maps/Street View as optional research tools.
- Keeps strict acreage parsing: a number counts as acreage only when followed by AC/ACRES.
