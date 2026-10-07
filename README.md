# Anderson County SC Tax Sale Analyzer v9.8

Updates from v9.7:
- Street View links in map popups now use the actual county parcel latitude/longitude (`viewpoint=lat,lng`) instead of an address-only search, preventing random Street View locations.
- Map popups prefer the county `PHYS_ADDR` when available.
- Added Zillow and Realtor.com cross-check links to map popups and property cards using a targeted web search for the physical address.
- Preserves official Anderson County parcel links and land/improved/house-clue color categories.
- External real-estate sites are cross-checks only; absence of a listing is not proof that a property has no house.
