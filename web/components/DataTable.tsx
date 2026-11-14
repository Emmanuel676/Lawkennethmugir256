"use client";

import { useMemo, useState, type ReactNode } from "react";

export interface Column<T> {
  key: string;
  header: ReactNode;
  /** Plain-text name for the sort button's accessible label when the header is not plain text. */
  name?: string;
  cell: (row: T) => ReactNode;
  /** Client-side sort value. Leave out (and leave out of serverSortable) for a column that cannot be sorted. */
  sortValue?: (row: T) => number | string;
  align?: "left" | "right";
  className?: string;
}

export interface ServerSort {
  key: string;
  order: "asc" | "desc";
  sortable: string[];
  onSort: (key: string, order: "asc" | "desc") => void;
}

/**
 * A table with a sticky header and sortable columns. Wide tables scroll inside their own box, never the page.
 * Sorting is client-side (sortValue) unless `server` is given, in which case the API sorts.
 */
export function DataTable<T>({ columns, rows, rowKey, caption, server, maxHeight = "70vh", onRowClick, rowLabel,
                               initialSort }: {
  columns: Column<T>[]; rows: T[]; rowKey: (row: T) => string; caption: string; server?: ServerSort;
  maxHeight?: string; onRowClick?: (row: T) => void; rowLabel?: (row: T) => string;
  initialSort?: { key: string; order: "asc" | "desc" };
}) {
  const [local, setLocal] = useState<{ key: string; order: "asc" | "desc" } | undefined>(initialSort);

  const sorted = useMemo(() => {
    if (server || !local) return rows;
    const column = columns.find((c) => c.key === local.key);
    if (!column?.sortValue) return rows;
    const value = column.sortValue;
    const copy = [...rows];
    copy.sort((a, b) => {
      const x = value(a), y = value(b);
      const result = typeof x === "number" && typeof y === "number" ? x - y : String(x).localeCompare(String(y));
      return local.order === "asc" ? result : -result;
    });
    return copy;
  }, [rows, columns, local, server]);

  const active = server ? { key: server.key, order: server.order } : local;

  function canSort(column: Column<T>): boolean {
    return server ? server.sortable.includes(column.key) : Boolean(column.sortValue);
  }

  function sortBy(column: Column<T>) {
    const order: "asc" | "desc" = active?.key === column.key && active.order === "desc" ? "asc" : "desc";
    if (server) server.onSort(column.key, order);
    else setLocal({ key: column.key, order });
  }

  return (
    <div className="relative overflow-auto rounded-xl border border-line" style={{ maxHeight }} tabIndex={0}
         role="region" aria-label={caption}>
      <table className="w-full border-collapse text-sm">
        <caption className="sr-only">{caption}</caption>
        <thead className="sticky top-0 z-10 bg-surface-2">
          <tr>
            {columns.map((column) => {
              const isSorted = active?.key === column.key;
              const align = column.align === "right" ? "text-right" : "text-left";
              return (
                <th key={column.key} scope="col"
                    aria-sort={isSorted ? (active!.order === "asc" ? "ascending" : "descending") : undefined}
                    className={`whitespace-nowrap border-b border-line px-3 py-2.5 text-xs font-semibold uppercase tracking-wide text-muted ${align} ${column.className ?? ""}`}>
                  {canSort(column) ? (
                    <button type="button" onClick={() => sortBy(column)}
                            aria-label={`Sort by ${column.name ?? (typeof column.header === "string" ? column.header : column.key)}`}
                            className={`inline-flex items-center gap-1 uppercase tracking-wide hover:text-ink ${isSorted ? "text-ink" : ""} ${column.align === "right" ? "flex-row-reverse" : ""}`}>
                      {column.header}
                      <span aria-hidden="true" className="text-[10px]">
                        {isSorted ? (active!.order === "asc" ? "▲" : "▼") : "↕"}
                      </span>
                    </button>
                  ) : column.header}
                </th>
              );
            })}
          </tr>
        </thead>
        <tbody>
          {sorted.map((row) => (
            <tr key={rowKey(row)}
                className={`border-b border-line/70 last:border-0 ${onRowClick ? "cursor-pointer hover:bg-accent-soft/60" : "hover:bg-surface-2/60"}`}
                onClick={onRowClick ? () => onRowClick(row) : undefined}
                aria-label={rowLabel?.(row)}>
              {columns.map((column) => (
                <td key={column.key}
                    className={`whitespace-nowrap px-3 py-2.5 text-ink-2 ${column.align === "right" ? "tabular text-right" : ""} ${column.className ?? ""}`}>
                  {column.cell(row)}
                </td>
              ))}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
