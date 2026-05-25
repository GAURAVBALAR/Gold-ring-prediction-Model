import React, { useState } from 'react';
import { Calculator, History, Settings as SettingsIcon } from 'lucide-react';
import PredictionForm from './components/PredictionForm';
import HistoryTable from './components/HistoryTable';
import AdminPanel from './components/AdminPanel';

const App: React.FC = () => {
  const [activeTab, setActiveTab] = useState<'predict' | 'history' | 'admin'>('predict');

  return (
    <div className="min-h-screen bg-[#f9fafb] text-[#111827] font-sans">
      {/* Navigation */}
      <nav className="bg-white border-b border-gray-200 sticky top-0 z-10">
        <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8">
          <div className="flex justify-between h-16">
            <div className="flex items-center">
              <Calculator className="h-8 w-8 text-accent mr-3" />
              <span className="text-xl font-bold tracking-tight">GoldWeight AI</span>
            </div>
            <div className="flex items-center space-x-8">
              <button
                onClick={() => setActiveTab('predict')}
                className={`flex items-center px-3 py-2 text-sm font-medium transition-colors ${
                  activeTab === 'predict' ? 'text-accent border-b-2 border-accent' : 'text-gray-500 hover:text-gray-700'
                }`}
              >
                <Calculator className="h-4 w-4 mr-2" />
                Predict
              </button>
              <button
                onClick={() => setActiveTab('history')}
                className={`flex items-center px-3 py-2 text-sm font-medium transition-colors ${
                  activeTab === 'history' ? 'text-accent border-b-2 border-accent' : 'text-gray-500 hover:text-gray-700'
                }`}
              >
                <History className="h-4 w-4 mr-2" />
                History
              </button>
              <button
                onClick={() => setActiveTab('admin')}
                className={`flex items-center px-3 py-2 text-sm font-medium transition-colors ${
                  activeTab === 'admin' ? 'text-accent border-b-2 border-accent' : 'text-gray-500 hover:text-gray-700'
                }`}
              >
                <SettingsIcon className="h-4 w-4 mr-2" />
                Admin
              </button>
            </div>
          </div>
        </div>
      </nav>

      {/* Main Content */}
      <main className="max-w-7xl mx-auto py-8 px-4 sm:px-6 lg:px-8">
        <div className="animate-fadeInUp">
          {activeTab === 'predict' ? (
            <div className="grid grid-cols-1 lg:grid-cols-2 gap-8">
              <div className="bg-white rounded-2xl shadow-sm border border-gray-200 p-8">
                <h2 className="text-2xl font-bold mb-6">Calculate Gold Weight</h2>
                <PredictionForm />
              </div>
              <div className="space-y-6">
                <div className="bg-blue-50 border border-blue-100 rounded-2xl p-6">
                  <h3 className="text-lg font-semibold text-blue-900 mb-2">How it works</h3>
                  <p className="text-blue-700 text-sm leading-relaxed">
                    Upload a ring image and provide manufacturing parameters. Our AI analyzes the visual design and geometric features to estimate the required gold weight with high precision.
                  </p>
                </div>
                <div className="bg-white rounded-2xl shadow-sm border border-gray-200 p-8">
                  <h3 className="text-lg font-semibold mb-4">Latest Results</h3>
                  <p className="text-gray-500 text-sm italic">Previous predictions will appear here after calculation.</p>
                </div>
              </div>
            </div>
          ) : activeTab === 'history' ? (
            <div className="bg-white rounded-2xl shadow-sm border border-gray-200 p-8">
              <h2 className="text-2xl font-bold mb-6">Prediction History</h2>
              <HistoryTable />
            </div>
          ) : (
            <div className="bg-white rounded-2xl shadow-sm border border-gray-200 p-8">
              <h2 className="text-2xl font-bold mb-6">System Settings</h2>
              <AdminPanel />
            </div>
          )}
        </div>
      </main>

      <footer className="mt-auto py-8 border-t border-gray-200 bg-white">
        <div className="max-w-7xl mx-auto px-4 text-center text-gray-400 text-sm">
          &copy; {new Date().getFullYear()} Gold Weight Prediction System — Phase 1 Foundation
        </div>
      </footer>
    </div>
  );
};

export default App;
