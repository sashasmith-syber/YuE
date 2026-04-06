#!/usr/bin/env python3
"""
ONPU AI K2 Studio - Soundblueprint Analyzer
Audio DNA extraction (existing behavior preserved).
"""
import io
import logging
from typing import Dict, Any

import numpy as np
import librosa
import soundfile as sf
from scipy import signal
from scipy.stats import entropy

logger = logging.getLogger(__name__)

DNA_DIMENSIONS = {
    "TRE": "Temporal Rhythmic Extractor",
    "RIM": "Rhythmic Intention Matrix",
    "TDU": "Timbre Deconstruction Unit",
    "SDE": "Spectral Dynamics Engine",
    "GRM": "Generative Rhythm Modulator",
    "GTSU": "Generative Timbre Synthesis Unit",
    "PMS": "Perceptual Metrics Synthesizer",
    "GEE": "Groove Entropy Evaluator",
    "CGE": "Contextual Genre Engine",
    "DCP": "Dynamic Compression Profiler",
    "CBE": "Contextual Beat Evaluator",
}
SAMPLE_RATE = 22050


class SoundblueprintAnalyzer:
    def __init__(self):
        logger.info("Soundblueprint Analyzer initialized")

    def analyze_audio(self, audio_data: bytes) -> Dict[str, Any]:
        try:
            audio, sr = sf.read(io.BytesIO(audio_data))
            if len(audio.shape) > 1:
                audio = audio.mean(axis=1)
            if sr != SAMPLE_RATE:
                audio = librosa.resample(audio, orig_sr=sr, target_sr=SAMPLE_RATE)
            dna = {}
            dna["TRE"] = self._extract_tre(audio)
            dna["RIM"] = self._extract_rim(audio)
            dna["TDU"] = self._extract_tdu(audio)
            dna["SDE"] = self._extract_sde(audio)
            dna["GRM"] = self._extract_grm(audio)
            dna["GTSU"] = self._extract_gtsu(audio)
            dna["PMS"] = self._extract_pms(audio)
            dna["GEE"] = self._extract_gee(audio)
            dna["CGE"] = self._extract_cge(audio)
            dna["DCP"] = self._extract_dcp(audio)
            dna["CBE"] = self._extract_cbe(audio)
            completeness = self._calculate_completeness(dna)
            duration = len(audio) / SAMPLE_RATE
            return {
                "success": True,
                "dna": dna,
                "completeness": completeness,
                "duration": duration,
                "sample_rate": SAMPLE_RATE,
                "dimensions": list(DNA_DIMENSIONS.keys()),
            }
        except Exception as e:
            logger.error("Analysis failed: %s", e)
            return {"error": str(e)}

    def _extract_tre(self, audio: np.ndarray) -> Dict[str, float]:
        onset_env = librosa.onset.onset_strength(y=audio, sr=SAMPLE_RATE)
        tempo, beats = librosa.beat.beat_track(onset_envelope=onset_env, sr=SAMPLE_RATE)
        beat_times = librosa.frames_to_time(beats, sr=SAMPLE_RATE)
        if len(beat_times) > 1:
            intervals = np.diff(beat_times)
            rhythm_consistency = 1.0 - min(np.std(intervals) / (60 / tempo + 1e-6), 1.0)
        else:
            rhythm_consistency = 0.5
        return {"tempo": float(tempo), "beat_count": len(beats), "rhythm_consistency": float(rhythm_consistency), "energy": float(np.mean(onset_env))}

    def _extract_rim(self, audio: np.ndarray) -> Dict[str, float]:
        hop_length, frame_length = 512, 2048
        frames = librosa.util.frame(audio, frame_length=frame_length, hop_length=hop_length)
        energy = np.sum(frames ** 2, axis=0)
        if len(energy) > 10:
            autocorr = np.correlate(energy, energy, mode="full")[len(energy) // 2 :]
            peaks, _ = signal.find_peaks(autocorr, height=np.mean(autocorr))
            pattern_strength = len(peaks) / len(energy)
        else:
            pattern_strength = 0.5
        return {"pattern_strength": float(pattern_strength), "dynamic_range": float(np.std(energy) / (np.mean(energy) + 1e-6)), "attack_rate": float(np.mean(np.diff(energy) > 0))}

    def _extract_tdu(self, audio: np.ndarray) -> Dict[str, float]:
        mfccs = librosa.feature.mfcc(y=audio, sr=SAMPLE_RATE, n_mfcc=13)
        spectral_centroid = librosa.feature.spectral_centroid(y=audio, sr=SAMPLE_RATE)
        spectral_rolloff = librosa.feature.spectral_rolloff(y=audio, sr=SAMPLE_RATE)
        return {"timbre_brightness": float(np.mean(spectral_centroid)), "timbre_darkness": 1.0 - float(np.mean(spectral_centroid) / (SAMPLE_RATE / 2)), "mfcc_mean": float(np.mean(mfccs)), "mfcc_variance": float(np.var(mfccs)), "rolloff_mean": float(np.mean(spectral_rolloff))}

    def _extract_sde(self, audio: np.ndarray) -> Dict[str, float]:
        D = np.abs(librosa.stft(audio))
        spectral_flux = np.sqrt(np.mean(np.diff(D, axis=1) ** 2))
        freqs = librosa.fft_frequencies(sr=SAMPLE_RATE)
        low_band = np.mean(D[freqs < 250])
        mid_band = np.mean(D[(freqs >= 250) & (freqs < 4000)])
        high_band = np.mean(D[freqs >= 4000])
        return {"spectral_flux": float(spectral_flux), "low_energy": float(low_band / (np.mean(D) + 1e-6)), "mid_energy": float(mid_band / (np.mean(D) + 1e-6)), "high_energy": float(high_band / (np.mean(D) + 1e-6))}

    def _extract_grm(self, audio: np.ndarray) -> Dict[str, float]:
        hop_length, frame_length = 512, 2048
        frames = librosa.util.frame(audio, frame_length=frame_length, hop_length=hop_length)
        energy = np.sum(frames ** 2, axis=0)
        dominant_mod = 0.0
        if len(energy) > 2:
            mod_freq, mod_power = signal.periodogram(energy)
            peak_idx = np.argmax(mod_power[1:]) + 1
            dominant_mod = mod_freq[peak_idx] * SAMPLE_RATE / hop_length
        return {"modulation_depth": float(np.std(energy) / (np.mean(energy) + 1e-6)), "dominant_modulation": float(dominant_mod), "rhythm_regularity": float(1.0 / (1.0 + np.std(np.diff(energy))))}

    def _extract_gtsu(self, audio: np.ndarray) -> Dict[str, float]:
        y_harm, y_perc = librosa.effects.hpss(audio)
        harmonic_energy, percussive_energy = np.sum(y_harm ** 2), np.sum(y_perc ** 2)
        pitches, magnitudes = librosa.piptrack(y=audio, sr=SAMPLE_RATE)
        pitch_confidence = np.mean(magnitudes[magnitudes > np.mean(magnitudes)])
        return {"harmonic_ratio": float(harmonic_energy / (harmonic_energy + percussive_energy + 1e-6)), "harmonic_stability": float(np.std(y_harm) / (np.mean(np.abs(y_harm)) + 1e-6)), "pitch_confidence": float(pitch_confidence / (np.max(magnitudes) + 1e-6))}

    def _extract_pms(self, audio: np.ndarray) -> Dict[str, float]:
        rms = librosa.feature.rms(y=audio)[0]
        zcr = librosa.feature.zero_crossing_rate(audio)[0]
        loudness = 20 * np.log10(rms + 1e-8)
        return {"average_loudness": float(np.mean(loudness)), "loudness_variance": float(np.var(loudness)), "transient_ratio": float(np.mean(zcr)), "dynamic_range_db": float(np.max(loudness) - np.min(loudness))}

    def _extract_gee(self, audio: np.ndarray) -> Dict[str, float]:
        onset_env = librosa.onset.onset_strength(y=audio, sr=SAMPLE_RATE)
        groove_score = 0.5
        if len(onset_env) > 4:
            groove_entropy = float(entropy(np.abs(np.diff(onset_env[:100])) + 1e-10))
            groove_score = 1.0 / (1.0 + groove_entropy)
        return {"groove_score": float(groove_score), "groove_entropy": float(np.std(onset_env)), "syncopation": float(np.mean(onset_env[1:]) - np.mean(onset_env[:-1]))}

    def _extract_cge(self, audio: np.ndarray) -> Dict[str, float]:
        spectral_centroid = librosa.feature.spectral_centroid(y=audio, sr=SAMPLE_RATE)[0]
        tempo, _ = librosa.beat.beat_track(y=audio, sr=SAMPLE_RATE)
        rms = librosa.feature.rms(y=audio)[0]
        energy_level = np.mean(rms)
        is_danceable = 1.0 if (100 < tempo < 140 and energy_level > 0.1) else 0.5
        is_acoustic = 1.0 if np.mean(spectral_centroid) < 2000 and energy_level < 0.15 else 0.5
        return {"tempo_category": float(tempo / 200), "energy_level": float(energy_level * 10), "danceable": float(is_danceable), "acoustic": float(is_acoustic), "spectral_brightness": float(np.mean(spectral_centroid) / (SAMPLE_RATE / 2))}

    def _extract_dcp(self, audio: np.ndarray) -> Dict[str, float]:
        hop_length, frame_length = 512, 2048
        frames = librosa.util.frame(audio, frame_length=frame_length, hop_length=hop_length)
        energy = np.sum(frames ** 2, axis=0)
        compression_ratio = np.max(energy) / (np.mean(energy) + 1e-6) if len(energy) > 1 else 1.0
        return {"compression_ratio": float(compression_ratio), "peak_to_rms": float(np.max(energy) / (np.mean(energy) + 1e-6)), "crest_factor": float(np.max(np.abs(audio)) / (np.sqrt(np.mean(audio ** 2)) + 1e-6))}

    def _extract_cbe(self, audio: np.ndarray) -> Dict[str, float]:
        onset_env = librosa.onset.onset_strength(y=audio, sr=SAMPLE_RATE)
        tempo, beats = librosa.beat.beat_track(onset_envelope=onset_env, sr=SAMPLE_RATE)
        beat_times = librosa.frames_to_time(beats, sr=SAMPLE_RATE)
        beat_regularity = 1.0 / (1.0 + np.std(np.diff(beat_times))) if len(beat_times) > 1 else 0.5
        return {"beat_clarity": float(len(beats) / (len(audio) / SAMPLE_RATE / 60 * tempo / 120 + 1)), "beat_regularity": float(beat_regularity), "beat_density": float(len(beats) / (len(audio) / SAMPLE_RATE / 60))}

    def _calculate_completeness(self, dna: Dict) -> float:
        scores = [np.mean(list(v.values())) for k, v in dna.items() if isinstance(v, dict)]
        return float(np.mean(scores)) if scores else 0.0

    def compare_dna(self, dna1: Dict, dna2: Dict) -> Dict[str, float]:
        similarities = {}
        for key in DNA_DIMENSIONS:
            if key in dna1 and key in dna2:
                v1, v2 = np.mean(list(dna1[key].values())), np.mean(list(dna2[key].values()))
                similarities[key] = float(1.0 - min(abs(v1 - v2), 1.0))
        return {"overall_similarity": float(np.mean(list(similarities.values()))) if similarities else 0.0, "dimensions": similarities}


_analyzer = None


def get_analyzer() -> SoundblueprintAnalyzer:
    global _analyzer
    if _analyzer is None:
        _analyzer = SoundblueprintAnalyzer()
    return _analyzer


def analyze_audio(audio_data: bytes) -> Dict[str, Any]:
    return get_analyzer().analyze_audio(audio_data)
