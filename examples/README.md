# Examples

Run examples from repository root after installing dependencies:

```bash
uv sync
uv sync --extra numpy
```

Basic API:

```bash
uv run python examples/basic_usage.py 1.psdata
```

NumPy API:

```bash
uv run python examples/numpy_usage.py 1.psdata --step 500
```

Export API:

```bash
uv run python examples/export_usage.py 1.psdata --out 1.psdata.decoded.example
```
