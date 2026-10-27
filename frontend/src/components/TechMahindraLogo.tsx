import React from 'react';
import { BrandLockup } from '../brand/BrandLockup';

interface TechMahindraLogoProps {
  className?: string;
  size?: 'sm' | 'md' | 'lg';
  /** Kept for existing call sites; the approved lockup always carries the product name. */
  showSubbrand?: boolean;
}

/** Existing call sites keep their API; rendering now uses the approved brand asset. */
export const TechMahindraLogo: React.FC<TechMahindraLogoProps> = ({ className = '', size = 'md' }) => (
  <BrandLockup size={size} className={className} />
);
