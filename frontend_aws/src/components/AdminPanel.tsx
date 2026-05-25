import { API_BASE_URL } from '../config';
import React, { useState, useEffect } from 'react';
import axios from 'axios';
import { Save, Shield, Key, Database, CheckCircle2, AlertCircle, Loader2 } from 'lucide-react';
import TrainingDataForm from './TrainingDataForm';

const AdminPanel: React.FC = () => {
  const [settings, setSettings] = useState({
    default_llm: 'gemini',
    anthropic_api_key: '',
    gemini_api_key: '',
    has_anthropic: false,
    has_gemini: false
  });
  
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [message, setMessage] = useState<{type: 'success' | 'error', text: string} | null>(null);

  useEffect(() => {
    fetchSettings();
  }, []);

  const fetchSettings = async () => {
    try {
      const response = await axios.get(API_BASE_URL + '/settings');
      setSettings(response.data);
    } catch (err) {
      console.error('Failed to fetch settings:', err);
      setMessage({ type: 'error', text: 'Failed to load settings.' });
    } finally {
      setLoading(false);
    }
  };

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setSaving(true);
    setMessage(null);
    
    try {
      await axios.post(API_BASE_URL + '/settings', {
        default_llm: settings.default_llm,
        anthropic_api_key: settings.anthropic_api_key,
        gemini_api_key: settings.gemini_api_key
      });
      setMessage({ type: 'success', text: 'Settings updated successfully!' });
      fetchSettings();
    } catch (err) {
      console.error('Failed to update settings:', err);
      setMessage({ type: 'error', text: 'Failed to update settings.' });
    } finally {
      setSaving(false);
    }
  };

  if (loading) {
    return (
      <div className="flex justify-center py-12">
        <div className="animate-spin rounded-full h-8 w-8 border-b-2 border-accent"></div>
      </div>
    );
  }

  return (
    <div className="max-w-3xl mx-auto">
      <div className="bg-blue-50 border border-blue-100 rounded-xl p-4 mb-8 flex items-start">
        <Shield className="h-5 w-5 text-blue-600 mr-3 mt-0.5" />
        <div className="text-sm text-blue-800">
          <p className="font-semibold">Administrator Access</p>
          <p className="mt-1">Manage API keys and add verified designs to the training library.</p>
        </div>
      </div>

      <form onSubmit={handleSubmit} className="space-y-8 mb-12">
        {/* Provider Selection */}
        <div>
          <h3 className="text-sm font-bold text-gray-500 uppercase tracking-wider mb-4 flex items-center">
            <Database className="h-4 w-4 mr-2" />
            AI Model Provider
          </h3>
          <div className="grid grid-cols-2 gap-4">
            <label className={`relative flex flex-col p-4 border-2 rounded-xl cursor-pointer transition-all ${
              settings.default_llm === 'gemini' ? 'border-accent bg-blue-50/30' : 'border-gray-200 hover:border-gray-300'
            }`}>
              <input 
                type="radio" name="default_llm" value="gemini" 
                checked={settings.default_llm === 'gemini'} 
                onChange={() => setSettings({...settings, default_llm: 'gemini'})}
                className="sr-only" 
              />
              <span className="font-bold text-[#111827]">Google Gemini</span>
              <span className="text-xs text-gray-500 mt-1">Fast & efficient (Gemini 3 Flash)</span>
              {settings.has_gemini && (
                <span className="absolute top-4 right-4 text-green-600">
                  <CheckCircle2 className="h-4 w-4" />
                </span>
              )}
            </label>
            <label className={`relative flex flex-col p-4 border-2 rounded-xl cursor-pointer transition-all ${
              settings.default_llm === 'anthropic' ? 'border-accent bg-blue-50/30' : 'border-gray-200 hover:border-gray-300'
            }`}>
              <input 
                type="radio" name="default_llm" value="anthropic" 
                checked={settings.default_llm === 'anthropic'} 
                onChange={() => setSettings({...settings, default_llm: 'anthropic'})}
                className="sr-only" 
              />
              <span className="font-bold text-[#111827]">Anthropic Claude</span>
              <span className="text-xs text-gray-500 mt-1">High reasoning (3.5 Sonnet)</span>
              {settings.has_anthropic && (
                <span className="absolute top-4 right-4 text-green-600">
                  <CheckCircle2 className="h-4 w-4" />
                </span>
              )}
            </label>
          </div>
        </div>

        {/* API Keys */}
        <div>
          <h3 className="text-sm font-bold text-gray-500 uppercase tracking-wider mb-4 flex items-center">
            <Key className="h-4 w-4 mr-2" />
            API Credentials
          </h3>
          <div className="space-y-4">
            <div>
              <label className="block text-xs font-bold text-gray-500 uppercase mb-2">Gemini API Key</label>
              <input
                type="password"
                value={settings.gemini_api_key}
                onChange={(e) => setSettings({...settings, gemini_api_key: e.target.value})}
                placeholder={settings.has_gemini ? "••••••••••••••••" : "Enter your Google AI Studio key"}
                className="w-full p-3 bg-white border border-gray-200 rounded-xl focus:ring-2 focus:ring-accent outline-none transition-all"
              />
            </div>
            <div>
              <label className="block text-xs font-bold text-gray-500 uppercase mb-2">Anthropic API Key</label>
              <input
                type="password"
                value={settings.anthropic_api_key}
                onChange={(e) => setSettings({...settings, anthropic_api_key: e.target.value})}
                placeholder={settings.has_anthropic ? "••••••••••••••••" : "Enter your Anthropic key"}
                className="w-full p-3 bg-white border border-gray-200 rounded-xl focus:ring-2 focus:ring-accent outline-none transition-all"
              />
            </div>
          </div>
        </div>

        {message && (
          <div className={`p-4 rounded-xl flex items-center text-sm ${
            message.type === 'success' ? 'bg-green-50 text-green-700 border border-green-100' : 'bg-red-50 text-red-700 border border-red-100'
          }`}>
            {message.type === 'success' ? <CheckCircle2 className="h-4 w-4 mr-2" /> : <AlertCircle className="h-4 w-4 mr-2" />}
            {message.text}
          </div>
        )}

        <button
          type="submit"
          disabled={saving}
          className="w-full bg-[#111827] text-white py-4 rounded-xl font-bold hover:bg-gray-800 transition-all transform hover:-translate-y-0.5 active:translate-y-0 flex items-center justify-center disabled:opacity-50"
        >
          {saving ? (
            <>
              <Loader2 className="h-5 w-5 mr-2 animate-spin" />
              Saving Settings...
            </>
          ) : (
            <>
              <Save className="h-5 w-5 mr-2" />
              Save Configuration
            </>
          )}
        </button>
      </form>

      <hr className="border-gray-100 my-12" />

      <TrainingDataForm />
    </div>
  );
};

export default AdminPanel;
