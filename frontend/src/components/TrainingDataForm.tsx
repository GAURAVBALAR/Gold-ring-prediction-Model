import { API_BASE_URL } from '../config';
import React, { useState } from 'react';
import axios from 'axios';
import { Upload, PlusCircle, CheckCircle2, AlertCircle, Loader2, X } from 'lucide-react';

const TrainingDataForm: React.FC = () => {
  const [formData, setFormData] = useState({
    product_name: '',
    karat: '18K',
    actual_weight_g: '',
    ring_size: '',
    stone_ct: '0.0'
  });
  const [image, setImage] = useState<File | null>(null);
  const [preview, setPreview] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);
  const [message, setMessage] = useState<{type: 'success' | 'error', text: string} | null>(null);

  const handleInputChange = (e: React.ChangeEvent<HTMLInputElement | HTMLSelectElement>) => {
    setFormData({ ...formData, [e.target.name]: e.target.value });
  };

  const handleImageChange = (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0];
    if (file) {
      setImage(file);
      const reader = new FileReader();
      reader.onloadend = () => setPreview(reader.result as string);
      reader.readAsDataURL(file);
    }
  };

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!image) {
      setMessage({ type: 'error', text: 'Please upload an image' });
      return;
    }

    setLoading(true);
    setMessage(null);

    const data = new FormData();
    Object.entries(formData).forEach(([key, value]) => {
      if (value) data.append(key, value);
    });
    data.append('image', image);

    try {
      await axios.post(API_BASE_URL + '/ingest', data);
      setMessage({ type: 'success', text: 'Verified design added to training library!' });
      setFormData({
        product_name: '',
        karat: '18K',
        actual_weight_g: '',
        ring_size: '',
        stone_ct: '0.0'
      });
      setImage(null);
      setPreview(null);
    } catch (err: any) {
      console.error(err);
      setMessage({ type: 'error', text: 'Failed to add design. Please try again.' });
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="bg-white border border-gray-100 rounded-2xl p-6 shadow-sm">
      <h3 className="text-lg font-bold text-[#111827] mb-6 flex items-center">
        <PlusCircle className="h-5 w-5 mr-2 text-accent" />
        Add Verified Training Design
      </h3>

      <form onSubmit={handleSubmit} className="space-y-4">
        {/* Image Upload */}
        <div className="mb-6">
          {preview ? (
            <div className="relative rounded-xl overflow-hidden aspect-video border border-gray-200">
              <img src={preview} alt="Preview" className="w-full h-full object-cover" />
              <button
                type="button"
                onClick={() => { setImage(null); setPreview(null); }}
                className="absolute top-2 right-2 p-1 bg-white/80 rounded-full text-gray-700"
              >
                <X className="h-4 w-4" />
              </button>
            </div>
          ) : (
            <label className="flex flex-col items-center justify-center w-full aspect-video border-2 border-dashed border-gray-200 rounded-xl cursor-pointer hover:bg-gray-50 transition-colors">
              <Upload className="h-8 w-8 text-gray-400 mb-2" />
              <span className="text-sm text-gray-500 text-center px-4">Upload verified design image</span>
              <input type="file" className="hidden" onChange={handleImageChange} accept="image/*" />
            </label>
          )}
        </div>

        <div className="grid grid-cols-2 gap-4">
          <div className="col-span-2">
            <label className="block text-xs font-bold text-gray-500 uppercase mb-1">Product Name</label>
            <input
              type="text" name="product_name" value={formData.product_name} onChange={handleInputChange} required
              placeholder="e.g. Vintage Floral Band"
              className="w-full p-2.5 bg-gray-50 border border-gray-200 rounded-lg outline-none focus:ring-2 focus:ring-accent"
            />
          </div>
          <div>
            <label className="block text-xs font-bold text-gray-500 uppercase mb-1">Actual Weight (g)</label>
            <input
              type="number" step="0.001" name="actual_weight_g" value={formData.actual_weight_g} onChange={handleInputChange} required
              placeholder="0.000"
              className="w-full p-2.5 bg-gray-50 border border-gray-200 rounded-lg outline-none focus:ring-2 focus:ring-accent"
            />
          </div>
          <div>
            <label className="block text-xs font-bold text-gray-500 uppercase mb-1">Karat</label>
            <select 
              name="karat" value={formData.karat} onChange={handleInputChange}
              className="w-full p-2.5 bg-gray-50 border border-gray-200 rounded-lg outline-none focus:ring-2 focus:ring-accent"
            >
              <option value="14K">14K Gold</option>
              <option value="18K">18K Gold</option>
              <option value="22K">22K Gold</option>
            </select>
          </div>
          <div>
            <label className="block text-xs font-bold text-gray-500 uppercase mb-1">Ring Size (US)</label>
            <input
              type="number" step="0.25" name="ring_size" value={formData.ring_size} onChange={handleInputChange}
              className="w-full p-2.5 bg-gray-50 border border-gray-200 rounded-lg outline-none focus:ring-2 focus:ring-accent"
            />
          </div>
          <div>
            <label className="block text-xs font-bold text-gray-500 uppercase mb-1">Stone Carat (ct)</label>
            <input
              type="number" step="0.01" name="stone_ct" value={formData.stone_ct} onChange={handleInputChange}
              className="w-full p-2.5 bg-gray-50 border border-gray-200 rounded-lg outline-none focus:ring-2 focus:ring-accent"
            />
          </div>
        </div>

        {message && (
          <div className={`p-3 rounded-lg flex items-center text-sm ${
            message.type === 'success' ? 'bg-green-50 text-green-700' : 'bg-red-50 text-red-700'
          }`}>
            {message.type === 'success' ? <CheckCircle2 className="h-4 w-4 mr-2" /> : <AlertCircle className="h-4 w-4 mr-2" />}
            {message.text}
          </div>
        )}

        <button
          type="submit"
          disabled={loading}
          className="w-full bg-[#111827] text-white py-3 rounded-xl font-bold hover:bg-gray-800 transition-all flex items-center justify-center disabled:opacity-50"
        >
          {loading ? <Loader2 className="h-5 w-5 animate-spin" /> : "Add to Library"}
        </button>
      </form>
    </div>
  );
};

export default TrainingDataForm;
