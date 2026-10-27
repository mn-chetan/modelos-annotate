import { useState } from 'react';
import { Eye, EyeOff, MousePointer2 } from 'lucide-react';
import type { Annotation, LiveAsset } from '../store';
import { api } from '../../services/api';
import { BoxOverlay } from './BoxOverlay';

export function ImageBoxes({
  asset,
  annotations,
  colours = {},
  selected = '',
  onSelect,
  hovered = '',
  onHover,
}: {
  asset: LiveAsset;
  annotations: Annotation[];
  colours?: Record<string, string>;
  selected?: string;
  hovered?: string;
  onSelect?: (id: string) => void;
  onHover?: (id: string) => void;
}) {
  const [names, setNames] = useState(false);
  const [visible, setVisible] = useState(true);
  const [failed, setFailed] = useState(false);
  return (
    <div className="prediction-stage">
      <div className="prediction-stage-toolbar">
        <span>
          <span className="live-dot" />
          AI predictions
        </span>
        <div>
          <label
            className="names-toggle"
            title="Space names to avoid overlap. Hover any box to inspect it."
          >
            <input
              type="checkbox"
              checked={names}
              onChange={(e) => setNames(e.target.checked)}
            />
            Names
          </label>
          <button
            className="studio-icon"
            title={visible ? 'View original image' : 'Show bounding boxes'}
            aria-label={visible ? 'View original image' : 'Show bounding boxes'}
            aria-pressed={!visible}
            onClick={() => setVisible((v) => !v)}
          >
            {visible ? <Eye size={16} /> : <EyeOff size={16} />}
          </button>
        </div>
      </div>
      <div className="prediction-image-wrap">
        <div className="image-boxes" key={asset.id}>
          <img
            src={api.getAssetImageUrl(asset.id)}
            alt={asset.filename}
            style={failed ? { display: 'none' } : undefined}
            onLoad={() => setFailed(false)}
            onError={() => setFailed(true)}
          />
          {!failed && (
            <BoxOverlay
              annotations={annotations}
              colours={colours}
              selected={selected}
              hovered={hovered}
              names={names}
              visible={visible}
              onSelect={onSelect}
              onHover={onHover}
              aria-label="AI bounding boxes"
            />
          )}
          {failed && (
            <div className="image-unavailable">
              <EyeOff size={24} />
              <b>Image unavailable</b>
              <span>The original file could not be loaded.</span>
            </div>
          )}
        </div>
      </div>
      <div className="canvas-status">
        <span>
          <MousePointer2 size={13} />
          {visible
            ? names
              ? 'Names are spaced. Hover any box to inspect.'
              : 'Hover a box to see its label.'
            : 'Original image · boxes hidden'}
        </span>
        <span>
          {asset.width} × {asset.height}
        </span>
      </div>
    </div>
  );
}
