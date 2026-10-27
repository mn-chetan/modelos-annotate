import React, { useEffect, useMemo, useState } from 'react';
import {
  FolderOpen,
  Image as ImageIcon,
  FileText,
  Filter,
  Search,
  Loader2,
  Trash2,
  Plus,
  RefreshCw,
  Layers,
  X,
  CheckCircle2,
} from 'lucide-react';
import { api, ProjectResponse } from '../services/api';

interface ProjectsViewProps {
  onToast?: (message: string) => void;
  onCreateProject?: () => void;
  onSelectProject?: (project: ProjectResponse) => void;
}

export type ModalityFilter = 'all' | 'image' | 'text';

/**
 * Robust classifier for project modality.
 * Correctly distinguishes Text/NLP projects from Image/Vision detection projects.
 */
export const isTextProject = (project: ProjectResponse): boolean => {
  const mod = String((project as any).modality || '').toLowerCase().trim();
  const type = String(project.project_type || '').toLowerCase().trim();
  const task = String(project.task_type || '').toLowerCase().trim();
  const name = String(project.name || '').toLowerCase().trim();

  // Definite image/video/vision exclusions
  if (mod === 'image' || mod === 'video' || mod === 'audio') return false;
  if (/image|video|vision|detection|yolo|bounding|segmentation|bbox|polygon/.test(type)) return false;
  if (/traffic|vehicle|car|coco|detection|yolo|image_2/.test(name) && mod !== 'text') return false;

  // Definite text/NLP inclusions
  if (mod === 'text' || mod === 'document' || mod === 'nlp') return true;
  return /text|ner|sentiment|classification|relation|nlp|document|clinical|extraction|pii|summary/.test(
    `${type} ${task} ${name}`
  );
};

export const isImageProject = (project: ProjectResponse): boolean => {
  return !isTextProject(project);
};

