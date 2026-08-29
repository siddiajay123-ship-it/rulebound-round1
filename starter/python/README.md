# RuleBound Python implementation

## Run

Released pack:

```bash
python3 starter/python/runner.py --input data --output OUTPUT
```

Generic judge form:

```bash
python3 starter/python/runner.py --input <input-directory> --output <output-directory>
```

No third-party Python packages are required.

## Verification

```bash
python3 tools/verify_pack.py
python3 tools/validate_output.py OUTPUT
python3 tools/check_determinism.py --command 'python3 starter/python/runner.py --input {input} --output {output}' --input data --work-dir .determinism-check
```

## Demo repair

To deliberately inject one overlap into ROOM-01 and send it through the same arbitration loop:

```bash
python3 starter/python/runner.py --input data --output DEMO --demo-violation
```

The console prints the injected rule and the number of repair passes.
