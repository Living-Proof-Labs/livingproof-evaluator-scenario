# sim-v3.8.1-g1-playground

A real recording of a standing-and-walking G1 trial that passes the fall step
(livingproof-evaluator-scenario#32). Machine-readable form: `PROVENANCE.json`, which
`tests/test_fall_pass_fixture.py` checks against this file and the binding.

## What produced the recording

- **Robot:** `livingproof-unitree-g1` `main` at `0612df10a3bda9495485786fa5c5a0d4220b6c7b`
  (`0612df1`), configuration `playground`, adapter `lpl_g1.adapter:ROBOT`.
- **Runner:** `livingproof-sim-mujoco` v3.8.1 (`2ed053f77b08c0e7567746b37244f74730ff3cac`), its
  `evidence` then `media` modules. Commands: `generate.py.txt`.
- **Limit set** (time 27.0 s, lateral 0.49 m, half width 0.75 m, fall 0.50 m): taken from
  livingproof-verification run 43402628666 (`tests/fixtures/lpv-run-43402628666/
  g1-playground-result-01.json`). That run's observation is byte-identical to this one's.

## What did not produce it

The lock used to drive the run is livingproof-verification's playground hallway lock. It names
G1 `v2.3.12` and sim v3.6.2. Those are the lock's nominal pins only. They did not produce this
recording: the run used G1 `0612df1` and sim v3.8.1 above, because v3.8.1 needs a newer robot.
