import React, { useState, useEffect } from 'react';
import {
  ZoomIn,
  ZoomOut,
  ImageOff,
  Palette,
  Loader2,
  RefreshCw,
} from 'lucide-react';
import { api } from '../../services/api';

export interface DetectionItem {
  id: string;
  name: string;
  label: string;
  confidence: number | null;
  color: string;
  box: { x: number; y: number; width: number; height: number };
}

interface AICanvasViewProps {
  mode?: 'Detection' | 'PII';
  imageIndex?: number;
  onToast: (msg: string) => void;
  selectedId: string | null;
  onSelect: (id: string) => void;
  detections?: DetectionItem[];
  imageUrl?: string;
  fallbackUrl?: string;
  assetId?: string;
  isLoading?: boolean;
  onRetry?: () => void;
}

export const AICanvasView: React.FC<AICanvasViewProps> = ({
  mode = 'Detection',
  onToast,
  selectedId,
  onSelect,
  detections: customDetections,
  imageUrl,
  fallbackUrl,
  assetId,
  isLoading = false,
  onRetry,
}) => {
  const [showLabels] = useState<boolean>(true);
  const [zoom, setZoom] = useState<number>(100);
  const [imageError, setImageError] = useState<boolean>(false);
  const [currentSrc, setCurrentSrc] = useState<string | undefined>(imageUrl);
  const [fallbackAttempted, setFallbackAttempted] = useState<boolean>(false);
  const [isImageLoading, setIsImageLoading] = useState<boolean>(true);
  const [boxStyle, setBoxStyle] = useState<'dashed' | 'solid' | 'corner'>('dashed');
  const [useClassColors, setUseClassColors] = useState<boolean>(true);

  const isPII = mode === 'PII';
  const detections = customDetections !== undefined ? customDetections : [];

  // Keep one stable, high-contrast color per class so repeated detections of
  // the same object are easy to follow across the image and prediction list.
  const classColors = ['#00D084', '#00A8FF', '#FFB000', '#FF4D6D', '#A855F7', '#14B8A6', '#F97316', '#EAB308'];
  const classColorMap = new Map<string, string>();
  detections.forEach((item) => {
    const key = (item.label || item.name || 'object').trim().toLowerCase();
    if (!classColorMap.has(key)) classColorMap.set(key, classColors[classColorMap.size % classColors.length]);
  });

  const getDetectionColor = (item: DetectionItem) => {
    if (!useClassColors) return item.color || '#00A8FF';
    return classColorMap.get((item.label || item.name || 'object').trim().toLowerCase()) || item.color || '#00A8FF';
  };

  // Sync currentSrc whenever imageUrl changes
  useEffect(() => {
    setCurrentSrc(imageUrl);
    setFallbackAttempted(false);
    setImageError(false);
    setIsImageLoading(true);
  }, [imageUrl]);

  const handleImageError = () => {
    // If the primary URL (e.g. cached blob URL) failed and we have a direct fallback URL, try it!
    if (!fallbackAttempted && fallbackUrl && fallbackUrl !== currentSrc) {
      console.warn('[AICanvasView] Primary image load failed, attempting direct endpoint fallback:', fallbackUrl);
      setFallbackAttempted(true);
      setCurrentSrc(fallbackUrl);
      if (assetId) {
        api.invalidateAssetImage(assetId);
      }
      return;
    }
    setImageError(true);
    setIsImageLoading(false);
    if (assetId) {
      api.invalidateAssetImage(assetId);
    }
  };

  const handleManualRetry = () => {
    setImageError(false);
    setFallbackAttempted(false);
    setIsImageLoading(true);
    if (assetId) {
      api.invalidateAssetImage(assetId);
    }
    if (onRetry) {
      onRetry();
    } else if (fallbackUrl) {
      setCurrentSrc(`${fallbackUrl}?t=${Date.now()}`);
    } else if (imageUrl) {
      setCurrentSrc(`${imageUrl}?t=${Date.now()}`);
    }
  };

  return (
    <div
      id="ai-canvas-card"
      className="rounded-xl border border-slate-200 bg-white p-4 shadow-2xs space-y-3.5"
    >
      {/* Top Toolbar inside canvas container */}
      <div className="flex flex-wrap items-center justify-between gap-3 text-xs">
        {/* Left: Task Type */}
        <div id="canvas-task-type" className="flex items-center gap-1.5">
          <span className="text-xs font-normal text-slate-500">Task Type:</span>
          <span className="text-xs font-bold text-slate-900">
            {isPII ? 'PII Masking' : 'Object Detection & Labeling'}
          </span>
        </div>

        {/* Right: Merged Zoom Controls: [ - ] 100% [ + ] */}
        <div className="flex items-center gap-2">
          <label className="inline-flex items-center gap-1.5 rounded-lg border border-slate-200 bg-white px-2 py-1 text-[11px] font-semibold text-slate-600">
            <span>Boxes</span>
            <select
              aria-label="Bounding box preview style"
              value={boxStyle}
              onChange={(event) => setBoxStyle(event.target.value as typeof boxStyle)}
              className="bg-transparent text-[11px] font-bold text-slate-800 outline-none cursor-pointer"
            >
              <option value="dashed">Dashed</option>
              <option value="solid">Solid</option>
              <option value="corner">Corner</option>
            </select>
          </label>
          <button
            type="button"
            onClick={() => setUseClassColors((enabled) => !enabled)}
            className={`inline-flex h-7 items-center gap-1 rounded-lg border px-2 text-[11px] font-semibold transition ${useClassColors ? 'border-sky-200 bg-sky-50 text-sky-700' : 'border-slate-200 bg-white text-slate-500'}`}
            title="Toggle stable colors by object class"
            aria-pressed={useClassColors}
          >
            <Palette className="h-3.5 w-3.5" />
            Class colors
          </button>
          <div
            id="canvas-merged-zoom-group"
            className="inline-flex items-center rounded-lg border border-slate-200 bg-white shadow-2xs divide-x divide-slate-100 overflow-hidden"
          >
            {/* Zoom Out Button */}
            <button
              id="btn-canvas-zoom-out"
              onClick={() => {
                setZoom((z) => Math.max(50, z - 15));
                onToast('Zoomed out');
              }}
              className="flex h-7 w-7 items-center justify-center text-slate-500 hover:text-slate-900 hover:bg-slate-50 transition cursor-pointer"
              title="Zoom Out"
              aria-label="Zoom Out"
            >
              <ZoomOut className="h-3.5 w-3.5" />
            </button>

            {/* 100% Zoom Reset / Adjust */}
            <button
              id="btn-canvas-zoom-percentage"
              onClick={() => {
                const next = zoom === 100 ? 125 : zoom === 125 ? 150 : 100;
                setZoom(next);
                onToast(`Zoom adjusted to ${next}%`);
              }}
              className="flex h-7 items-center justify-center px-2.5 font-semibold text-slate-700 hover:bg-slate-50 transition cursor-pointer text-xs tabular-nums"
              title="Adjust Zoom"
            >
              <span>{zoom}%</span>
            </button>

            {/* Zoom In Button */}
            <button
              id="btn-canvas-zoom-in"
              onClick={() => {
                setZoom((z) => Math.min(200, z + 15));
                onToast('Zoomed in');
              }}
              className="flex h-7 w-7 items-center justify-center text-slate-500 hover:text-slate-900 hover:bg-slate-50 transition cursor-pointer"
              title="Zoom In"
              aria-label="Zoom In"
            >
              <ZoomIn className="h-3.5 w-3.5" />
            </button>
          </div>
        </div>
      </div>

      {/* Main Image Viewport with Overlaid Bounding Boxes */}
      <div
        id="ai-canvas-viewport"
        className="relative w-full min-h-[460px] max-h-[75vh] overflow-hidden rounded-xl bg-slate-950 select-none shadow-inner border border-slate-200/60 flex items-center justify-center p-3"
      >
        {currentSrc && !imageError ? (
          <div
            className="relative inline-block max-w-full max-h-[70vh] transition-transform duration-200"
            style={{ transform: `scale(${zoom / 100})`, transformOrigin: 'center center' }}
          >
            <img
              src={currentSrc}
              alt={isPII ? 'PII Masking Asset View' : 'Object Detection Asset View'}
              referrerPolicy="no-referrer"
              onLoad={() => setIsImageLoading(false)}
              onError={handleImageError}
              className="block max-w-full max-h-[70vh] w-auto h-auto object-contain select-none pointer-events-none rounded shadow-md"
            />
            {isImageLoading && (
              <div className="absolute inset-0 flex items-center justify-center bg-slate-950/40 backdrop-blur-xs z-10 pointer-events-none">
                <Loader2 className="w-7 h-7 text-blue-400 animate-spin" />
              </div>
            )}

            {/* Overlaid Detection Bounding Boxes and Redaction Masks */}
            {showLabels && detections.length > 0 && (
              <div className="absolute inset-0 pointer-events-none">
                {detections.map((item) => {
                  const isSelected = selectedId === item.id;
                  const detectionColor = getDetectionColor(item);
                  return (
                    <div
                      key={item.id}
                      id={`bbox-${item.id}`}
                      onClick={() => onSelect(item.id)}
                      className={`absolute pointer-events-auto cursor-pointer transition-all duration-150 ${
                        isSelected
                          ? 'ring-2 ring-white ring-offset-2 ring-offset-slate-900/80 z-30 shadow-lg'
                          : 'hover:ring-1 hover:ring-white/80 z-20'
                      }`}
                      style={{
                        left: `${item.box.x}%`,
                        top: `${item.box.y}%`,
                        width: `${item.box.width}%`,
                        height: `${item.box.height}%`,
                        border: boxStyle === 'corner' ? '0' : `2px ${boxStyle} ${detectionColor}`,
                        backgroundColor: isPII ? 'rgba(15, 23, 42, 0.88)' : `${detectionColor}15`,
                        backdropFilter: isPII ? 'blur(6px)' : undefined,
                      }}
                      title={`${item.name}${item.confidence == null ? '' : ` (${(item.confidence * 100).toFixed(0)}%)`}`}
                    >
                      {boxStyle === 'corner' && (
                        <>
                          <span className="absolute left-0 top-0 h-3 w-3 border-l-2 border-t-2" style={{ borderColor: detectionColor }} />
                          <span className="absolute right-0 top-0 h-3 w-3 border-r-2 border-t-2" style={{ borderColor: detectionColor }} />
                          <span className="absolute bottom-0 left-0 h-3 w-3 border-b-2 border-l-2" style={{ borderColor: detectionColor }} />
                          <span className="absolute bottom-0 right-0 h-3 w-3 border-b-2 border-r-2" style={{ borderColor: detectionColor }} />
                        </>
                      )}
                      {/* Tag label tab pinned to top */}
                      <div
                        className="absolute -top-5 left-0 px-1.5 py-0.5 text-[10px] font-bold text-white whitespace-nowrap rounded-t shadow-xs flex items-center gap-1 leading-tight tracking-tight select-none"
                        style={{ backgroundColor: detectionColor }}
                      >
                        <span>{item.name}</span>
                        <span className="font-mono">{item.confidence == null ? (isPII ? 'Masked' : 'Human') : item.confidence.toFixed(2)}</span>
                      </div>
                    </div>
                  );
                })}
              </div>
            )}
          </div>
        ) : (
          <div className="flex flex-col items-center justify-center text-slate-400 font-medium text-xs py-16 space-y-3">
            <ImageOff className="w-8 h-8 text-slate-500 opacity-60" />
            <span>
              {imageError
                ? 'Failed to load asset image from backend'
                : isLoading
                ? 'Loading asset image...'
                : 'No asset image available for this project'}
            </span>
            {imageError && (
              <button
                type="button"
                onClick={handleManualRetry}
                className="inline-flex items-center gap-1.5 px-3 py-1.5 text-xs font-semibold rounded-lg bg-blue-600 text-white hover:bg-blue-700 active:scale-95 transition cursor-pointer shadow-xs"
              >
                <RefreshCw className="w-3.5 h-3.5" />
                Retry Loading Image
              </button>
            )}
          </div>
        )}
      </div>
    </div>
  );
};
