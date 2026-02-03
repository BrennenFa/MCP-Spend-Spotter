'use client';

import { useTheme } from '@/contexts/ThemeContext';
import { useState } from 'react';

export default function Header() {
  const { theme, toggleTheme } = useTheme();
  const [showDataSources, setShowDataSources] = useState(false);

  const dataSources = [
    {
      title: "Governor's Budget Recommendations",
      url: "https://www.osbm.nc.gov/budget/governors-budget-recommendations"
    },
    {
      title: "NC Open Budget",
      url: "https://www.nc.gov/government/open-budget"
    }
  ];

  return (
    <header className="fixed top-0 left-0 right-0 bg-white dark:bg-black border-b border-gray-200 dark:border-zinc-800 z-20">
      <div className="max-w-[700px] mx-auto px-6 py-3 flex items-center justify-between">
        <h1 className="text-xl font-medium text-gray-900 dark:text-gray-100">
          Spend Tracker
        </h1>

        <div className="flex items-center gap-2">
          <button
            onClick={() => setShowDataSources(!showDataSources)}
            className="p-2.5 rounded-full bg-gray-100 dark:bg-zinc-900 hover:bg-gray-200 dark:hover:bg-zinc-800 transition-all border border-gray-200 dark:border-zinc-800"
            aria-label="Data sources"
          >
            <svg className="w-5 h-5 text-gray-600 dark:text-gray-400" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M13 16h-1v-4h-1m1-4h.01M21 12a9 9 0 11-18 0 9 9 0 0118 0z" />
            </svg>
          </button>

          <button
            onClick={toggleTheme}
            className="p-2.5 rounded-full bg-gray-100 dark:bg-zinc-900 hover:bg-gray-200 dark:hover:bg-zinc-800 transition-all border border-gray-200 dark:border-zinc-800"
            aria-label="Toggle theme"
          >
            {theme === 'dark' ? (
              <svg className="w-5 h-5 text-yellow-400" fill="currentColor" viewBox="0 0 20 20">
                <path fillRule="evenodd" d="M10 2a1 1 0 011 1v1a1 1 0 11-2 0V3a1 1 0 011-1zm4 8a4 4 0 11-8 0 4 4 0 018 0zm-.464 4.95l.707.707a1 1 0 001.414-1.414l-.707-.707a1 1 0 00-1.414 1.414zm2.12-10.607a1 1 0 010 1.414l-.706.707a1 1 0 11-1.414-1.414l.707-.707a1 1 0 011.414 0zM17 11a1 1 0 100-2h-1a1 1 0 100 2h1zm-7 4a1 1 0 011 1v1a1 1 0 11-2 0v-1a1 1 0 011-1zM5.05 6.464A1 1 0 106.465 5.05l-.708-.707a1 1 0 00-1.414 1.414l.707.707zm1.414 8.486l-.707.707a1 1 0 01-1.414-1.414l.707-.707a1 1 0 011.414 1.414zM4 11a1 1 0 100-2H3a1 1 0 000 2h1z" clipRule="evenodd" />
              </svg>
            ) : (
              <svg className="w-5 h-5 text-gray-600" fill="currentColor" viewBox="0 0 20 20">
                <path d="M17.293 13.293A8 8 0 016.707 2.707a8.001 8.001 0 1010.586 10.586z" />
              </svg>
            )}
          </button>
        </div>
      </div>

      {showDataSources && (
        <div className="absolute top-14 right-6 bg-white dark:bg-zinc-900 border border-gray-200 dark:border-zinc-800 rounded-lg shadow-lg p-4 min-w-[300px] z-30">
          <div className="flex items-center justify-between mb-3">
            <h3 className="font-medium text-gray-900 dark:text-gray-100">Data Sources</h3>
            <button
              onClick={() => setShowDataSources(false)}
              className="text-gray-400 hover:text-gray-600 dark:hover:text-gray-300"
            >
              <svg className="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M6 18L18 6M6 6l12 12" />
              </svg>
            </button>
          </div>
          <div className="space-y-3">
            {dataSources.map((source, index) => (
              <a
                key={index}
                href={source.url}
                target="_blank"
                rel="noopener noreferrer"
                className="block p-3 rounded-md bg-gray-50 dark:bg-zinc-800 hover:bg-gray-100 dark:hover:bg-zinc-700 transition-colors"
              >
                <div className="text-sm font-medium text-gray-900 dark:text-gray-100 mb-1">
                  {source.title}
                </div>
                <div className="text-xs text-gray-500 dark:text-gray-400 break-all">
                  {source.url}
                </div>
              </a>
            ))}
          </div>
        </div>
      )}
    </header>
  );
}
