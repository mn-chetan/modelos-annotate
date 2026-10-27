import React from 'react';
import { BrandLockup } from '../brand/BrandLockup';

interface TechMahindraLogoProps {
  className?: string;
  size?: 'sm' | 'md' | 'lg';
  showSubbrand?: boolean;
}

/** Existing call sites keep their API; rendering now uses the approved brand asset. */
export const TechMahindraLogo: React.FC<TechMahindraLogoProps> = ({
  className = '',
  size = 'md',
  showSubbrand = true,
}) => <BrandLockup size={size} product={showSubbrand} className={className} />;
