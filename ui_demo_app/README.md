# UI Demo Architecture

`ui_demo.py` is only the executable entry point. The demo logic lives in
`ui_demo_app/` so rendering, simulated data, layout, and optional LLM analysis
can evolve independently.

- `config.py`: environment and CLI-backed runtime configuration.
- `simulator.py`: synthetic training metric stream and stats snapshots.
- `layout.py`: stable Rich layout and progress helpers.
- `plotting.py`: optional `plotext` graph renderer with a text fallback.
- `rendering.py`: Rich tables and summary panels.
- `analysis.py`: optional Gemini report generation via `GEMINI_API_KEY`.
- `app.py`: orchestration, CLI parsing, live loop, and final summary.

Generated reports go to `logs/ui_demo/KI_ANALYSE_REPORT.txt` by default.
Set `UI_DEMO_REPORT_PATH` or pass `--report-path` to override it.
