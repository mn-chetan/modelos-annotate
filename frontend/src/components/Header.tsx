import React from 'react';
import { Menu } from 'lucide-react';

interface HeaderProps {
  onToggleMobileSidebar: () => void;
  searchQuery?: string;
  onSearchChange?: (val: string) => void;
  onOpenNotifications?: () => void;
  notificationCount?: number;
}

export const Header: React.FC<HeaderProps> = ({
  onToggleMobileSidebar,
}) => {
  return (
    <header
      id="app-header"
      className="sticky top-0 z-30 flex h-16 w-full items-center justify-between border-b border-[#E2DDD5] bg-white/95 px-4 sm:px-8 backdrop-blur-md"
    >
      <div className="flex items-center gap-3">
        {/* Mobile menu toggle */}
        <button
          id="mobile-sidebar-toggle-btn"
          onClick={onToggleMobileSidebar}
          className="rounded-lg p-2 text-slate-600 hover:bg-slate-100 lg:hidden cursor-pointer"
          aria-label="Open sidebar"
        >
          <Menu className="h-5 w-5" />
        </button>
      </div>

      {/* Right side controls */}
      <div className="flex items-center gap-3 sm:gap-5">
        {/* Static operator identity; authentication controls are intentionally disabled. */}
        <div id="header-user-profile-pill" className="flex items-center gap-3">
            <div className="flex h-9 w-9 items-center justify-center rounded-full bg-[#0A0838] text-white font-semibold text-xs shadow-xs">
              AN
            </div>
            <div className="hidden md:flex flex-col text-left">
              <span className="text-xs sm:text-sm font-semibold text-slate-800 leading-tight">
                Annotator
              </span>
              <span className="text-[11px] text-slate-500 leading-tight">Annotator Lead</span>
            </div>
        </div>
      </div>
    </header>
  );
};
