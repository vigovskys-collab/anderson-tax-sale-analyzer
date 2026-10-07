# Anderson County SC Tax Sale Analyzer v9.7

- Queries the official Anderson County parcel layer directly by TMS in small batches.
- Uses parcel geometry for actual map locations and returns county IMPRV/market-value fields.
- Uses Google Maps when a valid key is supplied; otherwise automatically falls back to a key-free Leaflet/OpenStreetMap interactive map.
- Keeps Google Maps, Street View, and direct Anderson County parcel links.
- Keeps land/house-clue/county-improved colors and map filtering.
