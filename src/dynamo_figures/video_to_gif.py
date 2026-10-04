#!/usr/bin/env python3
"""
    File: video_to_gif.py
    Description: A python script to convert a video to an animated GIF.
    Supports frame rate control, time range selection, and resizing options.
"""

import argparse
import cv2
import os
import sys
from pathlib import Path
from tqdm import tqdm

try:
    from PIL import Image
    HAS_PIL = True
except ImportError:
    HAS_PIL = False

try:
    import imageio
    HAS_IMAGEIO = True
except ImportError:
    HAS_IMAGEIO = False


class VideoToGif:
    """Class for converting video files to animated GIFs."""

    def __init__(self, video_path, fps=10, start_t=0, end_t=None, scale=1.0,
                 width=None, crop_left=0, crop_right=0, crop_top=0, crop_bottom=0, speed=1.0,
                 loop=0, optimize=True, reverse=False, disable_pbar=False):
        """
        Initialize VideoToGif converter.
        
        Args:
            video_path: Path to the input video file
            fps: Output GIF frame rate (default: 10)
            start_t: Start time in seconds (default: 0)
            end_t: End time in seconds (default: None, meaning end of video)
            scale: Scale factor for output size (default: 1.0)
            width: Target width in pixels, maintains aspect ratio (default: None)
            crop_left: Pixels to crop from the left edge after scaling (default: 0)
            crop_right: Pixels to crop from the right edge after scaling (default: 0)
            crop_top: Pixels to crop from the top edge after scaling (default: 0)
            crop_bottom: Pixels to crop from the bottom edge after scaling (default: 0)
            speed: Playback speed multiplier, e.g. 2.0 for 2x faster (default: 1.0)
            loop: Number of loops, 0 for infinite (default: 0)
            optimize: Whether to optimize the GIF for smaller file size (default: True)
            reverse: Add reverse frames for boomerang effect (default: False)
            disable_pbar: Disable progress bar (default: False)
        """
        self.video_path = video_path
        self.fps = max(1, fps)
        self.start_t = max(0, start_t)
        self.end_t = end_t
        self.scale = max(0.01, min(2.0, scale))
        self.width = width
        self.crop_left = max(0, crop_left)
        self.crop_right = max(0, crop_right)
        self.crop_top = max(0, crop_top)
        self.crop_bottom = max(0, crop_bottom)
        self.speed = max(0.01, speed)
        self.loop = loop
        self.optimize = optimize
        self.reverse = reverse
        self.disable_pbar = disable_pbar
        
        # Video properties (populated during extraction)
        self.video_fps = None
        self.video_frame_count = None
        self.video_width = None
        self.video_height = None
        self.video_duration = None

    def _load_video_info(self, cap):
        """Load video properties from capture object."""
        self.video_fps = cap.get(cv2.CAP_PROP_FPS)
        self.video_frame_count = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
        self.video_width = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
        self.video_height = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
        self.video_duration = self.video_frame_count / self.video_fps if self.video_fps > 0 else 0

    def get_video_info(self):
        """
        Get video information without extracting frames.
        
        Returns:
            dict: Video information or None if video cannot be opened
        """
        if not os.path.exists(self.video_path):
            print(f"Error: Video file '{self.video_path}' not found.")
            return None

        cap = cv2.VideoCapture(self.video_path)
        if not cap.isOpened():
            print(f"Error: Could not open video file '{self.video_path}'.")
            return None

        self._load_video_info(cap)
        cap.release()

        return {
            'path': self.video_path,
            'width': self.video_width,
            'height': self.video_height,
            'frame_count': self.video_frame_count,
            'fps': self.video_fps,
            'duration': self.video_duration
        }

    def _calculate_output_size(self):
        """Calculate output dimensions based on scale or width parameters."""
        if self.width is not None:
            # Calculate height maintaining aspect ratio
            aspect_ratio = self.video_height / self.video_width
            out_width = self.width
            out_height = int(self.width * aspect_ratio)
        else:
            out_width = int(self.video_width * self.scale)
            out_height = int(self.video_height * self.scale)
        
        # Ensure dimensions are even (required by some codecs)
        out_width = out_width if out_width % 2 == 0 else out_width + 1
        out_height = out_height if out_height % 2 == 0 else out_height + 1
        
        return out_width, out_height

    def _crop_frame(self, frame, crop_left, crop_right, crop_top, crop_bottom):
        """Crop a frame by removing pixels from edges."""
        h, w = frame.shape[:2]
        x_start = crop_left
        x_end = w - crop_right
        y_start = crop_top
        y_end = h - crop_bottom
        
        # Ensure valid crop region
        x_start = max(0, min(x_start, w - 1))
        x_end = max(x_start + 1, min(x_end, w))
        y_start = max(0, min(y_start, h - 1))
        y_end = max(y_start + 1, min(y_end, h))
        
        return frame[y_start:y_end, x_start:x_end]

    def extract_frames(self):
        """
        Extract frames from the video file.
        
        Returns:
            list: List of frames as numpy arrays (RGB format), or None on error
        """
        if not os.path.exists(self.video_path):
            print(f"Error: Video file '{self.video_path}' not found.")
            return None

        cap = cv2.VideoCapture(self.video_path)
        if not cap.isOpened():
            print(f"Error: Could not open video file '{self.video_path}'.")
            return None

        self._load_video_info(cap)
        
        print(f" -- Video info: {self.video_frame_count} frames, {self.video_fps:.2f} FPS, {self.video_duration:.2f}s duration")

        # Calculate frame indices
        start_frame = int(self.start_t * self.video_fps)
        
        if self.end_t is not None:
            end_frame = int(self.end_t * self.video_fps)
        else:
            end_frame = self.video_frame_count
        
        # Clamp to valid range
        start_frame = max(0, min(start_frame, self.video_frame_count - 1))
        end_frame = max(start_frame + 1, min(end_frame, self.video_frame_count))

        # Calculate frame skip to achieve target fps
        frame_skip = max(1, int(self.video_fps / self.fps))
        
        # Calculate output size
        out_width, out_height = self._calculate_output_size()
        
        # Check if cropping is requested
        has_crop = (self.crop_left > 0 or self.crop_right > 0 or 
                    self.crop_top > 0 or self.crop_bottom > 0)

        print(f" -- Extracting frames {start_frame} to {end_frame} (every {frame_skip} frames)")
        print(f" -- Resize to: {out_width}x{out_height}")
        if has_crop:
            final_w = out_width - self.crop_left - self.crop_right
            final_h = out_height - self.crop_top - self.crop_bottom
            print(f" -- Crop: left={self.crop_left}, right={self.crop_right}, top={self.crop_top}, bottom={self.crop_bottom}")
            print(f" -- Final size: {final_w}x{final_h}")

        # Set video position to start frame
        cap.set(cv2.CAP_PROP_POS_FRAMES, start_frame)

        frames = []
        total_frames = (end_frame - start_frame) // frame_skip
        
        pbar = tqdm(total=total_frames, disable=self.disable_pbar, desc="Extracting frames")
        
        frame_idx = start_frame
        while frame_idx < end_frame:
            ret, frame = cap.read()
            if not ret:
                break
            
            if (frame_idx - start_frame) % frame_skip == 0:
                # Resize if needed
                if out_width != self.video_width or out_height != self.video_height:
                    frame = cv2.resize(frame, (out_width, out_height), interpolation=cv2.INTER_AREA)
                
                # Convert BGR to RGB for PIL/imageio
                frame_rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)

                # Apply crop if requested (after scaling)
                if has_crop:
                    frame_rgb = self._crop_frame(frame_rgb, self.crop_left, self.crop_right, 
                                                  self.crop_top, self.crop_bottom)

                frames.append(frame_rgb)
                pbar.update(1)
            
            frame_idx += 1

        pbar.close()
        cap.release()

        if len(frames) == 0:
            print("Error: No frames extracted from video.")
            return None

        print(f" -- Extracted {len(frames)} frames")
        return frames

    def _save_gif_pil(self, frames, output_path):
        """Save frames as GIF using PIL."""
        if not HAS_PIL:
            return False
        
        # Convert numpy arrays to PIL Images
        pil_frames = [Image.fromarray(frame) for frame in frames]
        
        # Calculate frame duration in milliseconds
        # Frame skip determines spacing in original video
        frame_skip = max(1, int(self.video_fps / self.fps)) if self.video_fps > 0 else 1
        # Duration accounts for frame skip and applies speed modifier
        duration = int(1000 * frame_skip / self.video_fps / self.speed)
        
        # Save GIF
        pil_frames[0].save(
            output_path,
            save_all=True,
            append_images=pil_frames[1:],
            duration=duration,
            loop=self.loop,
            optimize=self.optimize
        )
        return True

    def _save_gif_imageio(self, frames, output_path):
        """Save frames as GIF using imageio."""
        if not HAS_IMAGEIO:
            return False
        
        # Calculate frame duration
        # Frame skip determines spacing in original video
        frame_skip = max(1, int(self.video_fps / self.fps)) if self.video_fps > 0 else 1
        # Duration accounts for frame skip and applies speed modifier
        duration = frame_skip / self.video_fps / self.speed if self.video_fps > 0 else 1.0
        
        # Use v3 API if available, fallback to v2
        try:
            imageio.v3.imwrite(output_path, frames, duration=duration, loop=self.loop)
        except AttributeError:
            imageio.mimsave(output_path, frames, duration=duration, loop=self.loop)
        
        return True

    def convert(self, output_path):
        """
        Convert video to GIF and save to the specified path.
        
        Args:
            output_path: Path where the GIF will be saved
            
        Returns:
            bool: True if successful, False otherwise
        """
        # Check for required dependencies
        if not HAS_PIL and not HAS_IMAGEIO:
            print("Error: Either PIL (Pillow) or imageio is required.")
            print("Install with: pip install Pillow  OR  pip install imageio")
            return False

        # Extract frames
        frames = self.extract_frames()
        if frames is None:
            return False

        # Add reverse frames for boomerang effect
        if self.reverse and len(frames) > 1:
            frames = frames + frames[-2:0:-1]
            print(f" -- Added reverse frames (boomerang), total: {len(frames)} frames")

        # Create output directory if it doesn't exist
        output_dir = Path(output_path).parent
        output_dir.mkdir(parents=True, exist_ok=True)

        print(" -- Saving GIF...")
        
        # Try PIL first, then imageio
        success = False
        if HAS_PIL:
            try:
                success = self._save_gif_pil(frames, output_path)
            except Exception as e:
                print(f" -- PIL save failed: {e}")
                success = False
        
        if not success and HAS_IMAGEIO:
            try:
                success = self._save_gif_imageio(frames, output_path)
            except Exception as e:
                print(f" -- imageio save failed: {e}")
                success = False

        if success:
            # Get file size
            file_size = os.path.getsize(output_path)
            size_str = f"{file_size / 1024:.1f} KB" if file_size < 1024 * 1024 else f"{file_size / (1024 * 1024):.2f} MB"
            print(f" -- GIF saved to: {output_path}")
            print(f" -- File size: {size_str}")
            return True
        else:
            print("Error: Failed to save GIF.")
            return False


