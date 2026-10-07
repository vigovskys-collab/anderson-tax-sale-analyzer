# Anderson County SC Tax Sale Analyzer v9.9.1

This build fixes two problems from v9.9:

- Map marker colors now actually use the property-type classification: green = Land / other, red = House indicated, blue = Mobile home.
- The map property-type dropdown now filters those same three categories.
- Zillow and Realtor.com buttons now send a correctly formed Google site-search for the exact property address instead of the broken `+a+` query.

The external listing searches are research aids only. A missing Zillow/Realtor result does not prove that a property has no house.
