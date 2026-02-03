interface GraphDisplayProps {
  base64Image: string
  alt?: string
}

export default function GraphDisplay({ base64Image, alt }: GraphDisplayProps) {
  return (
    <div className="my-4 rounded-lg overflow-hidden border border-gray-300 dark:border-gray-700">
      <img
        src={`data:image/png;base64,${base64Image}`}
        alt={alt || "Query result visualization"}
        className="w-full"
      />
    </div>
  )
}
