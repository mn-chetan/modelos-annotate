import React from 'react';
import { AnnotationItem } from '../../types';
import { Plus, Eye, EyeOff, Edit2, CheckCircle2, AlertCircle } from 'lucide-react';

interface AnnotationsTableProps {
  annotations: AnnotationItem[];
  selectedAnnotationId: number | null;
  onSelectAnnotation: (id: number) => void;
  onToggleVisibility: (id: number) => void;
  onAddAnnotation: () => void;
  onEditAnnotation: (id: number) => void;
}

export const AnnotationsTable: React.FC<AnnotationsTableProps> = ({
  annotations,
  selectedAnnotationId,
  onSelectAnnotation,
  onToggleVisibility,
  onAddAnnotation,
  onEditAnnotation,
}) => {
  return (
    <div
      id="annotations-table-container"
      className="rounded-xl border border-slate-200 bg-white p-5 shadow-2xs"
    >
      {/* Header */}
      <div className="flex items-center justify-between pb-4 border-b border-slate-100">
        <div className="flex items-center gap-2">
          <h3 className="text-base font-bold text-slate-900">Annotations</h3>
          <span className="rounded-full bg-slate-100 px-2 py-0.5 text-xs font-semibold text-slate-600">
            {annotations.length}
          </span>
        </div>

        <button
          id="btn-add-annotation"
          onClick={onAddAnnotation}
          className="flex items-center gap-1.5 rounded-lg bg-blue-600 px-3.5 py-1.5 text-xs font-semibold text-white hover:bg-blue-700 shadow-2xs transition cursor-pointer"
        >
          <Plus className="h-3.5 w-3.5" />
          <span>Add Annotation</span>
        </button>
      </div>

      {/* Table */}
      <div className="overflow-x-auto mt-3">
        <table className="w-full text-left border-collapse text-xs">
          <thead>
            <tr className="border-b border-slate-100 text-[11px] font-semibold text-slate-400 uppercase tracking-wider">
              <th className="py-2.5 px-3 w-10">#</th>
              <th className="py-2.5 px-3">Label</th>
              <th className="py-2.5 px-3">Type</th>
              <th className="py-2.5 px-3">Confidence</th>
              <th className="py-2.5 px-3">Status</th>
              <th className="py-2.5 px-3 text-right">Actions</th>
            </tr>
          </thead>
          <tbody className="divide-y divide-slate-100">
            {annotations.map((item) => {
              const isSelected = selectedAnnotationId === item.id;
              const isApproved = item.status === 'Approved';

              return (
                <tr
                  key={item.id}
                  id={`annotation-row-${item.id}`}
                  onClick={() => onSelectAnnotation(item.id)}
                  className={`group cursor-pointer transition-colors ${
                    isSelected ? 'bg-blue-50/80 font-medium' : 'hover:bg-slate-50/80'
                  }`}
                >
                  {/* # */}
                  <td className="py-3 px-3 text-slate-500 font-medium">{item.id}</td>

                  {/* Label with colored dot */}
                  <td className="py-3 px-3 font-semibold text-slate-800">
                    <div className="flex items-center gap-2">
                      <span
                        className="h-2.5 w-2.5 rounded-full shrink-0"
                        style={{ backgroundColor: item.color }}
                      />
                      <span>{item.label}</span>
                    </div>
                  </td>

                  {/* Type */}
                  <td className="py-3 px-3 text-slate-600">{item.type}</td>

                  {/* Confidence */}
                  <td className="py-3 px-3 text-slate-700 font-semibold">
                    {item.confidence.toFixed(2)}
                  </td>

                  {/* Status */}
                  <td className="py-3 px-3">
                    {isApproved ? (
                      <span className="inline-flex items-center gap-1 font-semibold text-emerald-600">
                        <CheckCircle2 className="h-3.5 w-3.5 stroke-[2.5]" />
                        <span>Approved</span>
                      </span>
                    ) : (
                      <span className="inline-flex items-center gap-1 rounded-md bg-rose-50 px-2 py-0.5 text-[11px] font-semibold text-rose-600 border border-rose-100">
                        <AlertCircle className="h-3 w-3 stroke-[2.5]" />
                        <span>Needs Review</span>
                      </span>
                    )}
                  </td>

                  {/* Actions */}
                  <td className="py-3 px-3 text-right">
                    <div className="inline-flex items-center gap-2">
                      <button
                        id={`toggle-vis-btn-${item.id}`}
                        onClick={(e) => {
                          e.stopPropagation();
                          onToggleVisibility(item.id);
                        }}
                        className={`p-1 rounded text-slate-400 hover:text-slate-700 hover:bg-slate-100 transition cursor-pointer ${
                          !item.visible ? 'opacity-40' : ''
                        }`}
                        title={item.visible ? 'Hide bounding box' : 'Show bounding box'}
                      >
                        {item.visible ? (
                          <Eye className="h-3.5 w-3.5" />
                        ) : (
                          <EyeOff className="h-3.5 w-3.5 text-slate-400" />
                        )}
                      </button>

                      <button
                        id={`edit-ann-btn-${item.id}`}
                        onClick={(e) => {
                          e.stopPropagation();
                          onEditAnnotation(item.id);
                        }}
                        className="p-1 rounded text-slate-400 hover:text-blue-600 hover:bg-blue-50 transition cursor-pointer"
                        title="Edit annotation details"
                      >
                        <Edit2 className="h-3.5 w-3.5" />
                      </button>
                    </div>
                  </td>
                </tr>
              );
            })}
          </tbody>
        </table>
      </div>
    </div>
  );
};
