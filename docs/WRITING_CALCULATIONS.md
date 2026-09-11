# Writing `core/calculations.py`

A working guide. Keep it open beside the code.

---

## Setup

Two terminal tabs makes this much easier.

**Tab 1** — leave the tests running continuously:

```bash
cd "/Users/adriendalais/Claude Sandbox [Main]/Claude projects terminal sandbox/deal-screening-workbench"
source .venv/bin/activate
pytest tests/test_calculations.py -q
```

Re-run it after every save. If you want it automatic:
`pip install pytest-watch`, then `ptw tests/test_calculations.py`.

**Tab 2** — for anything else.

Open `core/calculations.py` in your editor. You are replacing six lines
that read `raise NotImplementedError("Adrien writes this one")`.

---

## Order

Each builds on the last. Do not skip ahead.

| | Function | Line | Tests |
|---|---|---|---|
| 1 | `revenue_growth` | 124 | 9 |
| 2 | `share_of_total` | 164 | 4 |
| 3 | `margin` | 182 | 6 |
| 4 | `variant_growth_metric` | 205 | 1 |
| 5 | `rule_of_40` | 219 | 7 |
| 6 | `cagr` | 149 | 4 |

`cagr` is last because its sign-change case is the fiddliest.

---

## How to read a failure

```
E       assert None == approx(0.3275862068965518 ± 3.3e-13)
```

Left of `==` is what your function returned. Right is what the test
expected. `approx` means "close enough for floating point" — you do not
need to match to the last digit.

```
E       Failed: DID NOT RAISE <class 'BasisMismatch'>
```

The test expected your function to raise and it did not.

```
E       BasisMismatch: ...
```

It raised when it should have returned a value. Usually a guard placed
too early, or a comparison that is too strict.

---

## Function 1 — `revenue_growth`

Nine tests. Work through them in this order; each one adds one rule.

### The shape

Every function here follows the same sequence:

```
1. Check the inputs are compatible   -> raise if not
2. Check the values are usable       -> return None if not
3. Do the arithmetic                 -> return the number
```

Order matters. A currency mismatch is still a currency mismatch when one
of the values is missing, so the raises come first.

### The nine rules, in plain English

Write them roughly in this order — get one test green, then add the next.

**1. The arithmetic.** Divide the later value by the earlier, subtract 1.
Gets `test_revenue_growth_thornbury_fy23_to_fy24` and
`test_revenue_growth_can_be_negative` passing at once, because negative
growth needs no special handling — the arithmetic already produces it.

**2. Missing values.** If either `.value` is `None`, return `None`.
Use `is None`, not `== None`, and not `if not figure.value` — a value of
`0` is falsy in Python and zero is not the same as missing. This is the
single most common bug in this whole file.

**3. Growing from zero.** If `earlier.value` is zero, return `None`.
Not infinity. Not 100%. There is no growth rate from nothing.

**4. Currency.** If the two currencies differ, `raise CurrencyMismatch`
with a message naming both. You raise an exception like this:

```python
raise SomeError(f"a message with {a_variable} in it")
```

**5. Units.** If `earlier.unit != later.unit`, raise `UnitMismatch`.
Also raise it if either figure is not monetary — `Figure` has an
`is_monetary` property for exactly this.

**6. Basis.** If one figure is an actual and the other is not, raise
`BasisMismatch`. Careful: the test
`test_revenue_growth_allows_two_forecasts_to_be_compared` requires that
two forecasts *are* allowed. So the rule is "the two bases must be equal",
not "both must be actual".

**7. Period.** If both figures carry the same `period_label`, raise
`PeriodMismatch`. Comparing a period with itself is a caller bug, not a
0% result.

### Python you will need

```python
if x is None:              # test for missing. NOT `if not x`
if a != b:                 # inequality
raise CurrencyMismatch(f"...{a}...{b}...")
return None                # explicit, not a bare `return`
```

### The shape, illustrated on something unrelated

So you can see the pattern without me writing your function:

```python
def average_speed(distance_km, hours, unit_a, unit_b):
    if unit_a != unit_b:                       # incompatible -> raise
        raise ValueError(f"{unit_a} vs {unit_b}")
    if distance_km is None or hours is None:   # missing -> None
        return None
    if hours == 0:                             # undefined -> None
        return None
    return distance_km / hours                 # the arithmetic
```

---

## Functions 2 and 3 — `share_of_total` and `margin`

Same shape, fewer rules. Both take two figures covering the **same**
period, so the period rule inverts: raise `PeriodMismatch` when the
labels *differ*, which is the opposite of `revenue_growth`.

`margin` must return negative results, not suppress them. Larkspur's FY22
adjusted EBITDA is negative and that is a fact about the business.

**You will notice the validation repeating by now.** Pulling it into a
shared helper is a real improvement and it is your call — not something I
should decide for you. If you do it, the tests will tell you
immediately whether you broke anything, which is the point of having
them.

---

## Function 4 — `variant_growth_metric`

Three lines. Given a `RuleOf40Variant`, return `"arr"`, `"carr"` or
`"revenue"`. A dictionary lookup or a chain of `if`s both work.

Small, but it is the single place that knows what a variant name means,
and reconciliation will reuse it to check a label against the inputs
actually used.

---

## Function 5 — `rule_of_40`

The one with real logic. It composes what you have already written.

1. Ask `variant_growth_metric` which metric this variant needs.
2. If that metric is missing from `current` **or** from `prior`, raise
   `VariantInputMissing`. This is the Larkspur defect: a scorecard
   labelled "CARR + EBITDA" for a company reporting no CARR must fail
   loudly rather than quietly substituting ARR.
3. If `"revenue"` or `"adjusted_ebitda"` is missing from `current`, raise
   `VariantInputMissing` too — no margin can be formed without them.
4. Compute the growth with `revenue_growth`, using the prior and current
   figures of the variant's metric.
5. Compute the margin with `margin`, using adjusted EBITDA over revenue.
6. If either is `None`, return `None`. An incomplete Rule of 40 is not a
   Rule of 40.
7. Otherwise return the sum.

**Note the difference between steps 2 and 6.** A metric *absent from the
mapping* is an error — the caller asked for something impossible.
A metric *present but holding None* is simply missing data. Same outcome
on screen, completely different meanings, and the tests check both.

Checking whether a key is in a mapping:

```python
if "carr" not in current:
    raise VariantInputMissing("...")
```

---

## Function 6 — `cagr`

Like `revenue_growth`, but compounding:

```
(later / earlier) ** (1 / years) - 1
```

`**` is "to the power of" in Python.

Return `None` when either value is `None`, `earlier.value` is zero, or
`years` is zero.

The fiddly one: **return `None` if either value is negative.** A
compound rate across a sign change is not a real number — Python will
either raise or hand you a complex number, and neither belongs in a
scorecard.

There is a free sanity check in
`test_cagr_over_one_year_equals_simple_growth`: with `years=1`, `cagr`
must agree exactly with `revenue_growth`. If it does not, one of the two
is wrong.

---

## When you are done

```bash
pytest tests/test_calculations.py -q     # 31 passed
pytest tests/ -q                         # 122 passed
```

Then tell me and I will review it — looking for bugs the tests do not
catch, and for places where the code says something different from what
it means.

## If you get stuck

Ask. Describe what you tried and paste the failure. I will explain the
concept or point at the bug, but I will not write the body — that rule is
in CLAUDE.md because code you cannot defend in an interview is worse than
no code at all.
