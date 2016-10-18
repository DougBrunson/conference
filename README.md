run with `python dev_appserver.py app.yaml`

Design
- sessions and speakers are ndb entities. This allows a speaker to be changed/ used across multiple sessions
- wishlists are a property of profile

Queries:
- by_location: searches sessions by location
- by_type: searches sessions by type

The problem with the problematic query is that it uses an inequality filter on two properties. Only one is allowed. I queried twice and return their intersection