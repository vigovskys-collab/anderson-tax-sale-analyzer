# Anderson County SC Tax Sale Analyzer — v4

Adds a configurable Maximum Bid / Bidding Strategy module.

For each property, the model starts with county GIS market value (or assessed value if GIS market value is unavailable), then subtracts:
- repair / cleanup reserve
- holding / carrying reserve
- transaction / closing reserve
- transparent risk reserve
- desired profit/equity margin

The resulting maximum is also capped at a user-selected percentage of estimated value.

Risk reserve automatically increases when the app detects flood, access, water, zoning, or mobile/manufactured-home risk indicators.

The model is a planning aid, not an appraisal, legal opinion, title opinion, or guarantee of profit. Independently verify title, liens, redemption, access, zoning, flood exposure, physical condition, marketability, and auction requirements.
