'use client';

import { useState } from 'react';
import TokenManager from './components/TokenManager';
import InjectionQueue from './components/InjectionQueue';

// ---------------------------------------------------------------------------
// Types
// ---------------------------------------------------------------------------

type SafetyTab = 'tokens' | 'injection';

// ---------------------------------------------------------------------------
// Page
// ---------------------------------------------------------------------------

export default function AdminSafetyPage() {
  const [activeTab, setActiveTab] = useState<SafetyTab>('tokens');

  return (
    <div>
      <div className="mb-6 flex items-center justify-between">
        <div>
          <h2 className="font-display text-2xl text-gray-900">Trust & Safety</h2>
          <p className="font-mono text-sm text-gray-500">
            Token management and injection detection review
          </p>
        </div>
      </div>

      {/* Tab navigation */}
      <div className="mb-6 flex gap-4 border-b border-warm-border">
        <button
          onClick={() => setActiveTab('tokens')}
          className={`border-b-2 pb-2 font-mono text-sm transition-colors ${
            activeTab === 'tokens'
              ? 'border-terracotta text-terracotta'
              : 'border-transparent text-gray-500 hover:text-gray-700'
          }`}
        >
          Token Management
        </button>
        <button
          onClick={() => setActiveTab('injection')}
          className={`border-b-2 pb-2 font-mono text-sm transition-colors ${
            activeTab === 'injection'
              ? 'border-terracotta text-terracotta'
              : 'border-transparent text-gray-500 hover:text-gray-700'
          }`}
        >
          Injection Queue
        </button>
      </div>

      {/* Active panel */}
      {activeTab === 'tokens' && <TokenManager />}
      {activeTab === 'injection' && <InjectionQueue />}
    </div>
  );
}
