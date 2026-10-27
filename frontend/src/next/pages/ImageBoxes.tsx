import type { Annotation, LiveAsset } from '../store';
import { api } from '../../services/api';
export function ImageBoxes({ asset, annotations }: { asset: LiveAsset; annotations: Annotation[] }) {
  return <div className="image-boxes"><img src={api.getAssetImageUrl(asset.id)} alt={asset.filename} />
    <svg viewBox="0 0 100 100" preserveAspectRatio="none" aria-label="AI bounding boxes">{annotations.filter(a=>a.geometry_type==='box' && a.review_status!=='rejected').map(a=><g key={a.id}><rect x={a.x} y={a.y} width={a.w} height={a.h} fill="none" stroke="#28a6de" strokeWidth="0.3" vectorEffect="non-scaling-stroke" /><text x={a.x} y={Math.max(2,a.y-0.8)} fontSize="2.2" fill="white" stroke="#15181e" strokeWidth="0.1">{a.label}</text></g>)}</svg>
  </div>;
}
