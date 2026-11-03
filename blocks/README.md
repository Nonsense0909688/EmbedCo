# Block definitions

Each built-in block category lives in its own YAML file under `categories/`.

- `lights.yaml` — LEDs, lights and strips
- `sensors.yaml` — sensor inputs and readings
- `motors.yaml` — servos and motors
- `actions.yaml` — buzzers and output actions
- `logic.yaml` — conditions and boolean logic
- `timing.yaml` — waits, repeats and timers
- `values.yaml` — numbers, variables and math
- `communication.yaml` — serial communication
- `display.yaml` — LCD and display blocks
- `advanced.yaml` — advanced utility blocks

The generator loads all `categories/*.yaml` files in alphabetical order. Add a new
category by creating another YAML file with this structure:

```yaml
category: my_category
blocks:
  - id: my_block
    name: My Block
    inputs: []
    code: "// generated code"
```

The legacy root-level `blocks.yaml` remains in the project as a reference snapshot;
the generator now reads the split category files from this directory.
