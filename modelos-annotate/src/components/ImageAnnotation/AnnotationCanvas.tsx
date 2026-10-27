import React, { useState } from 'react';
import {
  AnnotationItem,
  AnnotationToolType,
  FilmstripItem,
  LabelChip,
} from '../../types';
import {
  MousePointer,
  Square,
  Hexagon,
  Paintbrush,
  Target,
  Spline,
  Eraser,
  Hand,
  Crosshair,
  ZoomIn,
  RotateCcw,
  RotateCw,
  Settings,
  Plus,
  Maximize2,
  Link,
  ChevronLeft,
  ChevronRight,
  Sparkles,
} from 'lucide-react';

interface AnnotationCanvasProps {
  annotations: AnnotationItem[];
  selectedAnnotationId: number | null;
  onSelectAnnotation: (id: number) => void;
  activeTool: AnnotationToolType;
  onChangeTool: (tool: AnnotationToolType) => void;
  labels: LabelChip[];
  activeLabelId: string;
  onSelectLabel: (id: string) => void;
  onAddLabel: () => void;
}

export const AnnotationCanvas: React.FC<AnnotationCanvasProps> = ({
  annotations,
  selectedAnnotationId,
  onSelectAnnotation,
  activeTool,
  onChangeTool,
  labels,
  activeLabelId,
  onSelectLabel,
  onAddLabel,
}) => {
  const [showLabels, setShowLabels] = useState<boolean>(true);
  const [zoomLevel, setZoomLevel] = useState<number>(100);
  const [activeFilmIndex, setActiveFilmIndex] = useState<number>(0);

  // Tools list matching the left sidebar in the screenshot
  const tools: { id: AnnotationToolType; label: string; icon: React.ElementType }[] = [
    { id: 'select', label: 'Select', icon: MousePointer },
    { id: 'bbox', label: 'BBox', icon: Square },
    { id: 'polygon', label: 'Polygon', icon: Hexagon },
    { id: 'mask', label: 'Mask', icon: Paintbrush },
    { id: 'keypoint', label: 'Keypoint', icon: Target },
    { id: 'polyline', label: 'Polyline', icon: Spline },
    { id: 'eraser', label: 'Eraser', icon: Eraser },
    { id: 'pan', label: 'Pan', icon: Hand },
    { id: 'point', label: 'Point', icon: Crosshair },
    { id: 'zoom', label: 'Zoom', icon: ZoomIn },
    { id: 'undo', label: 'Undo', icon: RotateCcw },
    { id: 'redo', label: 'Redo', icon: RotateCw },
  ];

  // Filmstrip items
  const filmstripItems: FilmstripItem[] = [
    { id: 1, filename: 'IMG_00452.jpg', active: activeFilmIndex === 0, imageSrc: '' },
    { id: 2, filename: 'IMG_00453.jpg', active: activeFilmIndex === 1, imageSrc: '' },
    { id: 3, filename: 'IMG_00454.jpg', active: activeFilmIndex === 2, imageSrc: '' },
    { id: 4, filename: 'IMG_00455.jpg', active: activeFilmIndex === 3, imageSrc: '' },
    { id: 5, filename: 'IMG_00456.jpg', active: activeFilmIndex === 4, imageSrc: '' },
    { id: 6, filename: 'IMG_00457.jpg', active: activeFilmIndex === 5, imageSrc: '' },
    { id: 7, filename: 'IMG_00458.jpg', active: activeFilmIndex === 6, imageSrc: '' },
  ];

  return (
    <div
      id="annotation-canvas-wrapper"
      className="flex flex-col rounded-xl border border-slate-200 bg-white shadow-2xs overflow-hidden"
    >
      {/* Top Strip over the canvas: Labels & Canvas utilities */}
      <div className="flex flex-wrap items-center justify-between gap-3 border-b border-slate-200 bg-slate-50/70 px-4 py-2.5">
        {/* Left: Mode Switch & Labels */}
        <div className="flex flex-wrap items-center gap-2">
          {/* Active Tab */}
          <div className="flex items-center gap-1.5 border-r border-slate-200 pr-3">
            <span className="flex items-center gap-1 rounded-md bg-white px-2.5 py-1 text-xs font-bold text-slate-800 border border-slate-200 shadow-2xs">
              <Plus className="h-3 w-3 text-blue-600" />
              <span>Image</span>
            </span>
            <span className="text-xs font-semibold text-slate-600 px-2 py-1">
              Annotation Tools
            </span>
          </div>

          {/* Labels chips */}
          <div className="flex items-center gap-1.5 flex-wrap">
            <span className="text-[11px] font-bold text-slate-400 uppercase tracking-wider mr-1">
              Labels:
            </span>
            {labels.map((chip) => {
              const isSelected = activeLabelId === chip.id;
              return (
                <button
                  key={chip.id}
                  id={`label-chip-${chip.id}`}
                  onClick={() => onSelectLabel(chip.id)}
                  className={`flex items-center gap-1.5 rounded-full px-2.5 py-0.5 text-xs font-semibold transition cursor-pointer ${
                    isSelected
                      ? 'bg-slate-900 text-white shadow-xs'
                      : 'bg-white text-slate-700 hover:bg-slate-100 border border-slate-200/90'
                  }`}
                >
                  <span
                    className="h-2 w-2 rounded-full shrink-0"
                    style={{ backgroundColor: chip.dotColor }}
                  />
                  <span>{chip.name}</span>
                </button>
              );
            })}
            <button
              id="btn-add-label"
              onClick={onAddLabel}
              className="flex h-6 w-6 items-center justify-center rounded-full border border-dashed border-slate-300 bg-white text-slate-500 hover:border-slate-400 hover:text-slate-800 transition cursor-pointer"
              title="Add new label class"
            >
              <Plus className="h-3.5 w-3.5" />
            </button>
          </div>
        </div>

        {/* Right Canvas Utilities */}
        <div className="flex items-center gap-2 text-slate-600">
          {/* Zoom dropdown */}
          <div className="flex items-center rounded-md border border-slate-200 bg-white px-2 py-1 text-xs font-semibold text-slate-700 shadow-2xs">
            <span>{zoomLevel}%</span>
          </div>

          <button
            onClick={() => setZoomLevel((z) => Math.min(z + 25, 300))}
            className="p-1 rounded hover:bg-slate-200 text-slate-600 hover:text-slate-900 transition cursor-pointer"
            title="Zoom In"
          >
            <ZoomIn className="h-4 w-4" />
          </button>

          <button
            onClick={() => setZoomLevel(100)}
            className="p-1 rounded hover:bg-slate-200 text-slate-600 hover:text-slate-900 transition cursor-pointer"
            title="Fit to Screen"
          >
            <Maximize2 className="h-4 w-4" />
          </button>

          <button
            className="p-1 rounded hover:bg-slate-200 text-slate-600 hover:text-slate-900 transition cursor-pointer"
            title="Link views"
          >
            <Link className="h-4 w-4" />
          </button>

          <button
            className="p-1 rounded hover:bg-slate-200 text-slate-600 hover:text-slate-900 transition cursor-pointer"
            title="Rotate Left"
          >
            <RotateCcw className="h-4 w-4" />
          </button>

          {/* Show Labels Switch */}
          <div className="flex items-center gap-1.5 border-l border-slate-200 pl-2">
            <span className="text-xs font-medium text-slate-600 select-none">Show Labels</span>
            <button
              id="btn-toggle-show-labels"
              onClick={() => setShowLabels(!showLabels)}
              className={`relative inline-flex h-5 w-9 shrink-0 cursor-pointer rounded-full border-2 border-transparent transition-colors duration-200 ease-in-out focus:outline-none ${
                showLabels ? 'bg-blue-600' : 'bg-slate-300'
              }`}
            >
              <span
                className={`pointer-events-none inline-block h-4 w-4 transform rounded-full bg-white shadow-sm ring-0 transition duration-200 ease-in-out ${
                  showLabels ? 'translate-x-4' : 'translate-x-0'
                }`}
              />
            </button>
          </div>
        </div>
      </div>

      {/* Main Workspace: Left Tool Toolbar + Canvas Viewport */}
      <div className="relative flex min-h-[440px] bg-slate-900">
        {/* Left Vertical Tools Bar */}
        <aside className="z-10 flex w-12 flex-col items-center justify-between border-r border-slate-800 bg-[#070e24] py-3 text-slate-400">
          <div className="flex flex-col items-center gap-1 w-full px-1.5">
            {tools.map((t) => {
              const Icon = t.icon;
              const isActive = activeTool === t.id;
              return (
                <button
                  key={t.id}
                  id={`canvas-tool-${t.id}`}
                  onClick={() => onChangeTool(t.id)}
                  title={t.label}
                  className={`flex h-8 w-8 items-center justify-center rounded-lg transition cursor-pointer ${
                    isActive
                      ? 'bg-blue-600 text-white shadow-md shadow-blue-500/20'
                      : 'text-slate-400 hover:bg-slate-800/80 hover:text-slate-200'
                  }`}
                >
                  <Icon className="h-4 w-4" />
                </button>
              );
            })}
          </div>

          {/* Settings tool at bottom */}
          <button
            id="canvas-tool-settings"
            onClick={() => onChangeTool('settings')}
            className={`flex h-8 w-8 items-center justify-center rounded-lg transition cursor-pointer text-slate-400 hover:bg-slate-800/80 hover:text-slate-200 ${
              activeTool === 'settings' ? 'bg-blue-600 text-white' : ''
            }`}
            title="Canvas Settings"
          >
            <Settings className="h-4 w-4" />
          </button>
        </aside>

        {/* Interactive Canvas Stage */}
        <div
          id="canvas-viewport"
          className="relative flex-1 overflow-hidden select-none flex items-center justify-center bg-[#0b1329]"
        >
          {/* Realistic Traffic Street Scene SVG rendering */}
          <div
            className="relative w-full max-w-[880px] aspect-[16/10] overflow-hidden shadow-2xl transition-transform duration-150"
            style={{ transform: `scale(${zoomLevel / 100})` }}
          >
            {/* Base Image Representation */}
            <svg
              viewBox="0 0 880 550"
              className="h-full w-full object-cover"
              preserveAspectRatio="xMidYMid slice"
            >
              <defs>
                <linearGradient id="skyGrad" x1="0%" y1="0%" x2="0%" y2="100%">
                  <stop offset="0%" stopColor="#7dd3fc" />
                  <stop offset="60%" stopColor="#bae6fd" />
                  <stop offset="100%" stopColor="#e0f2fe" />
                </linearGradient>

                <linearGradient id="roadGrad" x1="0%" y1="0%" x2="0%" y2="100%">
                  <stop offset="0%" stopColor="#334155" />
                  <stop offset="100%" stopColor="#1e293b" />
                </linearGradient>

                <linearGradient id="carBody" x1="0%" y1="0%" x2="100%" y2="100%">
                  <stop offset="0%" stopColor="#1e293b" />
                  <stop offset="100%" stopColor="#0f172a" />
                </linearGradient>

                <linearGradient id="whiteCarBody" x1="0%" y1="0%" x2="100%" y2="100%">
                  <stop offset="0%" stopColor="#ffffff" />
                  <stop offset="100%" stopColor="#cbd5e1" />
                </linearGradient>

                <linearGradient id="busBody" x1="0%" y1="0%" x2="0%" y2="100%">
                  <stop offset="0%" stopColor="#1d4ed8" />
                  <stop offset="100%" stopColor="#1e40af" />
                </linearGradient>
              </defs>

              {/* Sky */}
              <rect width="880" height="240" fill="url(#skyGrad)" />

              {/* City Backdrop Architecture */}
              <path
                d="M 0 240 L 0 130 L 45 130 L 45 90 L 110 90 L 110 145 L 170 145 L 170 80 L 230 80 L 230 160 L 310 160 L 310 110 L 390 110 L 390 170 L 470 170 L 470 70 L 560 70 L 560 140 L 640 140 L 640 95 L 720 95 L 720 155 L 790 155 L 790 120 L 880 120 L 880 240 Z"
                fill="#94a3b8"
                opacity="0.45"
              />
              {/* Foreground Buildings */}
              <path
                d="M 0 240 L 0 170 L 70 170 L 70 140 L 140 140 L 140 190 L 200 190 L 200 150 L 280 150 L 280 210 L 360 210 L 360 160 L 440 160 L 440 220 L 530 220 L 530 150 L 620 150 L 620 200 L 700 200 L 700 165 L 780 165 L 780 215 L 880 215 L 880 240 Z"
                fill="#64748b"
                opacity="0.65"
              />

              {/* Building windows details */}
              <rect x="25" y="185" width="6" height="8" fill="#fef08a" opacity="0.6" />
              <rect x="40" y="185" width="6" height="8" fill="#fef08a" opacity="0.6" />
              <rect x="90" y="155" width="7" height="10" fill="#fef08a" opacity="0.7" />
              <rect x="105" y="155" width="7" height="10" fill="#fef08a" opacity="0.7" />
              <rect x="550" y="170" width="8" height="10" fill="#fef08a" opacity="0.8" />
              <rect x="570" y="170" width="8" height="10" fill="#fef08a" opacity="0.8" />

              {/* Street Foliage / Trees */}
              <circle cx="160" cy="235" r="16" fill="#15803d" opacity="0.9" />
              <circle cx="175" cy="230" r="18" fill="#16a34a" opacity="0.9" />
              <circle cx="710" cy="235" r="18" fill="#15803d" opacity="0.9" />
              <circle cx="730" cy="230" r="15" fill="#16a34a" opacity="0.9" />

              {/* Sidewalks and Curbs */}
              <polygon points="0,230 180,240 160,550 0,550" fill="#cbd5e1" />
              <polygon points="880,230 700,240 720,550 880,550" fill="#cbd5e1" />
              {/* Sidewalk lines */}
              <line x1="0" y1="320" x2="165" y2="320" stroke="#94a3b8" strokeWidth="1" />
              <line x1="0" y1="420" x2="162" y2="420" stroke="#94a3b8" strokeWidth="1" />
              <line x1="715" y1="320" x2="880" y2="320" stroke="#94a3b8" strokeWidth="1" />
              <line x1="718" y1="420" x2="880" y2="420" stroke="#94a3b8" strokeWidth="1" />

              {/* Main Asphalt Road */}
              <polygon points="180,240 700,240 720,550 160,550" fill="url(#roadGrad)" />

              {/* Road markings */}
              <line
                x1="440"
                y1="240"
                x2="440"
                y2="550"
                stroke="#facc15"
                strokeWidth="4"
                strokeDasharray="28,24"
              />
              <line
                x1="310"
                y1="240"
                x2="280"
                y2="550"
                stroke="#ffffff"
                strokeWidth="2.5"
                strokeDasharray="20,20"
                opacity="0.8"
              />
              <line
                x1="570"
                y1="240"
                x2="600"
                y2="550"
                stroke="#ffffff"
                strokeWidth="2.5"
                strokeDasharray="20,20"
                opacity="0.8"
              />

              {/* Pedestrian on left sidewalk (person) */}
              <g id="scene-person">
                {/* Body */}
                <ellipse cx="105" cy="318" rx="7" ry="7" fill="#f87171" />
                <path d="M 98 325 C 98 325, 105 324, 112 325 L 114 362 L 96 362 Z" fill="#1e3a8a" />
                <rect x="98" y="362" width="6" height="34" rx="2" fill="#0f172a" />
                <rect x="106" y="362" width="6" height="34" rx="2" fill="#0f172a" />
                {/* Backpack */}
                <rect x="93" y="328" width="6" height="16" rx="2" fill="#b91c1c" />
              </g>

              {/* Bus on left center lane */}
              <g id="scene-bus">
                <rect x="200" y="220" width="105" height="135" rx="10" fill="url(#busBody)" />
                {/* Windshield */}
                <rect x="207" y="230" width="91" height="42" rx="4" fill="#67e8f9" opacity="0.8" />
                <line x1="252" y1="230" x2="252" y2="272" stroke="#1e40af" strokeWidth="2" />
                {/* Destination sign */}
                <rect x="220" y="224" width="65" height="5" rx="1" fill="#facc15" />
                {/* Headlights */}
                <circle cx="218" cy="330" r="6" fill="#fef08a" />
                <circle cx="287" cy="330" r="6" fill="#fef08a" />
                {/* Grille */}
                <rect x="232" y="324" width="41" height="16" rx="2" fill="#0f172a" />
                {/* Wheels */}
                <rect x="196" y="338" width="8" height="20" rx="3" fill="#020617" />
                <rect x="301" y="338" width="8" height="20" rx="3" fill="#020617" />
              </g>

              {/* White Sedan ahead (car 0.88) */}
              <g id="scene-white-car">
                <path
                  d="M 395 270 C 405 258, 435 258, 445 270 L 458 290 C 458 298, 382 298, 382 290 Z"
                  fill="url(#whiteCarBody)"
                />
                {/* Rear window */}
                <polygon points="404,265 436,265 444,277 396,277" fill="#334155" />
                {/* Taillights */}
                <rect x="384" y="282" width="10" height="4" rx="1" fill="#ef4444" />
                <rect x="446" y="282" width="10" height="4" rx="1" fill="#ef4444" />
                <rect x="408" y="283" width="24" height="6" rx="1" fill="#e2e8f0" />
                {/* Tires */}
                <rect x="382" y="294" width="9" height="10" rx="2" fill="#0f172a" />
                <rect x="449" y="294" width="9" height="10" rx="2" fill="#0f172a" />
              </g>

              {/* Black SUV in foreground left (car 0.92) */}
              <g id="scene-black-car">
                {/* Roof & Cabin */}
                <path
                  d="M 270 375 C 285 345, 360 345, 375 375 L 398 420 C 398 440, 248 440, 248 420 Z"
                  fill="url(#carBody)"
                />
                {/* Rear Windshield */}
                <polygon points="280,360 365,360 380,388 265,388" fill="#38bdf8" opacity="0.75" />
                {/* Taillights */}
                <rect x="252" y="398" width="24" height="10" rx="2" fill="#dc2626" />
                <rect x="368" y="398" width="24" height="10" rx="2" fill="#dc2626" />
                {/* License Plate */}
                <rect x="302" y="405" width="40" height="14" rx="2" fill="#ffffff" />
                <rect x="312" y="410" width="20" height="4" fill="#0f172a" />
                {/* Bumper & Exhaust */}
                <rect x="250" y="420" width="144" height="18" rx="4" fill="#1e293b" />
                <rect x="246" y="432" width="18" height="26" rx="4" fill="#020617" />
                <rect x="380" y="432" width="18" height="26" rx="4" fill="#020617" />
              </g>

              {/* Motorcycle in front right (motorcycle 0.81) */}
              <g id="scene-motorcycle">
                {/* Driver */}
                <circle cx="530" cy="360" r="9" fill="#eab308" />
                <path d="M 522 370 L 538 370 L 536 405 L 524 405 Z" fill="#1e293b" />
                {/* Bike Frame */}
                <rect x="520" y="395" width="20" height="30" rx="3" fill="#f97316" />
                {/* Taillight */}
                <circle cx="530" cy="402" r="4" fill="#ef4444" />
                {/* Rear tire */}
                <ellipse cx="530" cy="432" rx="7" ry="12" fill="#020617" />
              </g>

              {/* Bicycle & Cyclist on far right (bicycle 0.76) */}
              <g id="scene-bicycle">
                {/* Cyclist helmet & person */}
                <circle cx="642" cy="342" r="7" fill="#a855f7" />
                <path d="M 636 350 L 648 350 L 646 376 L 638 376 Z" fill="#475569" />
                {/* Bike frame */}
                <line x1="642" y1="365" x2="636" y2="395" stroke="#9333ea" strokeWidth="2.5" />
                <line x1="642" y1="365" x2="650" y2="395" stroke="#9333ea" strokeWidth="2.5" />
                <circle cx="634" cy="395" r="7" stroke="#020617" strokeWidth="2" fill="none" />
                <circle cx="652" cy="395" r="7" stroke="#020617" strokeWidth="2" fill="none" />
              </g>

              {/* Traffic Light on right pole (traffic light 0.83) */}
              <g id="scene-traffic-light">
                {/* Metal Pole */}
                <line x1="695" y1="180" x2="695" y2="340" stroke="#64748b" strokeWidth="5" />
                {/* Signal Housing */}
                <rect x="686" y="195" width="18" height="46" rx="4" fill="#0f172a" />
                {/* Red, Amber, Green lenses */}
                <circle cx="695" cy="204" r="4.5" fill="#ef4444" />
                <circle cx="695" cy="218" r="4.5" fill="#475569" />
                <circle cx="695" cy="232" r="4.5" fill="#475569" />
              </g>
            </svg>

            {/* Overlaid Interactive Bounding Boxes */}
            {annotations.map((item) => {
              if (!item.visible) return null;
              const isSelected = selectedAnnotationId === item.id;
              const { x, y, width, height } = item.bbox;

              return (
                <div
                  key={item.id}
                  id={`canvas-bbox-${item.id}`}
                  onClick={(e) => {
                    e.stopPropagation();
                    onSelectAnnotation(item.id);
                  }}
                  className={`absolute cursor-pointer transition-all duration-100 ${
                    isSelected ? 'ring-2 ring-white/60 shadow-lg' : 'hover:ring-1 hover:ring-white/40'
                  }`}
                  style={{
                    left: `${x}%`,
                    top: `${y}%`,
                    width: `${width}%`,
                    height: `${height}%`,
                    border: `2px solid ${item.color}`,
                    backgroundColor: isSelected ? `${item.color}20` : `${item.color}0a`,
                  }}
                >
                  {/* Tag Label */}
                  {showLabels && (
                    <div
                      className="absolute -top-5 left-0 flex items-center gap-1 rounded-t-sm px-1.5 py-0.5 text-[10px] font-bold text-white shadow-xs select-none whitespace-nowrap"
                      style={{ backgroundColor: item.color }}
                    >
                      <span>{item.tagLabel}</span>
                    </div>
                  )}

                  {/* Corner Resize Handles when selected */}
                  {isSelected && (
                    <>
                      <span
                        className="absolute -top-1 -left-1 h-2.5 w-2.5 rounded-full border border-white bg-white shadow-xs"
                        style={{ borderColor: item.color }}
                      />
                      <span
                        className="absolute -top-1 -right-1 h-2.5 w-2.5 rounded-full border border-white bg-white shadow-xs"
                        style={{ borderColor: item.color }}
                      />
                      <span
                        className="absolute -bottom-1 -left-1 h-2.5 w-2.5 rounded-full border border-white bg-white shadow-xs"
                        style={{ borderColor: item.color }}
                      />
                      <span
                        className="absolute -bottom-1 -right-1 h-2.5 w-2.5 rounded-full border border-white bg-white shadow-xs"
                        style={{ borderColor: item.color }}
                      />
                    </>
                  )}
                </div>
              );
            })}
          </div>
        </div>
      </div>

      {/* Filmstrip Carousel Bar underneath Canvas */}
      <div
        id="canvas-filmstrip-bar"
        className="flex items-center justify-between border-t border-slate-200 bg-slate-50 px-3 py-2.5"
      >
        <button
          onClick={() => setActiveFilmIndex((i) => Math.max(0, i - 1))}
          className="flex h-7 w-7 items-center justify-center rounded-md border border-slate-200 bg-white text-slate-600 hover:bg-slate-100 hover:text-slate-900 transition cursor-pointer"
        >
          <ChevronLeft className="h-4 w-4" />
        </button>

        {/* Thumbnails row */}
        <div className="flex items-center gap-2 overflow-x-auto px-2 py-0.5">
          {filmstripItems.map((item, idx) => {
            const isActive = activeFilmIndex === idx;
            return (
              <div
                key={item.id}
                onClick={() => setActiveFilmIndex(idx)}
                className={`relative h-12 w-20 shrink-0 cursor-pointer overflow-hidden rounded-md border-2 transition-all ${
                  isActive
                    ? 'border-blue-600 ring-2 ring-blue-500/20 shadow-xs scale-105'
                    : 'border-slate-200 opacity-70 hover:opacity-100 hover:border-slate-300'
                }`}
              >
                {/* SVG Mini thumbnail */}
                <svg className="h-full w-full object-cover" viewBox="0 0 80 48">
                  <rect width="80" height="48" fill="#334155" />
                  <path d="M0 0h80v20H0z" fill="#93c5fd" opacity="0.6" />
                  <rect x="25" y="26" width="18" height="12" rx="2" fill="#ef4444" />
                  <rect x="48" y="22" width="14" height="16" rx="2" fill="#3b82f6" />
                </svg>

                {isActive && (
                  <span className="absolute bottom-0 left-0 right-0 bg-blue-600 py-0.2 text-center text-[8px] font-bold text-white uppercase tracking-tighter">
                    Active
                  </span>
                )}
              </div>
            );
          })}
        </div>

        <button
          onClick={() =>
            setActiveFilmIndex((i) => Math.min(filmstripItems.length - 1, i + 1))
          }
          className="flex h-7 w-7 items-center justify-center rounded-md border border-slate-200 bg-white text-slate-600 hover:bg-slate-100 hover:text-slate-900 transition cursor-pointer"
        >
          <ChevronRight className="h-4 w-4" />
        </button>
      </div>
    </div>
  );
};
