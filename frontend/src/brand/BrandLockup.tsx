import '@fontsource-variable/newsreader/opsz.css';
import './brand.css';
import techMahindraLogo from './tech-mahindra-logo.jpg';

export const PRODUCT_NAME = 'ModelOS Annotate';

/**
 * The brand lockup, reused everywhere the product is named:
 *
 *   [Tech Mahindra mark] │ ModelOS Annotate
 *
 * The approved JPEG is cropped to its content box by CSS and never redrawn or recoloured.
 * It relies on multiply blending, so it only belongs on light surfaces.
 */
export function BrandLockup({
  size = 'md',
  stacked = false,
  product = true,
  className = '',
}: {
  size?: 'sm' | 'md' | 'lg';
  stacked?: boolean;
  product?: boolean;
  className?: string;
}) {
  return (
    <span className={`lockup lockup-${size}${stacked ? ' lockup-stacked' : ''} ${className}`.trim()}>
      <span className="lockup-mark">
        <img src={techMahindraLogo} alt="Tech Mahindra" width={1536} height={804} />
      </span>
      {product ? (
        <>
          <span className="lockup-rule" aria-hidden />
          <span className="lockup-product">{PRODUCT_NAME}</span>
        </>
      ) : null}
    </span>
  );
}
