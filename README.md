## Architecture

```
backend/
├── server/       FastAPI HTTP server + static files
├── data/        REST API communication with Yieldizer
├── camera/     Raspberry Pi camera capture  
├── ai/         Plant analysis via local LLM
├── logic/      Parameter bounds & adjustment
└── logs/      Plant growth history
```

## Modules

### server
HTTP server endpoints:
- `GET /api/sensors` - Current sensor values
- `GET /api/image` - Camera feed (JPEG)
- `GET /api/analysis` - AI analysis results
- `POST /api/command` - Send command to Yieldizer

### data
Communicates with Yieldizer REST API (`YIELDIZER_URL`):
```python
state = await fetch_state()
await send_command({"type": "reset_errors"})
await set_parameter("nsolution", "ph_down_trig", 6.3)
```

### camera
- Tries picamera2 first
- Falls back to placeholder.png if unavailable
- Other modules unaware of fallback

### ai
- Sends image + sensor data to local LLM
- Returns: growth_stage, health, disease, recommended_params
- Recommended params: temp, humidity, ec, ph

### logic
- Loads plant bounds from CSV (`data/plants/{plant}.csv`)
- Clamps AI recommendations to safe bounds
- Example tomato.csv stages: seedling, vegetative, flowering, fruiting

### logs
- JSON event log per plant
- Event types: planted, sensor_change, ai_analysis

## Environment

```bash
YIELDIZER_URL=http://192.168.4.1:80
REFRESH_TIME=60
LLM_BASE_URL=http://127.0.0.1:11435/v1
PLANT_TYPE=tomato
PORT=8080
```

## Run

```bash
pip install -r requirements.txt
python -m backend.server.main
```