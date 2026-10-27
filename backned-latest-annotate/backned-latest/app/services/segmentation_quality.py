"""Segmentation Quality Validation, Mask-to-Polygon Contour Extraction, and Coordinate Transformation Service."""

from __future__ import annotations

from typing import Any

import cv2
import numpy as np

from app.logging import get_logger

logger = get_logger(__name__)


def validate_mask_and_calculate_metrics(
    mask_array: np.ndarray,
    image_w: int,
    image_h: int,
    bbox_percent: Any | None = None,
) -> dict[str, Any]:
    """Validate mask array dimensions, calculate mask area metrics, and flag suspicious masks."""
    if mask_array is None or not isinstance(mask_array, np.ndarray):
        return {
            "is_valid": False,
            "mask_area": 0,
            "bbox_area": 0,
            "mask_to_bbox_ratio": 0.0,
            "flags": ["INVALID_MASK"],
            "reason": "INVALID_MASK: mask array is null or invalid type",
        }

    mask_h, mask_w = mask_array.shape[:2]
    flags: list[str] = []

    if mask_w != image_w or mask_h != image_h:
        flags.append("MASK_OUT_OF_BOUNDS")

    foreground_pixels = int(np.count_nonzero(mask_array))
    total_image_pixels = image_w * image_h

    if foreground_pixels == 0:
        flags.append("EMPTY_MASK")

    bbox_pixel_area = total_image_pixels
    if bbox_percent is not None:
        bw = (float(getattr(bbox_percent, "w", 100.0) or 100.0) / 100.0) * image_w
        bh = (float(getattr(bbox_percent, "h", 100.0) or 100.0) / 100.0) * image_h
        bbox_pixel_area = max(1.0, bw * bh)

    mask_to_bbox_ratio = foreground_pixels / bbox_pixel_area if bbox_pixel_area > 0 else 0.0

    # Mask area > bbox_area * 1.15 indicates mask spill / bbox mismatch
    if foreground_pixels > (bbox_pixel_area * 1.15):
        flags.append("MASK_BBOX_MISMATCH")

    # Suspicious area: mask covering > 95% of entire image or < 5 pixels
    if foreground_pixels > (total_image_pixels * 0.95) and (bbox_pixel_area < total_image_pixels * 0.50):
        flags.append("SUSPICIOUS_MASK_AREA")
    elif 0 < foreground_pixels < 5:
        flags.append("SUSPICIOUS_MASK_AREA")

    is_valid = not bool(flags)

    return {
        "is_valid": is_valid,
        "mask_width": mask_w,
        "mask_height": mask_h,
        "image_width": image_w,
        "image_height": image_h,
        "mask_area": foreground_pixels,
        "bbox_area": int(bbox_pixel_area),
        "mask_to_bbox_ratio": round(mask_to_bbox_ratio, 4),
        "flags": flags,
        "reason": ", ".join(flags) if flags else None,
    }


def transform_crop_mask_to_full_image(
    crop_mask: np.ndarray,
    crop_box_pixels: tuple[int, int, int, int],  # x1, y1, x2, y2
    orig_w: int,
    orig_h: int,
) -> np.ndarray:
    """Transform crop mask onto original full-size image canvas and log parameters."""
    x1, y1, x2, y2 = crop_box_pixels
    crop_w = max(1, x2 - x1)
    crop_h = max(1, y2 - y1)

    # Resize crop_mask if needed to match target ROI dimensions
    if crop_mask.shape[:2] != (crop_h, crop_w):
        resized_crop_mask = cv2.resize(
            crop_mask.astype(np.uint8),
            (crop_w, crop_h),
            interpolation=cv2.INTER_NEAREST,
        )
    else:
        resized_crop_mask = crop_mask.astype(np.uint8)

    full_mask = np.zeros((orig_h, orig_w), dtype=np.uint8)
    
    # Clip coordinates to original image bounds
    target_x1 = max(0, min(orig_w, x1))
    target_y1 = max(0, min(orig_h, y1))
    target_x2 = max(0, min(orig_w, x2))
    target_y2 = max(0, min(orig_h, y2))

    src_w = target_x2 - target_x1
    src_h = target_y2 - target_y1

    if src_w > 0 and src_h > 0:
        full_mask[target_y1:target_y2, target_x1:target_x2] = resized_crop_mask[0:src_h, 0:src_w]

    logger.info(
        "mask_coordinate_transformation_logging",
        source_width=orig_w,
        source_height=orig_h,
        model_input_width=crop_mask.shape[1],
        model_input_height=crop_mask.shape[0],
        crop_x=x1,
        crop_y=y1,
        scale=1.0,
        padding=0,
        mask_width=orig_w,
        mask_height=orig_h,
    )

    return full_mask


def extract_polygon_from_mask(
    mask_array: np.ndarray,
    image_w: int,
    image_h: int,
    epsilon_ratio: float = 0.003,
) -> list[list[float]] | None:
    """Extract real polygon points from a binary mask array using OpenCV contours.

    Never creates a fake 4-point bounding box rectangle.
    Returns normalized points in [0, 100] percent space, closed (points[0] == points[-1]).
    """
    if mask_array is None or image_w <= 0 or image_h <= 0:
        return None

    binary_mask = (mask_array > 0).astype(np.uint8) * 255
    contours, _ = cv2.findContours(binary_mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)

    if not contours:
        return None

    contour = max(contours, key=cv2.contourArea)
    perimeter = cv2.arcLength(contour, True)

    approx = cv2.approxPolyDP(contour, epsilon_ratio * perimeter, True)

    points: list[list[float]] = []
    for pt in approx:
        px = max(0.0, min(100.0, float(pt[0][0] / image_w * 100.0)))
        py = max(0.0, min(100.0, float(pt[0][1] / image_h * 100.0)))
        points.append([round(px, 3), round(py, 3)])

    if len(points) < 3:
        return None

    # Ensure logically closed
    if points[0] != points[-1]:
        points.append(list(points[0]))

    return points


def evaluate_segmentation_quality_score(
    detection_confidence: float,
    mask_area: int,
    bbox_area: int,
) -> float:
    """Calculate separate segmentation quality score without combining/overwriting detection confidence."""
    if bbox_area <= 0 or mask_area <= 0:
        return 0.0

    ratio = mask_area / bbox_area
    if ratio > 1.15:
        # Penalty for significant spill
        quality = max(0.0, 1.0 - (ratio - 1.0))
    elif ratio < 0.10:
        # Penalty for tiny coverage inside large box
        quality = max(0.0, ratio / 0.10)
    else:
        quality = 1.0

    return round(float(quality), 4)
