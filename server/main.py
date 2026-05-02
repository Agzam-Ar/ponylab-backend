import asyncio
from asyncio.tasks import Task
import os
import sys
from pathlib import Path
import traceback
from typing import Never


sys.path.insert(0, str(Path(__file__).parent.parent))

from contextlib import asynccontextmanager

from fastapi import FastAPI, Response

from ai.analyze import AnalysisResult, analyze
from camera.capture import Camera
from data.yieldizer import fetch_state
from logic.control import Controller
from logs.plant_log import PlantLog

REFRESH_TIME = int(os.getenv("REFRESH_TIME", 60 * 10))
PLANT_TYPE = os.getenv("PLANT_TYPE", "tomato")


class GreenhouseServer:
    camera: Camera
    controller: Controller
    plant_log: PlantLog
    _loop_task: Task[Never] | None = None

    def __init__(self):
        self.camera = Camera()

        from server.config import Config

        self.controller = Controller(Config.rules)
        self.plant_log = Config.log
        self._analysis_cache: AnalysisResult | None = None

    async def get_sensors(self):
        state = await fetch_state()
        return {
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

            result = await asyncio.to_thread(analyze, image, state)
            self.plant_log.analysis_snapshot(result)

            # LOGIC модуль: корректирует и отправляет параметры в теплицу
            _ = await self.controller.process(result, state)

            self._analysis_cache = result
        except Exception as e:
            print(f"[Server] Analysis error: {e}")
            traceback.print_exc()
            self._analysis_cache = None

    def get_logs(self):
        return self.plant_log.results_str()

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
        if self._loop_task is not None:
            _ = self._loop_task.cancel()


server = GreenhouseServer()


@asynccontextmanager
async def lifespan(_app: FastAPI):
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


@app.get("/api/logs")
async def logs_api():
    return server.get_logs()


if __name__ == "__main__":
    import uvicorn

    port = int(os.getenv("PORT", 8080))
    uvicorn.run(app, host="0.0.0.0", port=port, access_log=False)
