# Anderson County Tax Sale Analyzer v10.1

This version fixes the map property classification logic.

### Map categories
- Green: Land / other
- Red: House indicated — includes Anderson County `CLASS=R` residential/homestead parcels, explicit house clues, or web-house evidence when available.
- Blue: Mobile home — explicit mobile/manufactured clue or web-mobile evidence.

### Important county-data distinction
Anderson County documents `CLASS=R` as the 4% class that usually means a legal residence/homestead, while `CLASS=A` is agricultural and `CLASS=C` is 6%. The county also documents `IMPRV` as improvements that can include a house, fence, barn, concrete, pole barn, garage, etc.; therefore IMPRV alone is not treated as proof of a house.

The map also retains Zillow/Realtor.com/Redfin cross-reference links. Those sites are evidence only; absence of a web record does not prove vacant land.