export const ProjectsView: React.FC<ProjectsViewProps> = ({ onToast, onCreateProject, onSelectProject }) => {
  const [projects, setProjects] = useState<ProjectResponse[]>([]);
  const [isLoading, setIsLoading] = useState(true);
  const [deletingProjectId, setDeletingProjectId] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  // Filter states
  const [filterModality, setFilterModality] = useState<ModalityFilter>('all');
  const [searchQuery, setSearchQuery] = useState('');

  const loadProjects = async (forceRefresh = false) => {
    setIsLoading(true);
    setError(null);
    try {
      const list = await api.getProjects({ throwOnError: true, forceRefresh });
      setProjects(list);
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Unable to load projects');
    } finally {
      setIsLoading(false);
    }
  };

  useEffect(() => {
    void loadProjects();
  }, []);

  const handleDelete = async (project: ProjectResponse) => {
    if (!window.confirm(`Delete project "${project.name}"? This cannot be undone.`)) return;

    setDeletingProjectId(project.id);
    try {
      await api.deleteProject(project.id);
      setProjects((current) => current.filter((item) => item.id !== project.id));
      onToast?.(`Project "${project.name}" deleted successfully.`);
    } catch (err) {
      onToast?.(err instanceof Error ? err.message : 'Unable to delete project');
    } finally {
      setDeletingProjectId(null);
    }
  };

  const projectTypeLabel = (project: ProjectResponse) => {
    if (isTextProject(project)) {
      const type = project.task_type || project.project_type || 'Text Annotation';
      return type.toLowerCase().includes('text') ? type : `Text · ${type}`;
    }
    const type = project.task_type || project.project_type || 'Object Detection';
    return type.toLowerCase().includes('image') || type.toLowerCase().includes('detection') ? type : `Image · ${type}`;
  };

  // Pre-calculated counts for badges
  const totalCount = projects.length;
  const imageCount = useMemo(() => projects.filter(isImageProject).length, [projects]);
  const textCount = useMemo(() => projects.filter(isTextProject).length, [projects]);

  // Filtered project list
  const filteredProjects = useMemo(() => {
    return projects.filter((project) => {
      // 1. Modality filter
      if (filterModality === 'image' && !isImageProject(project)) return false;
      if (filterModality === 'text' && !isTextProject(project)) return false;

      // 2. Search query filter
      if (searchQuery.trim()) {
        const query = searchQuery.toLowerCase().trim();
        const name = String(project.name || '').toLowerCase();
        const type = String(project.project_type || '').toLowerCase();
        const task = String(project.task_type || '').toLowerCase();
        if (!name.includes(query) && !type.includes(query) && !task.includes(query)) {
          return false;
        }
      }
      return true;
    });
  }, [projects, filterModality, searchQuery]);

  return (
    <div className="flex min-h-screen flex-1 flex-col bg-[#F6F2EA] text-slate-800">
      <main className="mx-auto w-full max-w-[1400px] flex-1 px-4 py-8 sm:px-8 space-y-6">
        
        {/* Top Header Row */}
        <div className="flex flex-wrap items-center justify-between gap-4 border-b border-[#E5DFD3] pb-5">
          <div>
            <div className="flex items-center gap-2">
              <h1 className="text-2xl sm:text-3xl font-black tracking-tight text-slate-900">Projects</h1>
              <span className="rounded-full bg-slate-200/80 px-2.5 py-0.5 text-xs font-bold text-slate-700">
                {projects.length} Total
              </span>
            </div>
            <p className="mt-1 text-xs sm:text-sm text-slate-600">
              Manage and access your computer vision and natural language processing annotation projects.
            </p>
          </div>

          <div className="flex items-center gap-2.5">
            <button
              type="button"
              id="create-new-project-button"
              onClick={onCreateProject}
              className="inline-flex items-center gap-1.5 rounded-xl bg-blue-600 px-4 py-2 text-xs sm:text-sm font-bold text-white shadow-xs hover:bg-blue-700 transition cursor-pointer"
            >
              <Plus className="h-4 w-4" />
              <span>Create Project</span>
            </button>
            <button
              type="button"
              id="refresh-projects-button"
              onClick={() => void loadProjects(true)}
              className="inline-flex items-center gap-1.5 rounded-xl border border-slate-200 bg-white px-3.5 py-2 text-xs sm:text-sm font-bold text-slate-700 hover:bg-slate-50 transition cursor-pointer shadow-2xs"
              title="Refresh project list from backend"
            >
              <RefreshCw className={`h-4 w-4 ${isLoading ? 'animate-spin text-blue-600' : 'text-slate-500'}`} />
              <span className="hidden sm:inline">Refresh</span>
            </button>
          </div>
        </div>

        {/* Filter Controls Bar: Buttons + Dropdown + Search */}
        <div
          id="projects-filter-bar"
          className="flex flex-wrap items-center justify-between gap-3 bg-white p-3.5 rounded-2xl border border-slate-200 shadow-2xs"
        >
          {/* Segmented Filter Buttons (All, Image, Text) */}
          <div className="flex flex-wrap items-center gap-1.5">
            <button
              type="button"
              id="filter-all-projects-btn"
              onClick={() => setFilterModality('all')}
              className={`inline-flex items-center gap-2 px-3.5 py-2 rounded-xl text-xs font-bold transition cursor-pointer ${
                filterModality === 'all'
                  ? 'bg-slate-900 text-white shadow-xs'
                  : 'bg-slate-100/80 text-slate-700 hover:bg-slate-200/80'
              }`}
            >
              <Layers className="w-3.5 h-3.5" />
              <span>All Projects</span>
              <span
                className={`ml-1 rounded-full px-1.5 py-0.2 text-[10px] font-extrabold ${
                  filterModality === 'all' ? 'bg-white/20 text-white' : 'bg-slate-200 text-slate-700'
                }`}
              >
                {totalCount}
              </span>
            </button>

            <button
              type="button"
              id="filter-image-projects-btn"
              onClick={() => setFilterModality('image')}
              className={`inline-flex items-center gap-2 px-3.5 py-2 rounded-xl text-xs font-bold transition cursor-pointer ${
                filterModality === 'image'
                  ? 'bg-blue-600 text-white shadow-xs'
                  : 'bg-blue-50/70 text-blue-800 hover:bg-blue-100/80 border border-blue-100'
              }`}
            >
              <ImageIcon className="w-3.5 h-3.5" />
              <span>Image Projects</span>
              <span
                className={`ml-1 rounded-full px-1.5 py-0.2 text-[10px] font-extrabold ${
                  filterModality === 'image' ? 'bg-white/20 text-white' : 'bg-blue-100 text-blue-800'
                }`}
              >
                {imageCount}
              </span>
            </button>

            <button
              type="button"
              id="filter-text-projects-btn"
              onClick={() => setFilterModality('text')}
              className={`inline-flex items-center gap-2 px-3.5 py-2 rounded-xl text-xs font-bold transition cursor-pointer ${
                filterModality === 'text'
                  ? 'bg-violet-600 text-white shadow-xs'
                  : 'bg-violet-50/70 text-violet-800 hover:bg-violet-100/80 border border-violet-100'
              }`}
            >
              <FileText className="w-3.5 h-3.5" />
              <span>Text Projects</span>
              <span
                className={`ml-1 rounded-full px-1.5 py-0.2 text-[10px] font-extrabold ${
                  filterModality === 'text' ? 'bg-white/20 text-white' : 'bg-violet-100 text-violet-800'
                }`}
              >
                {textCount}
              </span>
            </button>
          </div>

          {/* Right controls: Modality Dropdown & Quick Search */}
          <div className="flex flex-wrap items-center gap-2.5">
            {/* Explicit Dropdown Filter */}
            <div className="relative flex items-center">
              <Filter className="absolute left-3 w-3.5 h-3.5 text-slate-400 pointer-events-none" />
              <select
                id="project-modality-dropdown"
                value={filterModality}
                onChange={(e) => setFilterModality(e.target.value as ModalityFilter)}
                className="pl-8 pr-8 py-2 text-xs font-bold bg-slate-50 hover:bg-slate-100 text-slate-800 border border-slate-200 rounded-xl shadow-2xs hover:border-slate-300 focus:outline-hidden focus:ring-2 focus:ring-blue-500/20 cursor-pointer transition appearance-none"
                aria-label="Filter projects by modality"
              >
                <option value="all">Filter: All Modalities ({totalCount})</option>
                <option value="image">Filter: Image Projects ({imageCount})</option>
                <option value="text">Filter: Text Projects ({textCount})</option>
              </select>
            </div>

            {/* Project Search Input */}
            <div className="relative flex items-center">
              <Search className="absolute left-3 w-3.5 h-3.5 text-slate-400 pointer-events-none" />
              <input
                type="text"
                id="search-projects-input"
                value={searchQuery}
                onChange={(e) => setSearchQuery(e.target.value)}
                placeholder="Search projects..."
                className="pl-8 pr-7 py-2 text-xs bg-slate-50 text-slate-900 placeholder-slate-400 border border-slate-200 rounded-xl shadow-2xs hover:border-slate-300 focus:outline-hidden focus:ring-2 focus:ring-blue-500/20 w-44 sm:w-56 transition"
              />
              {searchQuery && (
                <button
                  type="button"
                  onClick={() => setSearchQuery('')}
                  className="absolute right-2.5 text-slate-400 hover:text-slate-600 cursor-pointer"
                  title="Clear search"
                >
                  <X className="w-3.5 h-3.5" />
                </button>
              )}
            </div>
          </div>
        </div>

        {/* Content Area */}
        {isLoading ? (
          <div className="flex flex-col items-center justify-center gap-3 rounded-2xl border border-slate-200 bg-white py-16 text-center text-sm text-slate-500 shadow-2xs">
            <Loader2 className="h-6 w-6 animate-spin text-blue-600" />
            <span className="font-semibold text-slate-700">Loading annotation projects...</span>
          </div>
        ) : error ? (
          <div className="rounded-2xl border border-red-200 bg-red-50 p-6 text-sm text-red-700 shadow-2xs">
            <div className="font-bold">Error loading projects:</div>
            <p className="mt-1">{error}</p>
            <button
              type="button"
              onClick={() => void loadProjects(true)}
              className="mt-3 rounded-lg bg-red-600 px-3 py-1.5 text-xs font-bold text-white hover:bg-red-700 transition"
            >
              Try Again
            </button>
          </div>
        ) : filteredProjects.length === 0 ? (
          <div className="rounded-2xl border border-dashed border-slate-300 bg-white p-12 text-center text-sm text-slate-500 shadow-2xs space-y-3">
            <div className="mx-auto flex h-12 w-12 items-center justify-center rounded-full bg-slate-100 text-slate-400">
              {filterModality === 'image' ? (
                <ImageIcon className="h-6 w-6 text-blue-500" />
              ) : filterModality === 'text' ? (
                <FileText className="h-6 w-6 text-violet-500" />
              ) : (
                <FolderOpen className="h-6 w-6 text-slate-400" />
              )}
            </div>
            <div>
              <div className="font-bold text-slate-800 text-base">
                No {filterModality === 'image' ? 'Image' : filterModality === 'text' ? 'Text' : ''} projects match your criteria
              </div>
              <p className="text-xs text-slate-500 mt-1">
                {searchQuery
                  ? `No projects matching "${searchQuery}" in ${filterModality} scope.`
                  : `There are currently no ${filterModality} projects available.`}
              </p>
            </div>
            {(filterModality !== 'all' || searchQuery) && (
              <button
                type="button"
                onClick={() => {
                  setFilterModality('all');
                  setSearchQuery('');
                }}
                className="inline-flex items-center gap-1.5 rounded-xl border border-slate-200 bg-slate-50 px-3.5 py-1.5 text-xs font-bold text-slate-700 hover:bg-slate-100 transition cursor-pointer"
              >
                Reset Filter
              </button>
            )}
          </div>
        ) : (
          <div className="grid grid-cols-1 gap-4 md:grid-cols-2 xl:grid-cols-3">
            {filteredProjects.map((project) => {
              const textProject = isTextProject(project);
              const itemCount = project.asset_count ?? project.item_count ?? 0;
              const statusRaw = String(project.status || 'ready').toLowerCase();
              const isCompleted = statusRaw.includes('complete') || statusRaw.includes('approved');

              return (
                <article
                  key={project.id}
                  onClick={() => onSelectProject?.(project)}
                  className={`group relative cursor-pointer rounded-2xl border p-5 shadow-2xs transition-all duration-150 hover:-translate-y-0.5 hover:shadow-md ${
                    textProject
                      ? 'border-slate-200/90 bg-white hover:border-violet-300'
                      : 'border-slate-200/90 bg-white hover:border-blue-300'
                  }`}
                >
                  {/* Top Bar with Icon, Title, and Delete Button */}
                  <div className="flex items-start justify-between gap-3">
                    <div className="flex min-w-0 items-start gap-3">
                      <div
                        className={`rounded-xl p-2.5 transition-colors ${
                          textProject
                            ? 'bg-violet-50 text-violet-600 group-hover:bg-violet-100'
                            : 'bg-blue-50 text-blue-600 group-hover:bg-blue-100'
                        }`}
                      >
                        {textProject ? <FileText className="h-5 w-5" /> : <ImageIcon className="h-5 w-5" />}
                      </div>
                      <div className="min-w-0">
                        <div className="flex items-center gap-2">
                          <h2
                            className={`truncate font-bold text-slate-900 transition-colors ${
                              textProject ? 'group-hover:text-violet-600' : 'group-hover:text-blue-600'
                            }`}
                            title={project.name}
                          >
                            {project.name}
                          </h2>
                        </div>
                        <p className="mt-0.5 text-xs text-slate-500 truncate">{projectTypeLabel(project)}</p>
                      </div>
                    </div>

                    <button
                      type="button"
                      aria-label={`Delete ${project.name}`}
                      title="Delete project"
                      disabled={deletingProjectId === project.id}
                      onClick={(e) => {
                        e.stopPropagation();
                        void handleDelete(project);
                      }}
                      className="rounded-lg p-2 text-slate-400 hover:text-red-600 hover:bg-red-50 transition-colors cursor-pointer disabled:cursor-not-allowed disabled:opacity-50"
                    >
                      {deletingProjectId === project.id ? (
                        <Loader2 className="h-4 w-4 animate-spin text-red-600" />
                      ) : (
                        <Trash2 className="h-4 w-4" />
                      )}
                    </button>
                  </div>

                  {/* Badges Bar: Modality Tag & Status */}
                  <div className="mt-4 flex items-center justify-between border-t border-slate-100 pt-3">
                    <span
                      className={`inline-flex items-center gap-1.5 px-2.5 py-0.5 rounded-full text-[10px] font-bold border ${
                        textProject
                          ? 'bg-violet-50 text-violet-700 border-violet-200'
                          : 'bg-blue-50 text-blue-700 border-blue-200'
                      }`}
                    >
                      {textProject ? <FileText className="w-3 h-3" /> : <ImageIcon className="w-3 h-3" />}
                      <span>{textProject ? 'Text / NLP' : 'Image / Vision'}</span>
                    </span>

                    <span
                      className={`inline-flex items-center gap-1 px-2.5 py-0.5 rounded-full text-[10px] font-bold border ${
                        isCompleted
                          ? 'bg-emerald-50 text-emerald-700 border-emerald-200'
                          : 'bg-slate-100 text-slate-700 border-slate-200'
                      }`}
                    >
                      <span
                        className={`w-1.5 h-1.5 rounded-full ${isCompleted ? 'bg-emerald-500' : 'bg-slate-400'}`}
                      />
                      <span className="capitalize">{project.status || 'Ready'}</span>
                    </span>
                  </div>

                  {/* Document / Asset Count Footer */}
                  <div className="mt-3 grid grid-cols-2 gap-3 text-xs text-slate-500 bg-slate-50/70 p-2.5 rounded-xl border border-slate-100">
                    <div>
                      <span className="block font-black text-slate-900 text-sm">
                        {itemCount.toLocaleString()}
                      </span>
                      <span className="text-[11px] font-medium text-slate-500">
                        {textProject ? 'Documents' : 'Assets'}
                      </span>
                    </div>
                    <div>
                      <span className="block font-bold text-slate-900 text-sm truncate">
                        {project.domain_use_case || (textProject ? 'NLP Analysis' : 'Vision')}
                      </span>
                      <span className="text-[11px] font-medium text-slate-500">Domain</span>
                    </div>
                  </div>
                </article>
              );
            })}
          </div>
        )}
      </main>
    </div>
  );
};
