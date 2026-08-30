"""
The intelligence layer.

Three deliberately separate pieces:

* ``forecast_model``      - short-term price direction from historical prices.
* ``matching_model``      - explainable weighted scoring of a buyer against a lot.
* ``recommendation_engine`` - net realization, ranking, sale window and the
  human-readable "why".

None of this is a black box, and none of it is trained on transaction history
we do not have. Everything here is arithmetic that can be shown to a farmer and
defended line by line.
"""
