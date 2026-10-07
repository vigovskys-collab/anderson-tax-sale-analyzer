# Anderson County SC Tax Sale Analyzer v9.5

Changes from v9.4:
- Google map now gets all available county SSAP GPS points in one browser-side request instead of dozens of smaller requests.
- Google map markers are positioned at their actual county GPS coordinates rather than all being placed at Anderson.
- Green markers = no county IMPRV value; orange markers = county IMPRV value.
- Map filter: All / Land only / County-improved / House clue.
- Streamlit property-type filter: all / land-no-house-clue / house-indicated / mobile homes.
- 5+ acre quick filter.
- Exact Anderson County parcel links remain direct and bypass the disclaimer screen.

Note: County IMPRV is an improvement indicator. It is not by itself proof that an improvement is a house. House-clue filtering is based on words in the tax-sale property description.