def main():
    """Main function for command-line interface."""
    parser = argparse.ArgumentParser(
        prog='dynamo-video-to-gif',
        description='Convert a video file to an animated GIF.',
        epilog='-'
    )
    parser.add_argument('--video_path', type=str, required=True,
                        help='path of input video file.')
    parser.add_argument('--output', type=str, default=None,
                        help='output file path (default: same directory as video with .gif extension)')
    parser.add_argument('--fps', type=int, default=10,
                        help='output GIF frame rate (default: 10)')
    parser.add_argument('--start_t', type=float, default=0,
                        help='start time in seconds (default: 0)')
    parser.add_argument('--end_t', type=float, default=None,
                        help='end time in seconds (default: end of video)')
    parser.add_argument('--scale', type=float, default=1.0,
                        help='scale factor for output size (default: 1.0)')
    parser.add_argument('--width', type=int, default=None,
                        help='target width in pixels, maintains aspect ratio (overrides --scale)')
    parser.add_argument('--crop_left', type=int, default=0,
                        help='pixels to crop from the left edge after scaling (default: 0)')
    parser.add_argument('--crop_right', type=int, default=0,
                        help='pixels to crop from the right edge after scaling (default: 0)')
    parser.add_argument('--crop_top', type=int, default=0,
                        help='pixels to crop from the top edge after scaling (default: 0)')
    parser.add_argument('--crop_bottom', type=int, default=0,
                        help='pixels to crop from the bottom edge after scaling (default: 0)')
    parser.add_argument('--speed', type=float, default=1.0,
                        help='playback speed multiplier, e.g. 2.0 for 2x faster (default: 1.0)')
    parser.add_argument('--loop', type=int, default=0,
                        help='number of loops, 0 for infinite (default: 0)')
    parser.add_argument('--no_optimize', action='store_true',
                        help='disable GIF optimization')
    parser.add_argument('--reverse', action='store_true',
                        help='add reverse frames for boomerang effect')
    parser.add_argument('--disable_pbar', action='store_true',
                        help='disable progress bar')
    parser.add_argument('--info_only', action='store_true',
                        help='only display video information without converting')

    args = parser.parse_args()

    # Read command-line parameters
    path = args.video_path

    print(" -- Load Param: video path", path)
    print(" -- Load Param: fps", args.fps)
    print(" -- Load Param: start_t", args.start_t)
    print(" -- Load Param: end_t", args.end_t)
    print(" -- Load Param: scale", args.scale)
    print(" -- Load Param: width", args.width)
    print(" -- Load Param: crop_left", args.crop_left)
    print(" -- Load Param: crop_right", args.crop_right)
    print(" -- Load Param: crop_top", args.crop_top)
    print(" -- Load Param: crop_bottom", args.crop_bottom)
    print(" -- Load Param: speed", args.speed)
    print(" -- Load Param: loop", args.loop)
    print(" -- Load Param: optimize", not args.no_optimize)
    print(" -- Load Param: reverse", args.reverse)

    # Create converter
    converter = VideoToGif(
        video_path=path,
        fps=args.fps,
        start_t=args.start_t,
        end_t=args.end_t,
        scale=args.scale,
        width=args.width,
        crop_left=args.crop_left,
        crop_right=args.crop_right,
        crop_top=args.crop_top,
        crop_bottom=args.crop_bottom,
        speed=args.speed,
        loop=args.loop,
        optimize=not args.no_optimize,
        reverse=args.reverse,
        disable_pbar=args.disable_pbar
    )

    # If info-only mode, just display video info
    if args.info_only:
        info = converter.get_video_info()
        if info is None:
            sys.exit(1)

        print(f" -- Video: {info['path']}")
        print(f" -- Dimensions: {info['width']}x{info['height']}")
        print(f" -- Frames: {info['frame_count']}")
        print(f" -- FPS: {info['fps']:.2f}")
        print(f" -- Duration: {info['duration']:.2f} seconds")
        return

    # Determine output path
    if args.output:
        output_path = args.output
    else:
        video_path = Path(path)
        output_path = str(video_path.parent / f'{video_path.stem}.gif')

    print(" -- Load Param: output", output_path)

    # Convert video to GIF
    success = converter.convert(output_path)

    if not success:
        sys.exit(1)


if __name__ == "__main__":
    main()
