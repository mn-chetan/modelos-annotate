import React from 'react';

interface TechMahindraLogoProps {
  className?: string;
  size?: 'sm' | 'md' | 'lg';
  showSubbrand?: boolean;
}

export const TechMahindraLogo: React.FC<TechMahindraLogoProps> = ({
  className = '',
  size = 'md',
  showSubbrand = true,
}) => {
  const heightClass = size === 'sm' ? 'h-6' : size === 'lg' ? 'h-9' : 'h-7';

  return (
    <div
      id="tech-mahindra-brand-header"
      className={`inline-flex items-center gap-2.5 select-none ${className}`}
    >
      {/* Official Tech Mahindra Graphic Mark + Wordmark */}
      <div className={`flex items-center gap-2.5 ${heightClass}`}>
        {/* Slanted Red Parallelogram Graphic Mark based on official logo */}
        <svg
          viewBox="0 0 60 110"
          className="h-full w-auto shrink-0"
          fill="none"
          xmlns="http://www.w3.org/2000/svg"
          aria-hidden="true"
        >
          {/* Tech Mahindra Red Parallelogram with vertical sides and upward-sloping top and bottom */}
          <polygon
            points="4,40 56,10 56,80 4,110"
            fill="#E31837"
          />
        </svg>

        {/* Wordmark: TECH (bold dark charcoal uppercase) + mahindra (crimson red lowercase) */}
        <div className="flex flex-col justify-center leading-none">
          <span
            className="font-black tracking-[0.14em] text-[#33373D] uppercase"
            style={{
              fontSize: size === 'sm' ? '10px' : size === 'lg' ? '14px' : '11.5px',
              lineHeight: '1.05',
              fontFamily: 'system-ui, -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif',
              fontWeight: 900,
            }}
          >
            TECH
          </span>
          <span
            className="font-bold tracking-tight text-[#E31837] lowercase"
            style={{
              fontSize: size === 'sm' ? '13px' : size === 'lg' ? '19px' : '15.5px',
              lineHeight: '1.05',
              fontFamily: '"Plus Jakarta Sans", system-ui, -apple-system, sans-serif',
              fontWeight: 800,
              letterSpacing: '-0.03em',
            }}
          >
            mahindra
          </span>
        </div>
      </div>

      {showSubbrand && (
        <div className="flex items-center gap-1.5 border-l border-[#E2DDD5] pl-2.5">
          <span className="text-slate-700 font-semibold text-xs tracking-tight">
            ModelOS Annotate
          </span>
        </div>
      )}
    </div>
  );
};
