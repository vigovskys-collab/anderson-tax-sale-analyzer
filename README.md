# Anderson County SC Tax Sale Analyzer v10.5

This version adds a county-data property identification engine using Anderson County GIS sources in the browser:
- Parcel fallback matching (primary + NewPropertyViewer parcel layer)
- County E911/SSAP address data, including mobile-home number (MH_NUM)
- Current Land Use (including Vacant)
- Parcel zoning
- County CLASS/IMPRV data
- Existing online evidence when available

Classification is conservative:
- Blue = mobile/manufactured evidence
- Red = house/structure indicated
- Green = positive land evidence
- Orange = unknown / needs verification

Unknown is never treated as vacant land.
