import '@fontsource-variable/newsreader/opsz.css';
import './brand.css';
import logoUrl from './modelos-annotate-logo.png';

export const PRODUCT_NAME = 'ModelOS Annotate';

/**
 * The brand lockup, reused everywhere the product is named:
 *
 *   [Tech Mahindra mark] [ModelOS, powered by Tech Mahindra] │ Annotate
 *
 * One approved PNG with a transparent ground, cropped to its content box by CSS and never
 * redrawn or recoloured. Its grey rule and wordmark need a light surface.
 */
export function BrandLockup({ size = 'md', className = '' }: { size?: 'sm' | 'md' | 'lg' | 'fill'; className?: string }) {
  return (
    <span className={`lockup lockup-${size} ${className}`.trim()}>
      <img src={logoUrl} alt={`${PRODUCT_NAME}, powered by Tech Mahindra`} width={4561} height={1032} />
    </span>
  );
}
