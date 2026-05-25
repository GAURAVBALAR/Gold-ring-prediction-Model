import { API_BASE_URL } from '../config';
import React, { useState } from 'react';
import axios from 'axios';
import { Upload, CheckCircle2, AlertCircle, Loader2, X, Search } from 'lucide-react';

interface FormData {
  ring_size: string;
  inner_diameter_mm: string;
  band_width_mm: string;
  band_thickness_mm: string;
  stone_length_mm: string;
  stone_width_mm: string;
  stone_ct: string;
  side_stone_count: string;
  side_stone_ct: string;
  karat: string;
  metal_color: string;
}

const PredictionForm: React.FC = () => {
  const [formData, setFormData] = useState<FormData>({
    ring_size: '',
    inner_diameter_mm: '',
    band_width_mm: '',
    band_thickness_mm: '',
    stone_length_mm: '',
    stone_width_mm: '',
    stone_ct: '',
    side_stone_count: '0',
    side_stone_ct: '0.0',
    karat: '18K',
    metal_color: 'Yellow'
  });

  const [images, setImages] = useState<File[]>([]);
  const [previews, setPreviews] = useState<string[]>([]);
  const [loading, setLoading] = useState(false);
  const [result, setResult] = useState<any>(null);
  const [error, setError] = useState<string | null>(null);

  const handleInputChange = (e: React.ChangeEvent<HTMLInputElement | HTMLSelectElement>) => {
    setFormData({ ...formData, [e.target.name]: e.target.value });
  };

  const handleImageChange = (e: React.ChangeEvent<HTMLInputElement>) => {
    const files = Array.from(e.target.files || []);
    const newImages = [...images, ...files].slice(0, 3);
    setImages(newImages);

    const newPreviews: string[] = [];
    newImages.forEach(file => {
      const reader = new FileReader();
      reader.onloadend = () => {
        newPreviews.push(reader.result as string);
        if (newPreviews.length === newImages.length) {
          setPreviews(newPreviews);
        }
      };
      reader.readAsDataURL(file);
    });
  };

  const removeImage = (index: number) => {
    const newImages = images.filter((_, i) => i !== index);
    const newPreviews = previews.filter((_, i) => i !== index);
    setImages(newImages);
    setPreviews(newPreviews);
  };

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (images.length === 0) {
      setError('Please upload at least one ring image');
      return;
    }

    setLoading(true);
    setError(null);
    setResult(null);

    const data = new FormData();
    Object.entries(formData).forEach(([key, value]) => {
      if (value) data.append(key, value);
    });
    
    images.forEach(img => {
      data.append('images', img);
    });

    try {
      const response = await axios.post(API_BASE_URL + '/predict', data);
      setResult(response.data);
    } catch (err: any) {
      console.error(err);
      setError(err.response?.data?.detail || 'Failed to get prediction. Please try again.');
    } finally {
      setLoading(false);
    }
  };

  if (result) {
    const prediction = result.prediction || result;
    const similar_examples = result.similar_examples || [];

    return (
      <div className="space-y-6 animate-fadeInUp">
        <div className="flex items-center text-green-600 mb-4">
          <CheckCircle2 className="h-6 w-6 mr-2" />
          <h3 className="text-xl font-semibold">Prediction Ready</h3>
        </div>
        
        <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
          <div className="bg-gray-50 p-4 rounded-xl border border-gray-100">
            <span className="text-xs text-gray-500 uppercase tracking-wider font-bold">14K Gold Range</span>
            <div className="text-xl font-bold text-[#111827] mt-1">
              {prediction.min_weight_14k?.toFixed(3)}g - {prediction.max_weight_14k?.toFixed(3)}g
            </div>
          </div>
          <div className="bg-gray-50 p-4 rounded-xl border border-gray-100">
            <span className="text-xs text-gray-500 uppercase tracking-wider font-bold">18K Gold Range</span>
            <div className="text-xl font-bold text-[#111827] mt-1">
              {prediction.min_weight_18k?.toFixed(3)}g - {prediction.max_weight_18k?.toFixed(3)}g
            </div>
          </div>
          <div className="bg-gray-50 p-4 rounded-xl border border-gray-100">
            <span className="text-xs text-gray-500 uppercase tracking-wider font-bold">22K Gold Range</span>
            <div className="text-xl font-bold text-[#111827] mt-1">
              {prediction.min_weight_22k?.toFixed(3)}g - {prediction.max_weight_22k?.toFixed(3)}g
            </div>
          </div>
        </div>

        <div className="bg-accent/5 border border-accent/10 rounded-xl p-4 flex justify-between items-center">
          <div>
            <span className="text-xs text-accent uppercase tracking-wider font-bold">Estimated Base Volume</span>
            <div className="text-lg font-bold text-[#111827]">{prediction.estimated_volume_mm3?.toFixed(2)} mm³</div>
          </div>
          <div className="text-right">
            <span className="text-[10px] text-gray-400 block uppercase">Manufacturing Cap</span>
            <span className="text-sm font-bold text-green-600">Safe Buffer Applied</span>
          </div>
        </div>

        <div className="mt-6">
          <h4 className="text-sm font-bold text-gray-500 uppercase tracking-wider mb-2">AI Explanation</h4>
          <p className="text-gray-700 text-sm leading-relaxed bg-white border border-gray-100 p-4 rounded-xl shadow-sm italic">
            "{prediction.llm_explanation}"
          </p>
        </div>

        {similar_examples.length > 0 && (
          <div className="mt-8">
            <h4 className="text-sm font-bold text-gray-500 uppercase tracking-wider mb-4 flex items-center">
              <Search className="h-4 w-4 mr-2" />
              Similar Designs from History
            </h4>
            <div className="grid grid-cols-1 gap-3">
              {similar_examples.map((ex: any, idx: number) => (
                <div key={idx} className="flex items-center justify-between p-3 bg-white border border-gray-100 rounded-xl shadow-sm hover:shadow-md transition-shadow">
                  <div className="flex-1">
                    <div className="text-sm font-bold text-gray-800">{ex.product_name || `Similar Ring #${idx + 1}`}</div>
                    <div className="text-xs text-gray-500">
                      Size: {ex.params?.ring_size || 'N/A'} | Stone: {ex.params?.stone_ct || 0}ct | Vol: {ex.actual_volume_mm3?.toFixed(1)}mm³
                    </div>
                  </div>
                  <div className="text-right">
                    <div className="text-sm font-bold text-accent">{ex.actual_weight}g ({ex.karat})</div>
                    <div className="text-[10px] text-gray-400">Match: {(ex.score * 100).toFixed(1)}%</div>
                  </div>
                </div>
              ))}
            </div>
          </div>
        )}

        <button
          onClick={() => {
            setResult(null);
            setFormData({
              ring_size: '',
              inner_diameter_mm: '',
              band_width_mm: '',
              band_thickness_mm: '',
              stone_length_mm: '',
              stone_width_mm: '',
              stone_ct: '',
              side_stone_count: '0',
              side_stone_ct: '0.0',
              karat: '18K',
              metal_color: 'Yellow'
            });
            setImages([]);
            setPreviews([]);
          }}
          className="w-full mt-4 bg-[#111827] text-white py-3 rounded-xl font-semibold hover:bg-gray-800 transition-all transform hover:-translate-y-0.5 active:translate-y-0"
        >
          New Calculation
        </button>
      </div>
    );
  }

  return (
    <form onSubmit={handleSubmit} className="space-y-6">
      {/* Image Upload */}
      <div className="space-y-4">
        <label className="block text-xs font-bold text-gray-500 uppercase tracking-wider">
          Ring Images (Up to 3, multi-angle recommended)
        </label>
        
        <div className="grid grid-cols-3 gap-4">
          {previews.map((preview, idx) => (
            <div key={idx} className="relative aspect-square rounded-xl overflow-hidden border border-gray-200 shadow-sm group">
              <img src={preview} alt={`Preview ${idx + 1}`} className="w-full h-full object-cover" />
              <button
                type="button"
                onClick={() => removeImage(idx)}
                className="absolute top-1 right-1 p-1 bg-white/90 rounded-full text-red-500 hover:bg-white transition-colors shadow-sm"
              >
                <X className="h-3 w-3" />
              </button>
            </div>
          ))}
          
          {images.length < 3 && (
            <label className="flex flex-col items-center justify-center aspect-square border-2 border-dashed border-gray-200 rounded-xl cursor-pointer hover:bg-gray-50 hover:border-accent transition-all group">
              <Upload className="h-6 w-6 text-gray-400 group-hover:text-accent group-hover:scale-110 transition-all" />
              <span className="text-[10px] text-gray-400 font-bold uppercase mt-1">Add Photo</span>
              <input type="file" className="hidden" onChange={handleImageChange} accept="image/*" multiple />
            </label>
          )}
        </div>
      </div>

      <div className="grid grid-cols-2 gap-4">
        <div>
          <label className="block text-xs font-bold text-gray-500 uppercase mb-1 ml-1">Ring Size (US)</label>
          <input
            type="number" step="0.25" name="ring_size" value={formData.ring_size} onChange={handleInputChange}
            placeholder="Optional"
            className="w-full p-3 bg-gray-50 border border-gray-200 rounded-xl outline-none focus:ring-2 focus:ring-accent transition-all"
          />
        </div>
        <div>
          <label className="block text-xs font-bold text-gray-500 uppercase mb-1 ml-1">Stone Carat (ct)</label>
          <input
            type="number" step="0.01" name="stone_ct" value={formData.stone_ct} onChange={handleInputChange}
            placeholder="Optional"
            className="w-full p-3 bg-gray-50 border border-gray-200 rounded-xl outline-none focus:ring-2 focus:ring-accent transition-all"
          />
        </div>
      </div>

      {error && (
        <div className="p-4 bg-red-50 text-red-700 rounded-xl flex items-center text-sm border border-red-100">
          <AlertCircle className="h-4 w-4 mr-2 flex-shrink-0" />
          {error}
        </div>
      )}

      <button
        type="submit"
        disabled={loading}
        className="w-full bg-[#111827] text-white py-4 rounded-xl font-bold hover:bg-gray-800 transition-all disabled:opacity-50 disabled:cursor-not-allowed flex items-center justify-center shadow-lg shadow-gray-200"
      >
        {loading ? (
          <>
            <Loader2 className="h-5 w-5 mr-2 animate-spin" />
            Calculating Volume & Weight...
          </>
        ) : (
          "Calculate Gold Weight"
        )}
      </button>
    </form>
  );
};

export default PredictionForm;
