"""
    File: composite_image.py
    Author: renyunfan
    Email: renyf@connect.hku.hk
    Description: A python script to create a composite image from a video.
    All Rights Reserved 2023
"""

import cv2
import numpy as np
from enum import Enum
import argparse
from pathlib import Path
from tqdm import tqdm


class CompositeMode(Enum):
    """Enumeration of composite image modes."""
    MAX_VARIATION = 0
    MIN_VALUE = 1
    MAX_VALUE = 2


class CompositeImage:
    """Class for creating composite images from video files."""

    def __init__(self, mode, video_path, start_t=0, end_t=999, skip_frame=1, alpha=0.5, disable_pbar=False):
        """
        Initialize CompositeImage.
        
        Args:
            mode: CompositeMode enum value
            video_path: Path to the input video file
            start_t: Start time in seconds (default: 0)
            end_t: End time in seconds (default: 999)
            skip_frame: Number of frames to skip (default: 1)
            alpha: Alpha blending factor for intermediate frames (default: 0.5)
            disable_pbar: Disable progress bar (default: False)
        """
        self.video_path = video_path
        self.skip_frame = skip_frame
        self.start_t = start_t
        self.end_t = end_t
        self.mode = mode
        self.disable_pbar = disable_pbar
        # clamp alpha
        self.alpha = max(0.0, min(1.0, alpha))

    def max_variation_update(self, image):
        """Update composite using maximum variation mode."""
        delta_img = image - self.ave_img
        image_norm = np.linalg.norm(image, axis=2)
        delta_norm = image_norm - self.ave_img_norm
        abs_delta_norm = np.abs(delta_norm)
        delta_mask = abs_delta_norm > self.abs_diff_norm
        diff_mask = abs_delta_norm <= self.abs_diff_norm
        delta_mask = np.stack((delta_mask.T, delta_mask.T, delta_mask.T)).T.astype(np.float32)
        diff_mask = np.stack((diff_mask.T, diff_mask.T, diff_mask.T)).T.astype(np.float32)
        self.diff_img = self.diff_img * diff_mask + delta_img * delta_mask
        self.diff_norm = np.linalg.norm(self.diff_img, axis=2)
        self.abs_diff_norm = np.abs(self.diff_norm)

    def min_value_update(self, image):
        """Update composite using minimum value mode."""
        image_norm = np.linalg.norm(image, axis=2)
        cur_min_image = self.diff_img + self.ave_img
        cur_min_image_norm = np.linalg.norm(cur_min_image, axis=2)
        delta_mask = cur_min_image_norm > image_norm
        min_mask = cur_min_image_norm <= image_norm
        delta_mask = np.stack((delta_mask.T, delta_mask.T, delta_mask.T)).T.astype(np.float32)
        min_mask = np.stack((min_mask.T, min_mask.T, min_mask.T)).T.astype(np.float32)
        new_min_img = image * delta_mask + min_mask * cur_min_image
        self.diff_img = new_min_img - self.ave_img

    def max_value_update(self, image):
        """Update composite using maximum value mode."""
        image_norm = np.linalg.norm(image, axis=2)
        cur_min_image = self.diff_img + self.ave_img
        cur_min_image_norm = np.linalg.norm(cur_min_image, axis=2)
        delta_mask = cur_min_image_norm < image_norm
        min_mask = cur_min_image_norm >= image_norm
        delta_mask = np.stack((delta_mask, delta_mask, delta_mask), axis=2).astype(np.float32)
        min_mask = np.stack((min_mask, min_mask, min_mask), axis=2).astype(np.float32)
        new_min_img = image * delta_mask + min_mask * cur_min_image
        self.diff_img = new_min_img - self.ave_img

    def extract_frames(self):
        """Extract frames from the video file."""
        if self.video_path is None:
            return None
        
        video = cv2.VideoCapture(self.video_path)
        # Get video frame rate
        fps = video.get(cv2.CAP_PROP_FPS)
        # Calculate start and end frame indices
        start_frame = int(self.start_t * fps)
        end_frame = int(self.end_t * fps)

        # Set the current frame to the start frame
        video.set(cv2.CAP_PROP_POS_FRAMES, start_frame)

        frame_count = 0  # Track extracted frames
        imgs = []

        # Loop through video frames
        while video.isOpened() and frame_count <= (end_frame - start_frame):
            ret, frame = video.read()
            if ret:
                if (frame_count % self.skip_frame != 0):
                    frame_count += 1
                    continue
                else: frame_count += 1
                imgs.append(frame)

                if frame_count > (end_frame - start_frame):
                    break
            else:
                break

        # Release the video object
        video.release()
        return imgs

    def merge_images(self):
        """Merge extracted frames into a composite image."""
        image_files = self.extract_frames()
        if image_files is None or len(image_files) < 1:
            print("Error: no image extracted, input video path at: ", self.video_path)
            exit(1)
        
        first_image = image_files[0]
        height, width, _ = first_image.shape

        # Calculate the average image
        sum_image = np.zeros((height, width, 3), dtype=np.float32)
        img_num = len(image_files)

        for image_file in image_files:
            image = image_file.astype(np.float32)
            sum_image += image

        self.ave_img = sum_image / img_num
        self.ave_img_norm = np.linalg.norm(self.ave_img, axis=2)
        self.diff_norm = np.zeros((height, width), dtype=np.float32)
        self.abs_diff_norm = np.zeros((height, width), dtype=np.float32)
        self.diff_img = np.zeros((height, width, 3), dtype=np.float32)

        for idx, image_file in tqdm(enumerate(image_files), total=img_num, disable=self.disable_pbar, desc="Processing"):
            image = image_file.astype(np.float32)
            # Alpha blend (all modes) for intermediate frames only
            if idx != 0 and idx != (img_num - 1) and self.alpha < 1.0:
                image = self.alpha * image + (1.0 - self.alpha) * self.ave_img
            if self.mode == CompositeMode.MAX_VARIATION:
                self.max_variation_update(image)
            elif self.mode == CompositeMode.MIN_VALUE:
                self.min_value_update(image)
            elif self.mode == CompositeMode.MAX_VALUE:
                self.max_value_update(image)

        merged_image = self.ave_img + self.diff_img
        merged_image = merged_image.astype(np.uint8)
        return merged_image


