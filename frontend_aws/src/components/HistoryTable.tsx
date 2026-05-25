import { API_BASE_URL } from '../config';
import React, { useState, useEffect } from 'react';
import axios from 'axios';
import { Calendar } from 'lucide-react';

const HistoryTable: React.FC = () => {
  const [history, setHistory] = useState<any[]>([]);
  const [loading, setLoading] = useState(true);

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
    <div className="overflow-x-auto">
      <table className="w-full text-left">
        <thead>
          <tr className="border-b border-gray-200">
            <th className="py-4 px-4 text-xs font-bold text-gray-400 uppercase tracking-wider">Date</th>
            <th className="py-4 px-4 text-xs font-bold text-gray-400 uppercase tracking-wider">Ring Size</th>
            <th className="py-4 px-4 text-xs font-bold text-gray-400 uppercase tracking-wider">14K Weight</th>
            <th className="py-4 px-4 text-xs font-bold text-gray-400 uppercase tracking-wider">18K Weight</th>
            <th className="py-4 px-4 text-xs font-bold text-gray-400 uppercase tracking-wider">Status</th>
          </tr>
        </thead>
        <tbody className="divide-y divide-gray-100">
          {history.map((item) => (
            <tr key={item.id} className="hover:bg-gray-50 transition-colors group">
              <td className="py-4 px-4">
                <div className="flex items-center text-sm text-gray-600">
                  <Calendar className="h-4 w-4 mr-2 text-gray-400" />
                  {new Date(item.created_at).toLocaleDateString()}
                </div>
              </td>
              <td className="py-4 px-4 font-medium">{item.ring_size}</td>
              <td className="py-4 px-4 font-bold text-[#111827]">{item.predicted_weight_14k.toFixed(3)}g</td>
              <td className="py-4 px-4 font-bold text-[#111827]">{item.predicted_weight_18k.toFixed(3)}g</td>
              <td className="py-4 px-4">
                <span className="inline-flex items-center px-2.5 py-0.5 rounded-full text-xs font-medium bg-blue-100 text-blue-800">
                  Predicted
                </span>
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
};

export default HistoryTable;
