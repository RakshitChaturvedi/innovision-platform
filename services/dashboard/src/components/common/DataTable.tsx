import type { ReactNode } from "react";
import { LoadingState } from "./LoadingState";
import { EmptyState } from "./EmptyState";

export interface Column<T> {
  key: string;
  header: string;
  width?: string;
  render?: (row: T, index: number) => ReactNode;
}

interface DataTableProps<T> {
  columns: Column<T>[];
  data: T[];
  keyExtractor: (row: T, index: number) => string;
  isLoading?: boolean;
  emptyMessage?: string;
  onRowClick?: (row: T) => void;
  className?: string;
}

export function DataTable<T>({
  columns,
  data,
  keyExtractor,
  isLoading = false,
  emptyMessage = "No records found.",
  onRowClick,
  className = "",
}: DataTableProps<T>) {
  if (isLoading) {
    return <LoadingState message="Loading data..." />;
  }

  if (data.length === 0) {
    return <EmptyState message={emptyMessage} />;
  }

  return (
    <div
      className={`data-table-container ${className}`}
      style={{
        overflowX: "auto",
        borderRadius: "10px",
        border: "1px solid var(--border, #292d36)",
        background: "var(--surface, #15171e)",
      }}
    >
      <table
        className="data-table"
        style={{
          width: "100%",
          borderCollapse: "collapse",
          fontSize: "13px",
          textAlign: "left",
        }}
      >
        <thead>
          <tr
            style={{
              borderBottom: "1px solid var(--border, #292d36)",
              backgroundColor: "var(--surface-raised, #191c24)",
            }}
          >
            {columns.map((col) => (
              <th
                key={col.key}
                style={{
                  padding: "12px 16px",
                  fontWeight: 600,
                  color: "var(--text-secondary, #a2a8b5)",
                  width: col.width,
                  whiteSpace: "nowrap",
                }}
              >
                {col.header}
              </th>
            ))}
          </tr>
        </thead>
        <tbody>
          {data.map((row, index) => (
            <tr
              key={keyExtractor(row, index)}
              onClick={() => onRowClick?.(row)}
              style={{
                borderBottom: "1px solid var(--border, #292d36)",
                cursor: onRowClick ? "pointer" : "default",
                transition: "background-color 0.1s",
              }}
              className={onRowClick ? "clickable-row" : ""}
            >
              {columns.map((col) => {
                const cellValue = (row as Record<string, unknown>)[col.key];
                return (
                  <td
                    key={col.key}
                    style={{
                      padding: "12px 16px",
                      color: "var(--text-primary, #f1f3f5)",
                      verticalAlign: "middle",
                    }}
                  >
                    {col.render
                      ? col.render(row, index)
                      : (cellValue != null ? String(cellValue) : "—")}
                  </td>
                );
              })}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
export default DataTable;
