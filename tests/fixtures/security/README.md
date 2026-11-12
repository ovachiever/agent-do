# Security advisory regression fixtures

These files are minimized **offline test extracts**, not a CVE database or complete
advisories. Runtime assessment queries the configured official advisory source.
Each JSON file records its public NVD mirror source URL and retrieval date.

| Fixture | Retained regression evidence |
| --- | --- |
| CVE-2012-1531 | Oracle JDK legacy base/update bounds, including `1.4.2_38`. |
| CVE-2012-1723 | Oracle JDK upper bound `1.4.2_37`. |
| CVE-2021-21349 | XStream range and historical Oracle Java SE `7u`/`8u` entries. |
| CVE-2022-21426 / CVE-2022-21434 | Oracle JDK versions and unrelated escaped NetApp product predicates. |
| CVE-2022-21449 | Oracle JDK 17.0.2/18 and unrelated escaped NetApp predicates. |
| CVE-2023-41993 | Apple, historical Oracle JDK and escaped WebKit product predicates. |
| CVE-2024-21235 | Oracle JDK exact versions, including the positive 17.0.12 match. |

Unrelated OR alternatives and redundant enumerations of old Java versions are
omitted. Included CPE criteria, vulnerability flags and version bounds retain the
source values. AND prerequisites and negated branches must be kept together when
minimizing a fixture. Opaque match IDs and unused CVSS component fields are omitted;
rating source, vector and base score remain where normalization is exercised.

Do not replace regression predicates with a hand-written CVE suppression. Tests
must preserve affected-version positives alongside modern/patched negatives, and
unsupported related semantics must remain uncertain. Use synthetic fixtures for
other parser shapes; do not describe them as full upstream snapshots.
