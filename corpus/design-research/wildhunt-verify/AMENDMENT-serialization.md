# Serialization-only amendment after the first execution

The first execution finished both measurement waves but failed while writing JSON:
`TypeError: Object of type int64 is not JSON serializable`. No score file was written
and no score values or gate verdicts were inspected. Progress output listed specimen
IDs only. The failed attempt is disclosed, not treated as a successful receipt.

Cause: a comparison with NumPy's epsilon yields a NumPy boolean, and summing those
booleans yields a NumPy integer. The JSON boundary accepted only Python scalars.

Repair: `catalog.write_json` converts only NumPy scalars with `.item()`, preserving
numeric and Boolean values, and rejects nonfinite JSON numbers. A regression test
checks counts, false values, decimals and NaN rejection. `evaluate.py` accepts an
explicit immutable freeze-record path so the original `freeze.json` remains intact;
the console summary casts its count to a Python integer. No formula, label, pair,
threshold, feature setting, metric implementation or protocol text changed.

The corrected complete run uses `freeze-serialization-fix.json`, created before its
execution. `preregistration.json` still fixes the original PROTOCOL/config hashes.
The original and amended code-hash differences are recorded in
`serialization-amendment.json`. No failed result is relabeled as successful.
