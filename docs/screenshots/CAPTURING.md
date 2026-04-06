# UI Screenshots — Capture Guide

Place screenshot files in this directory (`docs/screenshots/`) and commit them.  
The `README.md` at the repo root references these paths.

## Required screenshots

| File | What to capture |
|------|----------------|
| `dashboard-live.png` | Full LCARS shell with all nav tiles visible and the footer status indicator showing **LIVE** |
| `env-panel.png` | Environmental panel open — BME680 pressure/humidity/VOC readings + AS7265x spectral bar chart |
| `bio-panel.png` | Biosigns panel open — MAX30102 heart-rate/SpO₂ + MLX90640 thermal readings |
| `eng-panel.png` | Engineering panel open — HLK-LD2410 radar presence/confidence + TFMini-S LiDAR distance |
| `anomaly-alert.png` | Anomaly alert toast stack visible over a panel, with the **ACK** button highlighted |
| `agent-chat.png` | Agent chat panel showing a completed inference report rendered as markdown |

## Tips

- Run the server with simulated sensors so you don't need hardware:
  ```bash
  PYTHONPATH=src python -m uvicorn mcp_server.server:app --reload
  ```
  Open `http://127.0.0.1:8000/ui/index.html`

- Recommended resolution: **1280 × 800** (or crop to that ratio) for consistent display in the README.
- Use browser devtools device-emulation if capturing on a non-Pi display.
- PNG format preferred; keep files under 500 KB each (use `pngquant` or `oxipng` if needed).