def main():
    """Main function for command-line interface."""
    parser = argparse.ArgumentParser(
        prog='composite-image',
        description='Convert video to composite image.',
        epilog='-'
    )
    parser.add_argument('--video_path', type=str, required=True, 
                        help='path of input video file.')
    parser.add_argument('--mode', default='VAR', choices=['VAR', 'MAX', 'MIN'], 
                        help='mode of composite image.')
    parser.add_argument('--start_t', default=0, type=float, 
                        help='start time of composite image.')
    parser.add_argument('--end_t', default=999999, type=float, 
                        help='end time of composite image.')
    parser.add_argument('--skip_frame', default=1, type=int, 
                        help='skip frame when extract frames.')
    parser.add_argument('--alpha', default=0.5, type=float, 
                        help='alpha for intermediate frames in all modes (0..1)')
    parser.add_argument('--disable_pbar', action='store_true',
                        help='disable progress bar when merging images')
    parser.add_argument('--output', type=str, default=None,
                        help='output file path (default: same directory as video with .jpg extension)')

    args = parser.parse_args()

    # Read command-line parameters
    path = args.video_path
    mode_str = args.mode
    start_t = args.start_t
    end_t = args.end_t
    skip_frame = args.skip_frame
    alpha = args.alpha

    print(" -- Load Param: video path", path)
    print(" -- Load Param: mode", mode_str)
    print(" -- Load Param: start_t", start_t)
    print(" -- Load Param: end_t", end_t)
    print(" -- Load Param: skip_frame", skip_frame)
    print(" -- Load Param: alpha", alpha)

    # Convert mode string to enum
    if mode_str == 'MAX':
        mode = CompositeMode.MAX_VALUE
    elif mode_str == 'MIN':
        mode = CompositeMode.MIN_VALUE
    elif mode_str == 'VAR':
        mode = CompositeMode.MAX_VARIATION
    else:
        mode = CompositeMode.MAX_VARIATION

    # Create composite image
    merger = CompositeImage(mode, path, start_t, end_t, skip_frame, alpha, args.disable_pbar)
    merged_image = merger.merge_images()

    # Determine output path
    if args.output:
        output_path = args.output
    else:
        video_path = Path(path)
        output_path = video_path.parent / f'{video_path.stem}.jpg'

    # Save the composite image
    cv2.imwrite(str(output_path), merged_image)
    print(f" -- Composite image saved to: {output_path}")


if __name__ == "__main__":
    main()
