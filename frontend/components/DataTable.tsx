interface DataTableProps {
  data: any[]
  maxRows?: number
}

export default function DataTable({ data, maxRows = 10 }: DataTableProps) {
  if (!data || data.length === 0) {
    return null
  }

  // Get column names from first row
  const columns = Object.keys(data[0])

  // Limit rows if specified
  const displayData = maxRows ? data.slice(0, maxRows) : data
  const hasMore = data.length > displayData.length

  // Format cell value
  const formatValue = (value: any): string => {
    if (value === null || value === undefined) {
      return '-'
    }
    if (typeof value === 'number') {
      // Format large numbers with commas
      if (value > 1000) {
        return value.toLocaleString()
      }
      return value.toString()
    }
    return String(value)
  }

  return (
    <div className="mt-4 overflow-x-auto">
      <table className="min-w-full divide-y divide-gray-300 dark:divide-gray-700 border border-gray-300 dark:border-gray-700 rounded-lg">
        <thead className="bg-gray-100 dark:bg-gray-800">
          <tr>
            {columns.map((col) => (
              <th
                key={col}
                className="px-4 py-3 text-left text-xs font-semibold text-gray-700 dark:text-gray-300 uppercase tracking-wider"
              >
                {col.replace(/_/g, ' ')}
              </th>
            ))}
          </tr>
        </thead>
        <tbody className="bg-white dark:bg-gray-900 divide-y divide-gray-200 dark:divide-gray-800">
          {displayData.map((row, idx) => (
            <tr key={idx} className="hover:bg-gray-50 dark:hover:bg-gray-800">
              {columns.map((col) => (
                <td
                  key={col}
                  className="px-4 py-3 text-sm text-gray-900 dark:text-gray-100 whitespace-nowrap"
                >
                  {formatValue(row[col])}
                </td>
              ))}
            </tr>
          ))}
        </tbody>
      </table>

      {hasMore && (
        <p className="text-xs text-gray-500 dark:text-gray-400 mt-2 text-center">
          Showing {displayData.length} of {data.length} rows
        </p>
      )}
    </div>
  )
}
