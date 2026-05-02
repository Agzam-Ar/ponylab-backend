import asyncio
import os
import sys
from pathlib import Path
import traceback

from openai.resources.realtime.realtime import log

from server.config import Config

sys.path.insert(0, str(Path(__file__).parent.parent))

from contextlib import asynccontextmanager

from fastapi import FastAPI, Response

from ai.analyze import AnalysisResult, analyze
from camera.capture import Camera
from data.yieldizer import fetch_state, send_command, set_parameter
from logic.control import Controller
from logs.plant_log import PlantLog

REFRESH_TIME = int(os.getenv("REFRESH_TIME", 60 * 10))
PLANT_TYPE = os.getenv("PLANT_TYPE", "tomato")


class GreenhouseServer:
    camera: Camera
    controller: Controller
    plant_log: PlantLog

    def __init__(self):
        self.camera = Camera()

        self.controller = Controller(Config.rules)
        self.plant_log = Config.log
        self._state_cache = {}
        self._analysis_cache: AnalysisResult | None = None
        self._loop_task = None

    async def get_sensors(self):
        state = await fetch_state()
        self._state_cache = {
            "ph": state.values.ph,
            "ec": state.values.ec,
            "temp_solution": state.values.temp_solution,
            "temp_air": state.values.temp_air,
            "humidity_air": state.values.humidity_air,
            "co2": state.values.co2,
            "light": state.values.light,
            "level": state.values.level,
            "uptime": state.uptime,
            "wifi": state.wifi,
            "description": state.description,
            "errors": state.errors,
        }
        return self._state_cache

    def get_image(self):
        return self.camera.get_stream()

    async def _update_analysis(self):
        image = self.camera.get_stream()
        if not image:
            self._analysis_cache = None
            # {"error": "No image available"}
            return

        try:
            state = await fetch_state()
            self.plant_log.state_snapshot(state)

            # state = await self.get_sensors()

            result = await asyncio.to_thread(analyze, image, state)
            self.plant_log.analysis_snapshot(result)

            # LOGIC модуль: корректирует и отправляет параметры в теплицу
            adjusted = await self.controller.process(result, state)

            self._analysis_cache = result
            # self._analysis_cache = {
            #     "stage": result.growth_stage,
            #     "health": result.health,
            #     "disease": result.disease,
            #     "params": adjusted,
            # }

            # Логируем анализ
            # self.plant_log.log_ai_analysis(result)

        except Exception as e:
            print(f"[Server] Analysis error: {e}")
            traceback.print_exc()
            self._analysis_cache = None
            # {
            #     "stage": "unknown",
            #     "health": 0.5,
            #     "disease": "unavailable",
            #     "params": {},
            #     "last_error": str(e),
            # }

    def get_analysis(self):
        return self._analysis_cache

    async def _run_loop(self):
        while True:
            try:
                print("Running analysis loop...")
                await self._update_analysis()
            except Exception as e:
                print(f"Analysis error: {e}")
            await asyncio.sleep(REFRESH_TIME)

    def start_loop(self):
        self._loop_task = asyncio.create_task(self._run_loop())

    def stop_loop(self):
        if self._loop_task:
            self._loop_task.cancel()


server = GreenhouseServer()


@asynccontextmanager
async def lifespan(app: FastAPI):
    server.start_loop()
    yield
    server.stop_loop()


app = FastAPI(lifespan=lifespan)


@app.get("/api/sensors")
async def sensors():
    return await server.get_sensors()


@app.get("/api/image")
async def image():
    img = server.get_image()
    return Response(content=img, media_type="image/jpeg")


@app.get("/api/analysis")
async def analysis():
    return server.get_analysis()


# @app.post("/api/command")
# async def command(cmd: dict):
#     return await send_command(cmd)


if __name__ == "__main__":
    import uvicorn

    port = int(os.getenv("PORT", 8080))
    uvicorn.run(app, host="0.0.0.0", port=port, access_log=False)
