"""
    File: video_io.py
    Description: Threaded video decoding and ffmpeg/OpenCV video encoding.
"""

import os
import queue
import shutil
import subprocess
import threading

import cv2


class FrameReader:
    """Decodes video frames on a background thread into a bounded queue."""

    def __init__(self, cap, first_frame, max_queue):
        self._cap = cap
        self._first = first_frame
        self._queue = queue.Queue(maxsize=max_queue)
        self._stop = threading.Event()
        self._thread = threading.Thread(target=self._run, daemon=True)

    def _run(self):
        self._queue.put(self._first)
        while not self._stop.is_set():
            ret, frame = self._cap.read()
            if not ret:
                break
            self._queue.put(frame)
        self._queue.put(None)

    def start(self):
        self._thread.start()
        return self

    def batches(self, batch_size):
        """Yield lists of up to batch_size frames until the video ends."""
        done = False
        while not done:
            batch = []
            while len(batch) < batch_size:
                frame = self._queue.get()
                if frame is None:
                    done = True
                    break
                batch.append(frame)
            if batch:
                yield batch

    def close(self):
        """Stop the reader, unblocking it if it is waiting on a full queue."""
        self._stop.set()
        while self._thread.is_alive():
            try:
                self._queue.get_nowait()
            except queue.Empty:
                self._thread.join(timeout=0.1)


class FFmpegWriter:
    """Streams raw BGR frames into an ffmpeg process that encodes H.264."""

    def __init__(self, ffmpeg, output_path, width, height, fps, crf=18,
                 audio_source=None, log_dir=None):
        """
        Args:
            ffmpeg: Path to the ffmpeg executable
            output_path: Output video path
            width, height, fps: Frame properties
            crf: H.264 quality (lower = better)
            audio_source: Copy the audio track from this file, if it has one
            log_dir: Directory for ffmpeg's error log
        """
        cmd = [ffmpeg, '-y', '-loglevel', 'error',
               '-f', 'rawvideo', '-pix_fmt', 'bgr24', '-s', f'{width}x{height}', '-r', f'{fps}', '-i', '-']
        if audio_source:
            cmd += ['-i', audio_source, '-map', '0:v:0', '-map', '1:a?', '-c:a', 'copy']
        cmd += ['-vf', 'pad=ceil(iw/2)*2:ceil(ih/2)*2',  # yuv420p needs even dimensions
                '-c:v', 'libx264', '-crf', str(crf), '-pix_fmt', 'yuv420p',
                '-movflags', '+faststart', output_path]
        # Log to a file rather than a pipe so a chatty ffmpeg can never block
        self._log = open(os.path.join(log_dir, 'ffmpeg.log'), 'w+')
        self._proc = subprocess.Popen(cmd, stdin=subprocess.PIPE, stderr=self._log)

    def write(self, frame):
        self._proc.stdin.write(frame.tobytes())

    def close(self):
        """Finish encoding; returns True if ffmpeg succeeded."""
        try:
            self._proc.stdin.close()
        except BrokenPipeError:
            pass
        code = self._proc.wait()
        self._log.seek(0)
        err = self._log.read().strip()
        self._log.close()
        if code != 0:
            print(f"Error: ffmpeg failed: {err}")
        return code == 0


class OpenCVWriter:
    """Fallback writer (mp4v, no audio) for systems without ffmpeg."""

    def __init__(self, output_path, width, height, fps):
        self._writer = cv2.VideoWriter(output_path, cv2.VideoWriter_fourcc(*'mp4v'), fps, (width, height))
        if not self._writer.isOpened():
            raise IOError(f"Could not open video writer for '{output_path}'")

    def write(self, frame):
        self._writer.write(frame)

    def close(self):
        self._writer.release()
        return True


def open_writer(output_path, width, height, fps, crf=18, audio_source=None, log_dir=None):
    """
    Open the best available video writer.

    Returns:
        FFmpegWriter, or OpenCVWriter if ffmpeg is not installed
    """
    ffmpeg = shutil.which('ffmpeg')
    if ffmpeg is None:
        print(" -- Warning: ffmpeg not found; output will have no audio and use the mp4v codec")
        return OpenCVWriter(output_path, width, height, fps)
    return FFmpegWriter(ffmpeg, output_path, width, height, fps, crf, audio_source, log_dir)
