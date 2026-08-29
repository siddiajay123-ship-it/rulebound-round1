# RuleBound Round 1 — Architecture

## Contract boundary
The generative side is represented by a typed **LayoutProposal**: `room_id`, a deterministic ordered list of placements (`placement_id`, released `sku`, `finish_id`, `family`, `x_mm`, `y_mm`, `rotation_deg`) and a short intent/requirement summary. The proposal contains no price decisions. The deterministic side returns a **ConstraintResult**: the same placements after repair, a sorted list of structured violations (`violation_id`, `rule_id`, affected placement IDs, measured/required values and repair options), and `status = valid | unsatisfiable`. Only a `valid` result crosses into pricing.

## Arbitration
The model/generator may choose product families, released SKUs, finishes, quantities and an initial 2D arrangement. Once the proposal crosses the seam, geometry and pricing are deterministic. The model cannot waive a rule, edit a violation, set a price, or declare a layout valid. The rule engine owns acceptance.

Repair is a bounded local-search loop. For each pass the engine validates all hard rules, selects the first violation in stable `(rule_id, violation_id)` order, and tries deterministic candidate moves (grid positions and rotations) for the affected placement(s). A candidate is accepted **only if the hard-violation count strictly decreases**. The measure is `M = number of hard spatial violations`; therefore every accepted pass decreases `M` by at least one. The loop is bounded by `8 * placement_count + 8` passes. If no move decreases `M`, repair stops and the engine emits `status: unsatisfiable` with the remaining violations and customer-readable trade-offs. There is no re-prompt-and-hope path.

For the demo, `--demo-violation` deliberately injects one deterministic overlap into ROOM-01 and sends it through the exact same arbitration path; the console records the before/after measure.

## Deterministic pricing
Pricing runs only after a valid layout. It groups placements by `(sku, finish_id)`, uses integer INR and basis points, round-half-up only for fractional rupees, applies quantity discount to base amount, then one labour band and one freight band. Every component carries a trace naming `CATALOG` or its rule ID and exact source inputs. Incompatible/unpriced lines block the quote.

## Unsatisfiable outcome
A human sees the retained placements, structured rule violations, `status: unsatisfiable`, and explicit trade-offs describing what requirement could not be met. The quote is `blocked` under `RB-PRC-013`; no fake price is emitted.

## Reproducibility
The command is:

`python3 starter/python/runner.py --input {input} --output {output}`

For the released pack this is `python3 starter/python/runner.py --input data --output OUTPUT`.

Determinism check: `python3 tools/check_determinism.py --command 'python3 starter/python/runner.py --input {input} --output {output}' --input data --work-dir .determinism-check`

JSON is UTF-8, sorted keys, two-space indentation and a trailing newline. No timestamps, random IDs, network calls or probabilistic model calls are used.
