"""Deterministic reconciliation engine. The LLM never does arithmetic or decides matches.

TODO (Day 2): implement the rules in the documented order:
shipment_unknown -> duplicate_billing -> no_pod (short-circuit, line expected = 0), then
weight_over, rate_wrong, surcharge_wrong, detention_unjustified; math_error at invoice level.
"""
