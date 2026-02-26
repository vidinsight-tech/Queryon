"use client";
import { type ReactNode } from "react";

interface Props {
  icon: ReactNode;
  title: string;
  description: string;
  enabled: boolean;
  alwaysOn?: boolean;
  onToggle?: (enabled: boolean) => void;
  children?: ReactNode;
}

export function ModeCard({
  icon,
  title,
  description,
  enabled,
  alwaysOn,
  onToggle,
  children,
}: Props) {
  return (
    <div className={`border rounded-lg transition-colors ${enabled ? "border-indigo-300 bg-indigo-50/30" : "border-gray-200 bg-white"}`}>
      <div className="flex items-center gap-3 px-4 py-3">
        <div className={`p-2 rounded-md ${enabled ? "bg-indigo-100 text-indigo-600" : "bg-gray-100 text-gray-500"}`}>
          {icon}
        </div>
        <div className="flex-1 min-w-0">
          <p className="text-sm font-semibold text-gray-900">{title}</p>
          <p className="text-xs text-gray-500 truncate">{description}</p>
        </div>
        {alwaysOn ? (
          <span className="text-xs font-medium text-indigo-600 bg-indigo-100 px-2 py-0.5 rounded-full">
            Her zaman açık
          </span>
        ) : (
          <button
            type="button"
            onClick={() => onToggle?.(!enabled)}
            className={`relative inline-flex h-5 w-9 flex-shrink-0 cursor-pointer rounded-full border-2 border-transparent transition-colors focus:outline-none ${
              enabled ? "bg-indigo-600" : "bg-gray-200"
            }`}
            role="switch"
            aria-checked={enabled}
          >
            <span
              className={`inline-block h-4 w-4 transform rounded-full bg-white shadow transition-transform ${
                enabled ? "translate-x-4" : "translate-x-0"
              }`}
            />
          </button>
        )}
      </div>
      {enabled && children && (
        <div className="px-4 pb-4 border-t border-indigo-100 pt-3">
          {children}
        </div>
      )}
    </div>
  );
}
