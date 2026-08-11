import asyncio
import logging
import numpy as np

from typing import Optional

logger = logging.getLogger(__name__)

class StreamDropError(Exception):
    """raised when ffmpeg process exits / its output stream closes."""

class StreamDecoder:
    def __init__(self, source: str, width: int = 1920, height: int = 1080) -> None:
        self.source = source
        self.width = width
        self.height = height
        self._process: Optional[asyncio.subprocess.Process] = None

    def _build_command(self) -> list[str]:
        is_rtsp = self.source.startswith("rtsp://")
        is_file = not is_rtsp
        cmd = ["ffmpeg", "-loglevel", "error"]

        if is_rtsp:
            cmd += ["-rtsp_transport", "tcp", "-timeout", "5000000"]
        elif is_file:
            cmd+= ["-stream_loop", "-1"]
        cmd+= [
            "-i",
            self.source,

            # no audio/subtitle processing
            "-an",
            "-sn",

            # output raw bgr frames
            "-f",
            "rawvideo",
            "-pix_fmt",
            "bgr24",

            # normalize all sources to conf res
            "-vf",
            f"scale={self.width}:{self.height}",

            "pipe:1"
        ]
        return cmd

    async def start(self) -> None:
        # start ffmpeg subprocess
        if self.is_alive():
            return

        cmd = self._build_command()
        self._process = await asyncio.create_subprocess_exec(
            *cmd,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.DEVNULL
        )

        logger.info(
            "stream_decoder_started source=%s pid=%s", self._redact(self.source), self._process.pid
        )

    async def read_frame(self) -> np.ndarray:
        # read one decoded bgr24 frame, return np array (height, width, 3)
        if self._process is None or self._process.stdout is None:
            raise RuntimeError("Call start() before read_frames()")

        frame_size = self.width*self.height*3
        data = bytearray()

        while len(data) < frame_size:
            chunk = await self._process.stdout.read(frame_size-len(data))
            if not chunk:
                return self._handle_stream_drop()
            data.extend(chunk)

        return np.frombuffer(data, dtype=np.uint8).reshape(self.height, self.width, 3)
    
    def _handle_stream_drop(self) -> np.ndarray:
        # handle ffmpeg process that stopped producing frames
        logger.warning("stream_decoder_eof_or_drop source=%s", self._redact(self.source))
        raise StreamDropError(f"FFmpeg stream dropped: {self._redact(self.source)}")

    def is_alive(self) -> bool:
        return (self._process is not None and self._process.returncode is None)

    async def stop(self) -> None:
        if self._process is None:
            return

        process = self._process
        if process.returncode is None:
            process.terminate()
            try:
                await asyncio.wait_for(process.wait(), timeout=5.0)
            except asyncio.TimeoutError:
                logger.warning("stream_decoder_force_kill source=%s", self._redact(self.source))
                process.kill()
                await process.wait()

        self._process = None
        logger.info("stream_decoder_stopped source=%s", self._redact(self.source))

    @staticmethod
    def _redact(source:str) -> str:
        # redact creds from rtsp urls
        if "@" not in source:
            return source
        try:
            scheme, rest = source.split("://", 1)
            host_part = rest.split("@", 1)[1]
            return f"{scheme}://***@{host_part}"
        except ValueError:
            return "***"