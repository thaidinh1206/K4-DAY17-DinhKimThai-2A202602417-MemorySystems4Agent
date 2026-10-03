# Day 17 implementation

The offline implementation runs without an API key and gives deterministic answers so both agents can be benchmarked on identical input.

- `config.py` and `model_provider.py`: shared configuration and lazy model factory for six providers.
- `memory_store.py`: `User.md` persistence, Vietnamese fact extraction, token estimation, and compact memory.
- `agent_baseline.py`: full history within one thread only.
- `agent_advanced.py`: persistent user profile and compact per-thread history.
- `benchmark.py`: standard and long-context comparisons.
- `test_agents.py`: memory behavior checks.

Run from the repository root:

```powershell
.venv/Scripts/python.exe src/benchmark.py
.venv/Scripts/python.exe -m pytest src/test_agents.py -v
```

The benchmark writes profiles under ignored `state/benchmark_*` folders and resets dataset users before each run. See `../Report.md` for sample results and interpretation. The provider factory is available for a later live-agent extension; both agents currently run in offline mode.
