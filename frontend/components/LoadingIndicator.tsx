export default function LoadingIndicator() {
  return (
    <div className="mb-8 flex justify-start">
      <div className="max-w-[85%] w-full">
        {/* Role label */}
        {/* <div className="flex items-center gap-2 mb-2 px-1">
          <div className="w-6 h-6 rounded-full flex items-center justify-center text-xs font-semibold bg-gradient-to-br from-purple-500 to-blue-600 text-white">
            AI
          </div>
          <span className="text-sm font-medium text-gray-700 dark:text-gray-300">
            NC Spend Tracker
          </span>
        </div> */}

        {/* Loading content */}
        <div className="rounded-2xl bg-gray-50 dark:bg-gray-800/50 border border-gray-100 dark:border-gray-700/50 px-5 py-4">
          <div className="flex items-center gap-3">
            <div className="flex gap-1">
              <div className="w-2 h-2 bg-blue-500 dark:bg-blue-400 rounded-full animate-bounce" style={{ animationDelay: '0ms' }} />
              <div className="w-2 h-2 bg-blue-500 dark:bg-blue-400 rounded-full animate-bounce" style={{ animationDelay: '150ms' }} />
              <div className="w-2 h-2 bg-blue-500 dark:bg-blue-400 rounded-full animate-bounce" style={{ animationDelay: '300ms' }} />
            </div>
            <span className="text-sm text-gray-600 dark:text-gray-400">Analyzing your query...</span>
          </div>
        </div>
      </div>
    </div>
  );
}
