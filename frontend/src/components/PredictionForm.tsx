import { API_BASE_URL } from '../config';
import React, { useState } from 'react';
import axios from 'axios';
import { Upload, CheckCircle2, AlertCircle, Loader2, X, Search, ChevronDown, ChevronUp, Zap, Brain } from 'lucide-react';

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
  style: string;
  product_name: string;
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
    metal_color: 'Yellow',
    style: '',
    product_name: ''
  });

  const [images, setImages] = useState<File[]>([]);
  const [previews, setPreviews] = useState<string[]>([]);
  const [loading, setLoading] = useState(false);
  const [result, setResult] = useState<any>(null);
  const [error, setError] = useState<string | null>(null);
  const [advancedOpen, setAdvancedOpen] = useState(false);
  
  const [feedbackSubmitted, setFeedbackSubmitted] = useState(false);
  const [actualWeight, setActualWeight] = useState('');
  const [actualKarat, setActualKarat] = useState('18K');
  const [isSubmittingFeedback, setIsSubmittingFeedback] = useState(false);

  const handleFeedback = async (isCorrect: boolean) => {
    if (!result) return;
    
    setIsSubmittingFeedback(true);
    try {
      await axios.post(API_BASE_URL + '/feedback', {
        prediction_id: result.prediction?.id || result.id,
        is_correct: isCorrect,
        actual_weight_g: actualWeight ? parseFloat(actualWeight) : null,
        actual_karat: actualKarat,
        actual_diamond_carat: formData.stone_ct ? parseFloat(formData.stone_ct) : 0
      });
      setFeedbackSubmitted(true);
    } catch (err) {
      console.error('Feedback failed:', err);
    } finally {
      setIsSubmittingFeedback(false);
    }
  };

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
    
    // Parse raw_response breakdown
    const rawResponse = prediction.raw_response?.llm_raw || prediction.raw_response;
    const volumeBreakdown = rawResponse?.volume_breakdown;

    // Ensemble data from raw_response
    const ensemble = prediction.raw_response?.ensemble;
    const isFastPath = rawResponse?.fast_path === true;
    const ensembleSources = ensemble?.sources || {};
    const ensembleWeights = ensemble?.weights || {};
    const ensembleProfile = ensemble?.profile_used || 'default';

    // Source display config
    const sourceConfig: Record<string, { label: string; color: string; bgColor: string }> = {
      llm: { label: 'LLM (Gemini)', color: 'text-purple-700', bgColor: 'bg-purple-500' },
      rag: { label: 'RAG (Visual)', color: 'text-blue-700', bgColor: 'bg-blue-500' },
      xgb: { label: 'XGBoost', color: 'text-emerald-700', bgColor: 'bg-emerald-500' },
    };

    return (
      <div className="space-y-6 animate-fadeInUp">
        {/* Header with Fast Path / Full AI badge */}
        <div className="flex items-center justify-between mb-4">
          <div className="flex items-center text-green-600">
            <CheckCircle2 className="h-6 w-6 mr-2" />
            <h3 className="text-xl font-semibold">Prediction Ready</h3>
          </div>
          {isFastPath ? (
            <span className="inline-flex items-center gap-1.5 px-3 py-1.5 rounded-full text-xs font-bold bg-emerald-50 text-emerald-700 border border-emerald-200 shadow-sm" title="Prediction was served from cached ML models without calling the LLM API">
              <Zap className="h-3.5 w-3.5" />
              Fast Path (Cached)
            </span>
          ) : (
            <span className="inline-flex items-center gap-1.5 px-3 py-1.5 rounded-full text-xs font-bold bg-purple-50 text-purple-700 border border-purple-200 shadow-sm" title="Prediction used full Gemini LLM reasoning with ensemble blending">
              <Brain className="h-3.5 w-3.5" />
              Full AI Reasoning
            </span>
          )}
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

        {/* Ensemble Breakdown */}
        {ensemble && Object.keys(ensembleSources).length > 0 && (
          <div className="bg-white border border-gray-100 rounded-xl p-5 shadow-sm space-y-4">
            <div className="flex items-center justify-between">
              <h4 className="text-xs font-bold text-gray-500 uppercase tracking-wider">
                Ensemble Breakdown
              </h4>
              <span className="text-[10px] font-semibold text-gray-400 uppercase bg-gray-50 px-2 py-0.5 rounded-full border border-gray-100">
                Profile: {ensembleProfile}
              </span>
            </div>

            <div className="space-y-3">
              {Object.entries(ensembleSources).map(([key, volume]) => {
                const config = sourceConfig[key] || { label: key, color: 'text-gray-700', bgColor: 'bg-gray-500' };
                const weight = ensembleWeights[key] || 0;
                const pct = Math.round(weight * 100);

                return (
                  <div key={key} className="space-y-1">
                    <div className="flex items-center justify-between text-sm">
                      <span className={`font-semibold ${config.color}`}>{config.label}</span>
                      <span className="text-gray-500 text-xs font-medium">
                        {(volume as number)?.toFixed(1)} mm³ · <span className="font-bold text-gray-700">{pct}%</span>
                      </span>
                    </div>
                    <div className="w-full bg-gray-100 rounded-full h-2 overflow-hidden">
                      <div
                        className={`h-2 rounded-full ${config.bgColor} transition-all duration-500`}
                        style={{ width: `${pct}%` }}
                      />
                    </div>
                  </div>
                );
              })}
            </div>
          </div>
        )}

        {/* Detailed Volume Breakdown */}
        {volumeBreakdown && (
          <div className="bg-white border border-gray-100 rounded-xl p-5 shadow-sm space-y-4">
            <h4 className="text-xs font-bold text-gray-500 uppercase tracking-wider">
              Component Volume Breakdown
            </h4>
            <div className="grid grid-cols-2 sm:grid-cols-4 gap-3">
              <div className="bg-gray-50/50 p-3 rounded-lg border border-gray-100">
                <span className="text-[10px] text-gray-400 uppercase font-bold">Shank</span>
                <div className="text-sm font-bold text-gray-800 mt-0.5">
                  {volumeBreakdown.shank_mm3 ? `${volumeBreakdown.shank_mm3.toFixed(1)} mm³` : '0.0 mm³'}
                </div>
              </div>
              <div className="bg-gray-50/50 p-3 rounded-lg border border-gray-100">
                <span className="text-[10px] text-gray-400 uppercase font-bold">Head/Setting</span>
                <div className="text-sm font-bold text-gray-800 mt-0.5">
                  {volumeBreakdown.head_setting_mm3 ? `${volumeBreakdown.head_setting_mm3.toFixed(1)} mm³` : '0.0 mm³'}
                </div>
              </div>
              <div className="bg-gray-50/50 p-3 rounded-lg border border-gray-100">
                <span className="text-[10px] text-gray-400 uppercase font-bold">Gallery</span>
                <div className="text-sm font-bold text-gray-800 mt-0.5">
                  {volumeBreakdown.gallery_mm3 ? `${volumeBreakdown.gallery_mm3.toFixed(1)} mm³` : '0.0 mm³'}
                </div>
              </div>
              <div className="bg-gray-50/50 p-3 rounded-lg border border-gray-100">
                <span className="text-[10px] text-gray-400 uppercase font-bold">Side Channels</span>
                <div className="text-sm font-bold text-gray-800 mt-0.5">
                  {volumeBreakdown.side_stone_channels_mm3 ? `${volumeBreakdown.side_stone_channels_mm3.toFixed(1)} mm³` : '0.0 mm³'}
                </div>
              </div>
            </div>

            {volumeBreakdown.calculation_steps && (
              <div className="text-xs text-gray-500 italic bg-gray-50/30 p-2.5 rounded-lg border border-dashed border-gray-100">
                <span className="font-semibold text-gray-600 block mb-0.5">Calculation Steps:</span>
                "{volumeBreakdown.calculation_steps}"
              </div>
            )}
          </div>
        )}

        {/* Confidence and Calibration */}
        {rawResponse && (
          <div className="bg-white border border-gray-100 rounded-xl p-5 shadow-sm space-y-4">
            <h4 className="text-xs font-bold text-gray-500 uppercase tracking-wider">
              Confidence & Reference Calibration
            </h4>
            
            <div className="grid grid-cols-2 gap-4">
              <div className="bg-gray-50/50 p-3 rounded-lg border border-gray-100">
                <span className="text-[10px] text-gray-400 uppercase font-bold">Confidence Level</span>
                <div className={`text-sm font-bold mt-0.5 capitalize ${
                  rawResponse.confidence === 'high' ? 'text-green-600' :
                  rawResponse.confidence === 'medium' ? 'text-amber-500' : 'text-red-500'
                }`}>
                  {rawResponse.confidence || 'Medium'}
                </div>
              </div>
              <div className="bg-gray-50/50 p-3 rounded-lg border border-gray-100">
                <span className="text-[10px] text-gray-400 uppercase font-bold">Confidence Note</span>
                <div className="text-xs text-gray-600 mt-0.5 font-medium">
                  {rawResponse.confidence_note || 'N/A'}
                </div>
              </div>
            </div>

            {rawResponse.reference_alignment && (
              <div className="text-xs text-gray-600 bg-gray-50/30 p-3 rounded-lg border border-gray-100">
                <span className="font-semibold text-gray-700 block mb-1">Reference Alignment:</span>
                "{rawResponse.reference_alignment}"
              </div>
            )}
          </div>
        )}

        <div className="mt-6">
          <h4 className="text-sm font-bold text-gray-500 uppercase tracking-wider mb-2">AI Explanation</h4>
          <p className="text-gray-700 text-sm leading-relaxed bg-white border border-gray-100 p-4 rounded-xl shadow-sm italic">
            "{prediction.llm_explanation}"
          </p>
        </div>

        {/* FEEDBACK SECTION */}
        <div className="mt-8 bg-white border border-gray-100 rounded-2xl p-6 shadow-sm">
          <h4 className="text-sm font-bold text-gray-500 uppercase tracking-wider mb-4 flex items-center">
            <CheckCircle2 className="h-4 w-4 mr-2 text-accent" />
            Was this prediction accurate?
          </h4>
          
          {!feedbackSubmitted ? (
            <div className="space-y-4">
              <div className="flex space-x-4">
                <button 
                  onClick={() => handleFeedback(true)}
                  className="flex-1 py-3 px-4 rounded-xl border-2 border-green-500 text-green-600 font-bold hover:bg-green-50 transition-colors"
                >
                  Yes, Accurate
                </button>
                <button 
                  onClick={() => handleFeedback(false)}
                  className="flex-1 py-3 px-4 rounded-xl border-2 border-red-500 text-red-600 font-bold hover:bg-red-50 transition-colors"
                >
                  No, Needs Fix
                </button>
              </div>
              
              <div className="pt-4 border-t border-gray-50">
                <p className="text-xs text-gray-500 mb-3">Provide actual data to improve the AI's future accuracy:</p>
                <div className="grid grid-cols-2 gap-4">
                  <input 
                    type="number" 
                    placeholder="Actual Weight (g)" 
                    value={actualWeight}
                    onChange={(e) => setActualWeight(e.target.value)}
                    className="p-3 bg-gray-50 border border-gray-200 rounded-xl outline-none focus:ring-2 focus:ring-accent text-sm"
                  />
                  <select 
                    value={actualKarat}
                    onChange={(e) => setActualKarat(e.target.value)}
                    className="p-3 bg-gray-50 border border-gray-200 rounded-xl outline-none focus:ring-2 focus:ring-accent text-sm"
                  >
                    <option value="14K">14K</option>
                    <option value="18K">18K</option>
                    <option value="22K">22K</option>
                    <option value="24K">24K</option>
                  </select>
                </div>
                <button 
                  onClick={() => handleFeedback(false)}
                  disabled={!actualWeight || isSubmittingFeedback}
                  className="w-full mt-4 bg-accent text-white py-3 rounded-xl font-bold hover:bg-accent/90 transition-all disabled:opacity-50"
                >
                  {isSubmittingFeedback ? 'Syncing with Vector DB...' : 'Submit Actual Data'}
                </button>
              </div>
            </div>
          ) : (
            <div className="bg-green-50 text-green-700 p-4 rounded-xl text-center text-sm font-medium border border-green-100">
              Thank you! This data has been converted to design density and re-indexed into Pinecone to improve future RAG results.
            </div>
          )}
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
              metal_color: 'Yellow',
              style: '',
              product_name: ''
            });
            setImages([]);
            setPreviews([]);
            setFeedbackSubmitted(false);
            setActualWeight('');
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

      {/* Core Parameters */}
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
        <div>
          <label className="block text-xs font-bold text-gray-500 uppercase mb-1 ml-1">Ring Style</label>
          <select
            name="style" value={formData.style} onChange={handleInputChange}
            className="w-full p-3 bg-gray-50 border border-gray-200 rounded-xl outline-none focus:ring-2 focus:ring-accent transition-all"
          >
            <option value="">Auto-detect</option>
            <option value="solitaire">Solitaire</option>
            <option value="halo">Halo</option>
            <option value="bypass">Bypass / Toi et Moi</option>
            <option value="pave_single">Pavé (Single Row)</option>
            <option value="pave_double">Pavé (Double Row)</option>
            <option value="vintage">Vintage</option>
            <option value="cluster">Cluster</option>
            <option value="eternity">Eternity</option>
            <option value="bezel">Bezel</option>
            <option value="chevron">Chevron</option>
            <option value="band">Plain Band</option>
          </select>
        </div>
        <div className="col-span-2">
          <label className="block text-xs font-bold text-gray-500 uppercase mb-1 ml-1">Product Name</label>
          <input
            type="text" name="product_name" value={formData.product_name} onChange={handleInputChange}
            placeholder="e.g. Two stone bypass ring with oval diamonds"
            className="w-full p-3 bg-gray-50 border border-gray-200 rounded-xl outline-none focus:ring-2 focus:ring-accent transition-all"
          />
        </div>
      </div>

      {/* Advanced Geometry Section (collapsible) */}
      <div className="border border-gray-200 rounded-xl overflow-hidden">
        <button
          type="button"
          onClick={() => setAdvancedOpen(!advancedOpen)}
          className="w-full flex items-center justify-between p-4 bg-gray-50/50 hover:bg-gray-50 transition-colors text-left"
        >
          <span className="text-xs font-bold text-gray-500 uppercase tracking-wider">Advanced Geometry</span>
          {advancedOpen ? (
            <ChevronUp className="h-4 w-4 text-gray-400" />
          ) : (
            <ChevronDown className="h-4 w-4 text-gray-400" />
          )}
        </button>

        {advancedOpen && (
          <div className="p-4 space-y-4 border-t border-gray-100 animate-fadeInUp">
            <p className="text-xs text-gray-400 italic">
              These fields help improve prediction accuracy for detailed manufacturing estimates.
            </p>
            <div className="grid grid-cols-2 gap-4">
              <div>
                <label className="block text-xs font-bold text-gray-500 uppercase mb-1 ml-1">Band Width (mm)</label>
                <input
                  type="number" step="0.1" name="band_width_mm" value={formData.band_width_mm} onChange={handleInputChange}
                  placeholder="e.g. 2.5"
                  className="w-full p-3 bg-gray-50 border border-gray-200 rounded-xl outline-none focus:ring-2 focus:ring-accent transition-all text-sm"
                />
              </div>
              <div>
                <label className="block text-xs font-bold text-gray-500 uppercase mb-1 ml-1">Band Thickness (mm)</label>
                <input
                  type="number" step="0.1" name="band_thickness_mm" value={formData.band_thickness_mm} onChange={handleInputChange}
                  placeholder="e.g. 1.5"
                  className="w-full p-3 bg-gray-50 border border-gray-200 rounded-xl outline-none focus:ring-2 focus:ring-accent transition-all text-sm"
                />
              </div>
              <div>
                <label className="block text-xs font-bold text-gray-500 uppercase mb-1 ml-1">Stone Length (mm)</label>
                <input
                  type="number" step="0.1" name="stone_length_mm" value={formData.stone_length_mm} onChange={handleInputChange}
                  placeholder="e.g. 6.0"
                  className="w-full p-3 bg-gray-50 border border-gray-200 rounded-xl outline-none focus:ring-2 focus:ring-accent transition-all text-sm"
                />
              </div>
              <div>
                <label className="block text-xs font-bold text-gray-500 uppercase mb-1 ml-1">Stone Width (mm)</label>
                <input
                  type="number" step="0.1" name="stone_width_mm" value={formData.stone_width_mm} onChange={handleInputChange}
                  placeholder="e.g. 4.0"
                  className="w-full p-3 bg-gray-50 border border-gray-200 rounded-xl outline-none focus:ring-2 focus:ring-accent transition-all text-sm"
                />
              </div>
              <div>
                <label className="block text-xs font-bold text-gray-500 uppercase mb-1 ml-1">Side Stone Count</label>
                <input
                  type="number" step="1" name="side_stone_count" value={formData.side_stone_count} onChange={handleInputChange}
                  placeholder="0"
                  className="w-full p-3 bg-gray-50 border border-gray-200 rounded-xl outline-none focus:ring-2 focus:ring-accent transition-all text-sm"
                />
              </div>
              <div>
                <label className="block text-xs font-bold text-gray-500 uppercase mb-1 ml-1">Side Stone Carat (ct)</label>
                <input
                  type="number" step="0.01" name="side_stone_ct" value={formData.side_stone_ct} onChange={handleInputChange}
                  placeholder="0.0"
                  className="w-full p-3 bg-gray-50 border border-gray-200 rounded-xl outline-none focus:ring-2 focus:ring-accent transition-all text-sm"
                />
              </div>
            </div>
          </div>
        )}
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
