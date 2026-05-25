import { API_BASE_URL } from '../config';
import React, { useState, useEffect } from 'react';
import axios from 'axios';
import { Calendar, Download, Loader2, CheckCircle2, AlertCircle } from 'lucide-react';

const HistoryTable: React.FC = () => {
  const [history, setHistory] = useState<any[]>([]);
  const [loading, setLoading] = useState(true);
  const [exporting, setExporting] = useState(false);
  const [exportError, setExportError] = useState<string | null>(null);

  useEffect(() => {
    const fetchHistory = async () => {
      try {
        const response = await axios.get(API_BASE_URL + '/history');
        setHistory(response.data);
      } catch (err) {
        console.error('Failed to fetch history:', err);
      } finally {
        setLoading(false);
      }
    };
    fetchHistory();
  }, []);

  const handleExportCSV = async () => {
    setExporting(true);
    setExportError(null);
    try {
      const response = await axios.get(API_BASE_URL + '/history/export', {
        responseType: 'blob'
      });

      const blob = new Blob([response.data], { type: 'text/csv' });
      const url = window.URL.createObjectURL(blob);
      const link = document.createElement('a');
      link.href = url;
      link.download = 'gold_weight_predictions_history.csv';
      document.body.appendChild(link);
      link.click();
      document.body.removeChild(link);
      window.URL.revokeObjectURL(url);
    } catch (err) {
      console.error('Export failed:', err);
      setExportError('Failed to export CSV. Please try again.');
    } finally {
      setExporting(false);
    }
  };

  if (loading) {
    return (
      <div className="flex justify-center py-12">
        <div className="animate-spin rounded-full h-8 w-8 border-b-2 border-accent"></div>
      </div>
    );
  }

  if (history.length === 0) {
    return (
      <div className="text-center py-12 text-gray-500 italic">
        No predictions found in history.
      </div>
    );
  }

  return (
    <div className="space-y-4">
      {/* Header row with export button */}
      <div className="flex items-center justify-between">
        <p className="text-sm text-gray-500">
          {history.length} prediction{history.length !== 1 ? 's' : ''} recorded
        </p>
        <button
          onClick={handleExportCSV}
          disabled={exporting}
          className="inline-flex items-center gap-2 px-4 py-2 rounded-xl bg-[#1e293b] text-white text-sm font-semibold hover:bg-[#334155] transition-all disabled:opacity-50 disabled:cursor-not-allowed shadow-sm"
        >
          {exporting ? (
            <>
              <Loader2 className="h-4 w-4 animate-spin" />
              Exporting…
            </>
          ) : (
            <>
              <Download className="h-4 w-4" />
              Export CSV
            </>
          )}
        </button>
      </div>

      {exportError && (
        <div className="p-3 bg-red-50 text-red-700 rounded-xl flex items-center text-sm border border-red-100">
          <AlertCircle className="h-4 w-4 mr-2 flex-shrink-0" />
          {exportError}
        </div>
      )}

      {/* Table */}
      <div className="overflow-x-auto">
        <table className="w-full text-left">
          <thead>
            <tr className="border-b border-gray-200">
              <th className="py-4 px-4 text-xs font-bold text-gray-400 uppercase tracking-wider">Date</th>
              <th className="py-4 px-4 text-xs font-bold text-gray-400 uppercase tracking-wider">Ring Size</th>
              <th className="py-4 px-4 text-xs font-bold text-gray-400 uppercase tracking-wider">14K Weight</th>
              <th className="py-4 px-4 text-xs font-bold text-gray-400 uppercase tracking-wider">18K Weight</th>
              <th className="py-4 px-4 text-xs font-bold text-gray-400 uppercase tracking-wider">Status</th>
              <th className="py-4 px-4 text-xs font-bold text-gray-400 uppercase tracking-wider">Actual</th>
            </tr>
          </thead>
          <tbody className="divide-y divide-gray-100">
            {history.map((item) => {
              const hasActual = item.actual_weight_g != null && item.actual_weight_g > 0;

              return (
                <tr key={item.id} className="hover:bg-gray-50 transition-colors group">
                  <td className="py-4 px-4">
                    <div className="flex items-center text-sm text-gray-600">
                      <Calendar className="h-4 w-4 mr-2 text-gray-400" />
                      {new Date(item.created_at).toLocaleDateString()}
                    </div>
                  </td>
                  <td className="py-4 px-4 font-medium">{item.ring_size ?? '—'}</td>
                  <td className="py-4 px-4 font-bold text-[#111827]">
                    {item.predicted_weight_14k != null ? `${item.predicted_weight_14k.toFixed(3)}g` : '—'}
                  </td>
                  <td className="py-4 px-4 font-bold text-[#111827]">
                    {item.predicted_weight_18k != null ? `${item.predicted_weight_18k.toFixed(3)}g` : '—'}
                  </td>
                  <td className="py-4 px-4">
                    {hasActual ? (
                      <span className="inline-flex items-center gap-1 px-2.5 py-0.5 rounded-full text-xs font-medium bg-green-50 text-green-700 border border-green-200">
                        <CheckCircle2 className="h-3 w-3" />
                        Verified
                      </span>
                    ) : (
                      <span className="inline-flex items-center px-2.5 py-0.5 rounded-full text-xs font-medium bg-blue-100 text-blue-800">
                        Predicted
                      </span>
                    )}
                  </td>
                  <td className="py-4 px-4">
                    {hasActual ? (
                      <div className="text-sm">
                        <span className="font-bold text-green-700">{item.actual_weight_g.toFixed(3)}g</span>
                        {item.actual_karat && (
                          <span className="ml-1 text-xs text-gray-500">({item.actual_karat})</span>
                        )}
                      </div>
                    ) : (
                      <span className="text-xs text-gray-400 italic">—</span>
                    )}
                  </td>
                </tr>
              );
            })}
          </tbody>
        </table>
      </div>
    </div>
  );
};

export default HistoryTable;
