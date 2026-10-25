"use client";

import { useState, useRef, useEffect } from "react";
import { cn } from "@/src/utils/cn";
import { Search, X } from "lucide-react";

type Option = {
  id: string;
  label: string;
};

type Props = {
  options: Option[];
  value: string[];
  onChange: (value: string[]) => void;
};

export default function MultiSelectDropdown({
  options,
  value,
  onChange,
}: Props) {
  const [open, setOpen] = useState(false);
  const [search, setSearch] = useState("");
  const containerRef = useRef<HTMLDivElement>(null);

  // Close the dropdown on an outside click.
  useEffect(() => {
    function handleClickOutside(e: MouseEvent) {
      if (
        containerRef.current &&
        !containerRef.current.contains(e.target as Node)
      ) {
        setOpen(false);
      }
    }

    document.addEventListener("mousedown", handleClickOutside);
    return () => document.removeEventListener("mousedown", handleClickOutside);
  }, []);

  const filtered = options.filter((opt) =>
    opt.label.toLowerCase().includes(search.toLowerCase())
  );

  const toggleOption = (id: string) => {
    if (value.includes(id)) {
      onChange(value.filter((v) => v !== id));
    } else {
      onChange([...value, id]);
    }
  };

  return (
    <div ref={containerRef} className="relative w-full">
      {/* Trigger button. No placeholder text is shown when nothing is
          selected — this control has no i18n key of its own (it is a
          generic form primitive, not page copy), and the design's rule
          against filling in content we are not authorised to write applies
          here the same as it does to the result table: an empty selection
          reads as "nothing chosen yet", which is honest. */}
      <button
        type="button"
        onClick={() => setOpen((prev) => !prev)}
        aria-label="Properties"
        className={cn(
          "flex min-h-[36px] w-full flex-wrap items-center gap-[var(--space-2)] border border-divider bg-white px-[var(--space-2)] py-1",
          open && "border-accent-600",
        )}
      >
        {value.map((id) => {
          const label = options.find((o) => o.id === id)?.label;
          return (
            // Neutral, not accent: the accent ramp is reserved for the
            // design's restricted uses (primary button fill,
            // active nav item, pulse dot, positive log2FC, kicker/step
            // numerals, the must-fix tag) — a selected-property chip is not
            // among them, so this reuses `.tag-neutral`'s palette instead of
            // introducing a new solid accent fill.
            <span
              key={id}
              className="tag tag-neutral flex items-center gap-1"
            >
              {label}
              <span
                onClick={(e) => {
                  e.stopPropagation();
                  toggleOption(id);
                }}
                className="cursor-pointer"
              >
                <X className="h-3 w-3" strokeWidth={2} />
              </span>
            </span>
          );
        })}

        <span className="ml-auto text-[11px] text-neutral-500">▼</span>
      </button>

      {open && (
        <div className="absolute z-[100] mt-1 w-full border border-divider bg-white p-[var(--space-3)]">
          <div className="relative mb-[var(--space-2)]">
            <Search
              className="absolute left-2 top-2 h-4 w-4 text-neutral-500"
              strokeWidth={2}
            />
            <input
              type="text"
              aria-label="Search properties"
              value={search}
              onChange={(e) => setSearch(e.target.value)}
              className="input w-full pl-8 text-[13px]"
            />
          </div>

          <div className="max-h-52 space-y-1 overflow-y-auto">
            {filtered.map((option) => (
              <label
                key={option.id}
                className="flex cursor-pointer items-center gap-[var(--space-2)] px-[var(--space-2)] py-1 hover:bg-neutral-100"
              >
                <input
                  type="checkbox"
                  checked={value.includes(option.id)}
                  onChange={() => toggleOption(option.id)}
                />
                <span className="text-[13px]">{option.label}</span>
              </label>
            ))}
          </div>
        </div>
      )}
    </div>
  );
}
