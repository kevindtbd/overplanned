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
          <h2 className="font-display text-2xl text-ink-100">Trust & Safety</h2>
          <p className="font-dm-mono text-sm text-ink-500">
            Token management and injection detection review
          </p>
        </div>
      </div>

      {/* Tab navigation */}
      <div className="mb-6 flex gap-4 border-b border-ink-700">
        <button
          onClick={() => setActiveTab('tokens')}
          className={`border-b-2 pb-2 font-dm-mono text-sm transition-colors ${
            activeTab === 'tokens'
              ? 'border-accent text-accent'
              : 'border-transparent text-ink-500 hover:text-ink-300'
          }`}
        >
          Token Management
        </button>
        <button
          onClick={() => setActiveTab('injection')}
          className={`border-b-2 pb-2 font-dm-mono text-sm transition-colors ${
            activeTab === 'injection'
              ? 'border-accent text-accent'
              : 'border-transparent text-ink-500 hover:text-ink-300'
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
