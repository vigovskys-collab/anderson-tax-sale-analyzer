# Anderson County SC Tax Sale Analyzer v10.0

New in v10.0:
- Selected-property web cross-reference for Zillow, Realtor.com, and Redfin.
- Extracts bedrooms, bathrooms, and square footage from public search-result snippets when available.
- Strong house evidence requires at least two of those property facts; mobile/manufactured wording is separately flagged.
- No match is never treated as proof that a parcel is vacant land.
- Existing map, county parcel, Google Maps, Street View, acreage, bid, and property-type filters are preserved.

The web cross-reference runs on demand for the selected property and is cached for 24 hours to avoid repeatedly querying the same address.
